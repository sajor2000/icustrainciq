# ICU Lookahead backend

Read this if you want to run, test or change what serves the board and writes the forecast.

Everything the board needs at run time is here. Model training stays in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin). What runs where, the API and the data boundary: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

![Technical architecture](../docs/diagrams/architecture.png)

## Layout

| Path | What it is |
|---|---|
| `app/board.py` | Board server: the page and `/api/forecast`, `/api/rooms`, `/api/runs`, `/api/capacity`, `/api/rerun`, `/api/ask` |
| `app/dispatcher.py` | Starts forecast runs on Fuzzball: 07:00 daily with retry and catch-up, the unit or one room on request |
| `app/chat_agent.py` | The chat agent: Nemotron 3 Nano on vLLM, tool calling, answers from tool results |
| `app/rooms.py`, `app/aggregate.py` | Write `rooms.json` (per room) and `forecast.json` (unit counts with ranges) |
| `app/clif_now.py` | Life support running at the cut and the last 12 hours of vitals, read from raw CLIF tables |
| `app/stage_ward.py`, `app/ward_check.py` | The ward's room map; checks that a ward's CLIF folder is ready |
| `app/fake_names.py` | Generated names for the room tiles (`--names fake`); never real names |
| `app/static/index.html` | The page the board serves (copy of `mockups/command-center.html`) |
| `icutwin/` | Tokenizer, model definition and probe scoring |
| `fuzzball/` | Workflow templates for Fuzzball 4.3: `t7-code`, `t7-ward`, `t7-forecast`, `t7-twin`, and `t7-fit` as a fallback. `ready/` holds them rendered for a pinned commit. `t7-smoke` is off the run path |
| `scripts/launch.sh` | One command to bring the board up on the cluster and print its link |
| `scripts/make_ready.sh`, `scripts/render_fz.py` | Render `fuzzball/ready/` for a commit; refuse a token left unfilled |
| `scripts/run_cohort.py` | A ward end to end on a laptop: no GPU, no cluster |
| `clif_demo/` | The open MIMIC-IV Demo in CLIF format, the default ward |
| `requirements/` | Hash-locked packages the cluster installs |
| `docs/` | See below |

Chat grounding, on `main`: `app/demo_context.py` builds the shared ICU snapshot, `app/evidence.py` renders answers from it, and `fuzzball/t7-lookahead-prepare.fz`, `-forecast.fz` and `-chat.fz` run it on the restricted volume `demo-context`. These three workflows have not been run on the cluster yet. Lands with PR #20: `app/capacity.py` (machines and staffing).

## Docs

| File | For |
|---|---|
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | set up, publish code, launch, check, stop, known failures |
| [`docs/CONTRACT.md`](docs/CONTRACT.md) | the JSON shapes of `forecast.json` and `rooms.json` |
| [`docs/CHAT_AGENT.md`](docs/CHAT_AGENT.md) | the chat loop, its tools and its limits |
| [`docs/LIVE_DEMO.md`](docs/LIVE_DEMO.md) | the demo-day plan |
| [`docs/CLUSTER_FACTS.md`](docs/CLUSTER_FACTS.md) | hardware, scheduler and storage facts, dated |
| [`docs/FUZZBALL_VALIDATION.md`](docs/FUZZBALL_VALIDATION.md) | validation record and storage map, dated |
| [`docs/COMPUTE_PLAN.md`](docs/COMPUTE_PLAN.md), [`docs/FUZZBALL_43_REVIEW.md`](docs/FUZZBALL_43_REVIEW.md), [`docs/FUZZBALL_TEST_PLAN.md`](docs/FUZZBALL_TEST_PLAN.md) | planning records written before the first run, dated |

## Run on the cluster

The team ran ICU Lookahead end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, and it worked.

```bash
bash scripts/launch.sh            # start what is missing, print and open the board's link
bash scripts/launch.sh --all      # publish code, stage the ward, forecast, then the board
bash scripts/launch.sh --restart  # after publishing new code
```

| Fact | Value |
|---|---|
| Volume we write | `twin-store`, mounted at `/store` |
| Volumes we only read | `mimic_clif` at `/data` (ward at `dashboard_data/`, model at `model_output/final/`); `hfcache` (Nemotron weights) |
| Probe | fitted by job 4 in vaishvikc/ICU-Twin, staged at `/store/train/probe-final.joblib` with `probe-final.meta.json` |
| Code the cluster runs | the commit pinned in `fuzzball/ready/CODE_REF`, not the working tree |

Steps, checks and failures: [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## Run locally

```bash
uv run --extra dev --extra model pytest -q
uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080
```

Open http://localhost:8080. Every POST needs `Content-Type: application/json` and `X-Lookahead: 1`.

## Run a ward on a laptop

The open demo ward, with no model:

```bash
python app/stage_ward.py clif_demo --out /tmp/ids.csv
uv run --extra model python scripts/run_cohort.py clif_demo --ward-ids /tmp/ids.csv --names fake --out /tmp/out --work /tmp/work
uv run python app/board.py --forecast /tmp/out/forecast.json --host 127.0.0.1 --port 8080
```

`run_cohort.py` builds the room map, tokenizes, cuts each stay, reads what is running at the cut from raw CLIF, and writes `rooms.json` and `forecast.json`.

| Option | Effect |
|---|---|
| no `--model` | The files say `"forecast_state": "pending-model"`. The Now side is real; every prediction is null ([`docs/CONTRACT.md`](docs/CONTRACT.md)) |
| `--model <dir> --probes <probe>` | Adds the predictions. Needs the trained weights and the probe |
| `--real-ward` | Real MIMIC-IV rooms. Local machines only; always serve with `--host 127.0.0.1` |
| `--demo-clock-hours 6` | Moves every patient six hours on, on that patient's own clock |
| `--cut-table 0,24,48,72` | Prints how many rooms remain and how many are on each support at each clock. Counts only; writes nothing |

Every script prints counts only: never a row, an id, a date of the data or a name. Patient data, model weights and probes are never stored in this repo.

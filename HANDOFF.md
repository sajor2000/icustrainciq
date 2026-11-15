# Handoff: where ICU Lookahead stands and how to take it over

Last updated: 2026-11-14, late afternoon. Branch `ui/strain-rooms-chat`, merged to `main` by pull request as work lands.

**Chat (branch `t7/ui-nemotron-chatbot`).** The chat is grounded in one published snapshot of the unit (`context.json`: the same 25 rooms, Now and forecast, one `snapshot_id`), built by `backend/app/demo_context.py` and `scripts/run_cohort.py`. Nemotron picks bounded JSON tools (`chat_agent.py`); the numbers in an answer are rendered from that evidence (`evidence.py`), not from model prose. Unknown observations stay unknown. Its workflows are `backend/fuzzball/t7-lookahead-{prepare,chat,forecast}.fz`; they read packages from `/store/py` like the rest and keep the private roster on a separate restricted volume, `demo-context`. Details and next steps: [CHATBOT_HANDOFF.md](CHATBOT_HANDOFF.md) and [`backend/docs/LOOKAHEAD_DEMO.md`](backend/docs/LOOKAHEAD_DEMO.md).

## What ICU Lookahead is

A bed board for one ICU. It shows what life support each patient is on **now** and forecasts the **next 24 hours** (07:00 to 07:00): starting a ventilator, a vasopressor or CRRT, leaving the ICU, and death. It adds the patients up into unit strain. It runs on two local Lenovo PGX machines under Fuzzball. Nothing is in the cloud. Story: the rural ICU (`docs/DECISIONS.md` D21).

## Read in this order

| Read | For |
|---|---|
| [`README.md`](README.md) | screenshots and the overview |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | what runs where, tech stack, endpoints, every diagram, run steps |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | why it is built this way (D12 to D22 are the final design) |
| [`docs/FRONTEND_SPEC.md`](docs/FRONTEND_SPEC.md), [`DESIGN.md`](DESIGN.md) | the board: screens, data it reads, look |
| [`backend/README.md`](backend/README.md), [`backend/docs/CONTRACT.md`](backend/docs/CONTRACT.md) | the backend and the JSON shapes |
| [`backend/docs/LIVE_DEMO.md`](backend/docs/LIVE_DEMO.md) | the cluster runbook |
| [`backend/docs/COMPUTE_PLAN.md`](backend/docs/COMPUTE_PLAN.md) | which machine and GPU runs what |
| [`backend/docs/FUZZBALL_43_REVIEW.md`](backend/docs/FUZZBALL_43_REVIEW.md) | workflow files checked against the Fuzzball 4.3 docs |
| `backend/docs/FUZZBALL_VALIDATION.md`, `backend/docs/FUZZBALL_TEST_PLAN.md` | what was checked against the live cluster and the storage map; the step-by-step test |

## Where the code is

| Part | Path | Owner going forward |
|---|---|---|
| Board page (one HTML file, no build step) | `mockups/command-center.html`; served copy `backend/app/static/index.html` | Frontend (J.C., Dema) |
| Board server, dispatcher, chat agent | `backend/app/board.py`, `dispatcher.py`, `chat_agent.py` | Services lane |
| Forecast builders, life support now | `backend/app/rooms.py`, `aggregate.py`, `clif_now.py`, `stage_ward.py` | Forecast lane |
| Tokenizer, model definition, probe scoring | `backend/icutwin/` | Vaishvik (training stays in the ICU-Twin repo) |
| Fuzzball workflows | `backend/fuzzball/*.fz` | Fuzzball lane |
| Diagrams (editable HTML + PNG) | `docs/diagrams/` | anyone; use the diagram-design skill |

## Run it

```bash
# the board with made-up data, no backend
python3 -m http.server 8000      # open http://localhost:8000/mockups/command-center.html#synthetic

# the backend tests
cd backend && uv run --extra dev --extra model pytest -q

# the board server on example data
cd backend && uv run python app/board.py --forecast ../examples/forecast.json \
  --static ../mockups/command-center.html --port 8080
```

On the cluster: the numbered list under Status, below.

## Status

Facts as of 2026-11-14, late afternoon. Record of the cluster checks: [`backend/docs/FUZZBALL_VALIDATION.md`](backend/docs/FUZZBALL_VALIDATION.md).

### To run it on the cluster

Files: `backend/fuzzball/ready/` (fully rendered for the final cohort; `README.md` there). Each step: `fuzzball workflow validate <file> && fuzzball workflow start <file> --name <name>`. Nothing below has been started by anyone yet except step 1.

| # | Step | State |
|---|---|---|
| 1 | The cohort and the names are on the cluster: `mimic_clif:/dashboard_data/` holds the 19 CLIF tables, `dashboard_patients_unit25.parquet` and `name.parquet` | **Done.** The folder was made by a teammate's workflow (`t7-fc-dashboard-patients.fz`); `name.parquet` was placed by two one-core `fuzzball run` jobs from J.C.'s session (checksums match the local copy). The names are fictional |
| 2 | Create the one missing volume: `fuzzball volume create team7 twin-store --size 50GiB` | **Ready to run** (needs the team's go-ahead). Until then every file fails `validate` on this volume only |
| 3 | Merge this branch to `main`, then `cd backend && scripts/make_ready.sh` and commit `fuzzball/ready/` | **Ready to run.** Needed because the commit pinned in `ready/t7-code.fz` today predates the storage change (`fuzzball/ready/README.md`) |
| 4 | Publish the code and the Python packages: `ready/t7-code.fz` (CPU only) | **Blocked** by 2 and 3 |
| 5 | Confirm the trained model | **Found, not yet loaded by our code.** Training packaged checkpoint 2616 of run `ep2-20261114c` to `mimic_clif:/model_output/final/` and its own load test passed. Unverified: that our extractor loads it with our pinned packages, and that `tokenized_output/` has the three token files and the same vocabulary. `t7-fit` checks both first |
| 6 | `ready/t7-fit.fz`: features and probes, once per model (one GPU) | **Blocked** by 4 |
| 7 | `ready/t7-ward.fz`: checks the cohort and the names file, stages the 25 rooms | **Blocked** by 6 |
| 8 | `ready/t7-twin.fz`: board, dispatcher, Nemotron (one GPU) | **Blocked** by 4; useful after 7 |
| 9 | First unit forecast: "Update the unit" on the board (the dispatcher starts it), or `ready/t7-forecast-unit.fz` by hand as `--name t7-forecast-manual` | **Blocked** by 7 |
| 10 | Open the board: `fuzzball workflow connect --name board --endpoint web <t7-twin id>` | **Blocked** by 8 |

Storage in one line: `mimic_clif` is only read (cohort, model, training tokens); everything ICU Lookahead writes goes to the one new volume `twin-store`; Nemotron is served from `hfcache`.

### Pieces

| Piece | State |
|---|---|
| Board design, Dema's figure and threshold toggle, forecast-not-ready state | Done, on `main` |
| Final page served by the backend (`backend/app/static/index.html`) | Done |
| Backend services, life support at 07:00 from raw CLIF, cohort pipeline, fictional names | Done; 282 tests pass, ruff clean |
| Workflow files match the real cluster; `t7-code` publishes this repo's `backend/` | Done; all six ready files pass `fuzzball workflow validate` once `twin-store` exists (checked with a stand-in volume) |
| Anything of ours run on the real cluster | **Not done.** Only read-only calls and the two small jobs that placed `name.parquet` |
| Model predictions on the 25 demo patients | Waiting for steps 2 to 9. Until then the board shows the Now side and "forecast not ready" |

## Rules that must hold

- **Patient data never enters git.** The 25 demo patients are real MIMIC-IV records. They live in `backend/data/local/` (git-ignored) and on the Fuzzball volume `mimic_clif` (`dashboard_data/`). The repo is public. Logs and reports carry counts only.
- Names on the board are invented, on the cluster too: `fake_names.py` generates one per room number (`--names fake`); the older `name.parquet` is no longer read.
- Every POST to the board needs `Content-Type: application/json` and `X-Lookahead: 1`.
- Only the dispatcher starts forecast runs. One GPU job at a time beside the chat model.
- Wording: "trained and run on local hardware", never "trained on this hospital's patients".

## Open decisions for the team

1. Who creates `twin-store`, and when (step 2). If the `team7` storage is node-local, it must sit where jobs can also mount `mimic_clif` (`FUZZBALL_VALIDATION.md`).
2. One volume now holds the board's files and the staged patient tokens. Accept that for the demo (treat `twin-store` as restricted and clear it after judging), or go back to a second, restricted volume.
3. Is checkpoint 2616 (60% of one epoch of the second run, the one training packaged as `final`) the model to demo, or will training package another? A new model means `t7-fit` again.
4. The demo clock: at 24 h after ICU arrival no patient in the cohort is on CRRT. Pick the clock setting once the cut table is in `LIVE_DEMO.md`.
5. First live check: does a forecast start while `t7-twin` is up? (`COMPUTE_PLAN.md`.)
6. ECMO: one cohort patient has ECMO records; the board leaves ECMO out.
7. "Not improving" is derived on the page. A real "comes off support" prediction would need a new model task.

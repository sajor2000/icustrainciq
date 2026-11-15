# Handoff

Read this if you are taking over ICU Lookahead and need its state, its owners and the next steps.

Last updated: 2026-11-14. `main` holds the team's merged work (PR #19), the name ICU Lookahead (D24) and the chat grounded in a shared ICU snapshot (PR #16). One pull request is open: #20 (staffing and capacity in the backend, final board page).

## What it is

A bed board for one ICU. It shows the life support each patient is on now and forecasts the next 24 hours (07:00 to 07:00): starting a ventilator, a vasopressor or CRRT, leaving the ICU, and death. It adds the patients up into unit strain. It runs on two local Lenovo ThinkStation PGX machines under CIQ Fuzzball 4.3. Nothing is in the cloud.

## Read in this order

| Read | For |
|---|---|
| [`README.md`](README.md) | the overview and screenshots |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | what runs where, tech stack, endpoints, data boundary, every figure |
| [`docs/RESULTS.md`](docs/RESULTS.md) | held-out results per task |
| [`backend/docs/RUNBOOK.md`](backend/docs/RUNBOOK.md) | set up, publish code and relaunch on the cluster |
| [`backend/README.md`](backend/README.md), [`backend/docs/CONTRACT.md`](backend/docs/CONTRACT.md) | the backend and the JSON shapes |
| [`backend/docs/CHAT_AGENT.md`](backend/docs/CHAT_AGENT.md), [`backend/docs/LOOKAHEAD_DEMO.md`](backend/docs/LOOKAHEAD_DEMO.md), [`CHATBOT_HANDOFF.md`](CHATBOT_HANDOFF.md) | the chat: its tools, the shared ICU snapshot, its workflows and next steps |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | why it is built this way |
| [`docs/FRONTEND_SPEC.md`](docs/FRONTEND_SPEC.md), [`DESIGN.md`](DESIGN.md) | the board: screens, states, look |

## Team

Names and affiliations as listed by the [CLIF Consortium](https://clif-icu.com/team).

| Name | Affiliation | Owns |
|---|---|---|
| J.C. Rojas, MD | Rush University | product, board and chat, Fuzzball workflows, docs |
| Kaveri Chhikara, MS | UChicago Medicine | forecast pipeline on the cluster, dispatcher, `launch.sh`, runbook |
| Vaishvik Chaudhari, MS | Rush University | the patient model: tokenizer, training, the ICU + 24 h cut, probes |
| Dema Therese, MS | UChicago Medicine | board design and the capacity model |
| Zewei ('Whiskey') Liao, MS | UChicago Medicine | team member |

## Where the code is

| Part | Path |
|---|---|
| Board page (one HTML file, no build step) | `mockups/command-center.html`; served copy `backend/app/static/index.html` |
| Board server, dispatcher, chat agent | `backend/app/board.py`, `dispatcher.py`, `chat_agent.py` |
| Chat grounding: the shared ICU snapshot and the evidence answers are rendered from | `backend/app/demo_context.py`, `evidence.py`; workflows `backend/fuzzball/t7-lookahead-prepare.fz`, `-forecast.fz`, `-chat.fz`; volume `demo-context` |
| Forecast builders, life support now, generated names | `backend/app/rooms.py`, `aggregate.py`, `clif_now.py`, `stage_ward.py`, `fake_names.py` |
| Tokenizer, model definition, probe scoring | `backend/icutwin/` |
| Fuzzball workflows | `backend/fuzzball/*.fz`; rendered for a pinned commit in `backend/fuzzball/ready/` |
| Launch and render scripts | `backend/scripts/launch.sh`, `make_ready.sh`, `render_fz.py` |
| Training workflows (jobs 2 to 4) | [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin), `workflows/` |
| Figures | `docs/diagrams/make_figures.py` writes the HTML; PNGs sit beside it, night copies in `docs/site/night/` |

## Run it

| Where | Command |
|---|---|
| Cluster | `cd backend && bash scripts/launch.sh` (variants `--all`, `--restart`, `--forecast`, `--link`, `--no-open`) |
| Laptop, the page with made-up data | `python3 -m http.server 8000`, then open `http://localhost:8000/mockups/command-center.html#synthetic` |
| Laptop, the board server on example data | `cd backend && uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080` |
| Tests | `cd backend && uv run --extra dev --extra model pytest -q` and `ruff check app tests` |

## Status

The team ran ICU Lookahead end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, and it worked.

| Piece | State |
|---|---|
| The whole app on the cluster: `t7-code`, `t7-ward`, `t7-forecast`, `t7-twin` | Ran end to end with `launch.sh` |
| Patient model | Trained on both GPUs; checkpoint 2616 of 4351 packaged at `mimic_clif:/model_output/final/` |
| Probes | Fitted by job 4 beside the model; held-out results in `docs/RESULTS.md`. The forecast reads the staged copy at `/store/train/probe-final.joblib` with its `probe-final.meta.json` |
| Board page, served by the backend | On `main`. The final page with staffing lands with PR #20 |
| Board server, dispatcher, chat agent, life support now, generated names | On `main`, with tests |
| Chat grounded in a shared ICU snapshot (`demo_context.py`, `evidence.py`, `t7-lookahead-*.fz`, volume `demo-context`) | On `main`, with tests on synthetic data. Its workflows have not been run on the cluster |
| `t7-twin` without Nemotron (the no-chat fallback) | Not run |
| Launch path (`launch.sh`, `RUNBOOK.md`) | On `main`; the path the team ran |
| `backend/fuzzball/ready/` | Pins commit `617edc0`, older than the templates. Render again before publishing from this repo |

## Next steps on the cluster

1. Merge the open pull request, then `cd backend && scripts/make_ready.sh $(git rev-parse HEAD)` and commit `fuzzball/ready/`.
2. Check the ingress line names this repo: `grep -h "uri:.*http" fuzzball/ready/*.fz | sort -u`.
3. If `twin-store` was recreated, stage job 4's probe again (`RUNBOOK.md` section 4).
4. `bash scripts/launch.sh --all`, then `--restart` after any later code publish.

## Rules that must hold

- Patient data never enters git. The 25 demo patients are MIMIC-IV records. They live in `backend/data/local/` (git-ignored) and on the Fuzzball volume `mimic_clif`. The repo is public. Logs and reports carry counts only.
- Names on the board are generated per room number by `fake_names.py` (`--names fake`), on the cluster too.
- Every POST to the board needs `Content-Type: application/json` and `X-Lookahead: 1`.
- Only the dispatcher starts forecast runs. One GPU job at a time beside the chat model.
- Do not start, stop or delete anything on the cluster without the team's go-ahead.
- Wording: "trained and run on local hardware", never "trained on this hospital's patients".

## Open decisions

| # | Question |
|---|---|
| 1 | `twin-store` holds the board's files and the staged patient tokens. Keep one restricted volume and clear it after judging, or adopt the separate `demo-context` volume the `t7-lookahead-*` workflows use? |
| 2 | Is checkpoint 2616 (60% of one epoch) the model to demo? A new model means job 4 again and a newly staged probe |
| 3 | The demo clock: at 24 h after ICU arrival no patient in the cohort is on CRRT. Pick the clock setting for the demo |
| 4 | ECMO: one cohort patient has ECMO records; the board leaves ECMO out |
| 5 | "Not improving" is derived on the page. A "comes off support" prediction would need a new model task |

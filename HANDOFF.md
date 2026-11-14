# Handoff: where Lookahead stands and how to take it over

Last updated: 2026-11-14, afternoon. Branch `ui/strain-rooms-chat`, draft PR #3 into `main`.

## What Lookahead is

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
| `backend/docs/FUZZBALL_TEST_PLAN.md` | step-by-step test on the real cluster (being written) |

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

On the cluster, in this order, only after training finishes: `t7-fit` → load the 25 demo patients (`t7-ward`) → `t7-twin` → first unit forecast → open the board. Details: `docs/ARCHITECTURE.md` "Before the live demo".

## Status

| Piece | State |
|---|---|
| Board design (two tabs, Now / Next 24 h, percentages, icons, hover legends, chat widget, names) | Done, in the PR |
| Dema's people figure and risk-threshold toggle (50 / 25 / 10%) | In progress |
| Backend services with review and security fixes | Done, tests pass locally |
| Life support running at 07:00 from raw CLIF | Done |
| Final 25 demo patients wired into the pipeline, fictional names, `t7-ward` | In progress |
| Fuzzball 4.3 review fixes | In progress |
| Final page copied into `backend/app/static/` and checked against the board server | To do |
| Anything run on the real cluster | **Not done.** Nothing here has run on Fuzzball. Training was running, so no cluster calls were made. |
| Model predictions on the 25 demo patients | Waiting for the trained model and the probe fit |

## Rules that must hold

- **Patient data never enters git.** The 25 demo patients are real MIMIC-IV records. They live in `backend/data/local/` (git-ignored) and, later, on a Fuzzball volume. The repo is public. Logs and reports carry counts only.
- Names on the board are invented (`name.parquet`, `fake_names.py`).
- Every POST to the board needs `Content-Type: application/json` and `X-Lookahead: 1`.
- Only the dispatcher starts forecast runs. One GPU job at a time beside the chat model.
- Wording: "trained and run on local hardware", never "trained on this hospital's patients".

## Open decisions for the team

1. How the 25 demo patients get onto the cluster: copy the extract to a volume, or rebuild it there from the ID list.
2. The demo clock: at 24 h after ICU arrival no patient in the cohort is on CRRT. Pick the clock setting once the cut table is in `LIVE_DEMO.md`.
3. First live check after training: does a forecast start while `t7-twin` is up? (`COMPUTE_PLAN.md`: `exclusive` reserves a whole machine.)
4. ECMO: one cohort patient has ECMO records; the board leaves ECMO out.
5. "Not improving" is derived on the page. A real "comes off support" prediction would need a new model task.

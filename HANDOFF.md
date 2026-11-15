# Handoff

Read this if you are taking over ICU Horizon and need its state, its owners and the next steps.

Last updated: 2026-11-15.

> **The demo runs from the team's ICU-Twin repo ([github.com/vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin)). Do not run `launch.sh` from this repo; its `ready/` files would overwrite the team's code on the shared volume.**

**Status in one line:** ICU-Twin is the demo repo. This repo is final: it holds the polished board page, the docs, the one-pager and every fix made after the team's code was synced, and it is the place to read what to port back.

**For the morning meeting, read first:** [`docs/ICU_TWIN_DELTA.md`](docs/ICU_TWIN_DELTA.md) (every change here against ICU-Twin, its risk to the running demo, port before or after), then [`docs/UI_REVIEW.md`](docs/UI_REVIEW.md) (each page change with pictures).

## What it is

A bed board for one ICU. It shows the life support each patient is on now and forecasts the next 24 hours (07:00 to 07:00): starting a ventilator, a vasopressor or CRRT, leaving the ICU, and death. It adds the patients up into unit strain. It runs on two local Lenovo ThinkStation PGX machines under CIQ Fuzzball 4.3. Nothing is in the cloud.

## Read in this order

| # | Read | For |
|---|---|---|
| 1 | [`docs/ICU_TWIN_DELTA.md`](docs/ICU_TWIN_DELTA.md) | every change in this repo against the team's ICU-Twin repo, the risk of each to the running demo, and what to port before or after the demo |
| 2 | [`docs/UI_REVIEW.md`](docs/UI_REVIEW.md) | each change to the team's board page: before and after pictures, why, how to undo, and how to port |
| 3 | [`README.md`](README.md) | the overview and screenshots |
| 4 | [`docs/submission/`](docs/submission/), [`docs/ONE_PAGER.md`](docs/ONE_PAGER.md) | the printed one-sheet and the five-minute demo script; the one-page explainer of the model and of how Fuzzball ran it |
| 5 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | what runs where, tech stack, endpoints, data boundary, every figure |
| 6 | [`docs/RESULTS.md`](docs/RESULTS.md) | held-out results per task |
| 7 | [`backend/docs/RUNBOOK.md`](backend/docs/RUNBOOK.md) | set up, publish code and relaunch on the cluster |
| 8 | [`backend/README.md`](backend/README.md), [`backend/docs/CONTRACT.md`](backend/docs/CONTRACT.md) | the backend and the JSON shapes |
| 9 | [`backend/docs/CHAT_AGENT.md`](backend/docs/CHAT_AGENT.md), [`backend/docs/LOOKAHEAD_DEMO.md`](backend/docs/LOOKAHEAD_DEMO.md), [`CHATBOT_HANDOFF.md`](CHATBOT_HANDOFF.md) | the chat: its tools, the shared ICU snapshot, its workflows and next steps |
| 10 | [`docs/DECISIONS.md`](docs/DECISIONS.md) | why it is built this way (D25 to D27 for the page) |
| 11 | [`docs/FRONTEND_SPEC.md`](docs/FRONTEND_SPEC.md), [`DESIGN.md`](DESIGN.md) | the board: screens, states, look |
| 12 | [`docs/WHAT_WE_FIXED.md`](docs/WHAT_WE_FIXED.md), [`docs/UPSTREAM_REVIEW_NOTES.md`](docs/UPSTREAM_REVIEW_NOTES.md) | what the CodeRabbit reviews found, what was fixed, and patch text for teammates' code |

Old plans are in [`docs/archive/`](docs/archive/README.md).

## Team

Names and affiliations as listed by the [CLIF Consortium](https://clif-icu.com/team).

| Name | Affiliation |
|---|---|
| J.C. Rojas, MD, MS | Rush University |
| Kaveri Chhikara, MS | UChicago Medicine |
| Vaishvik Chaudhari, MS | Rush University |
| Dema Therese, MS | UChicago Medicine |
| Zewei ('Whiskey') Liao, MS | UChicago Medicine |

We built it together; there are no per-person roles.

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
| Cluster | **From the ICU-Twin checkout, not from here:** `bash scripts/launch.sh` (variants `--all`, `--restart`, `--forecast`, `--link`, `--no-open`). The same script is in `backend/scripts/` here for reference only |
| Laptop, the page with made-up data | `python3 -m http.server 8000`, then open `http://localhost:8000/mockups/command-center.html#synthetic` |
| Laptop, the board server on example data | `cd backend && uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080` |
| Tests | `cd backend && uv run --extra dev --extra model pytest -q` (431 tests) and `ruff check app tests`. With a browser: `uv run --extra dev --extra model --with playwright python -m pytest -q` (459: 28 drive the page) |

## Status

The team ran ICU Horizon end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, from ICU-Twin, and it worked. The workflow files as rendered from this repo have not been run on the cluster.

| Piece | State |
|---|---|
| The whole app on the cluster: `t7-code`, `t7-ward`, `t7-forecast`, `t7-twin` | Ran end to end with `launch.sh` |
| Patient model | Trained on both GPUs; checkpoint 2616 of 4351 packaged at `mimic_clif:/model_output/final/` |
| Probes | Fitted by job 4 beside the model; held-out results in `docs/RESULTS.md`. The forecast reads the staged copy at `/store/train/probe-final.joblib` with its `probe-final.meta.json` |
| Board page, served by the backend | Final: the team's design (D25) with the refinements of D27. Not yet in ICU-Twin; see `docs/UI_REVIEW.md` |
| Staffing and capacity in the backend | On `main` (PR #20), with tests. The page shows machine capacity; staffing is in the API and the chat |
| Board server, dispatcher, chat agent, life support now, generated names | On `main`, with tests |
| Chat grounded in a shared ICU snapshot (`demo_context.py`, `evidence.py`, `t7-lookahead-*.fz`, volume `demo-context`) | On `main`, with tests on synthetic data. Its workflows have not been run on the cluster |
| `t7-twin` without Nemotron (the no-chat fallback) | Not run |
| Launch path (`launch.sh`, `RUNBOOK.md`) | On `main`; the path the team ran, from ICU-Twin |
| `backend/fuzzball/ready/` | Pins commit `617edc0`, older than the templates and older than this pull request. **Re-render `ready/` after this pull request merges** (step 1 below); until then it must not be launched |
| Open pull requests | #17, #18 and #22 are older doc and review branches; #24 is superseded by the final pull request (its fixes are in it) |

## The morning steps (2026-11-15)

1. **Meet (the team).** Go through the summary table in [`docs/ICU_TWIN_DELTA.md`](docs/ICU_TWIN_DELTA.md) and section 1 of [`docs/UI_REVIEW.md`](docs/UI_REVIEW.md). Mark each row: port before the demo, port after, or keep here only.
2. **Port what was approved into ICU-Twin**, on a branch there: the page (one file), and the four small fixes (`UI_REVIEW.md` section 4). Run ICU-Twin's tests.
3. **Publish from ICU-Twin** (workflows and backend): its own `make_ready.sh`, then `bash scripts/launch.sh --code --restart`, and check the board at its link. Press "Update the unit" once and watch the progress strip: that is the one live check the page still needs.
4. **Rehearse** with [`docs/submission/DEMO_SCRIPT.md`](docs/submission/DEMO_SCRIPT.md); fill its `[FILL]` slots (speaker, driver, link, timings).
5. **Print** [`docs/submission/one-sheet.pdf`](docs/submission/one-sheet.pdf) after filling the slots in [`docs/submission/FILL_IN.md`](docs/submission/FILL_IN.md).

## If this repo is ever launched on the cluster

Not for the demo. Afterwards, and only with the team's go-ahead:

1. Merge the final pull request, then **re-render `ready/`**: `cd backend && scripts/make_ready.sh $(git rev-parse HEAD)` and commit `fuzzball/ready/`. The files there now pin `617edc0`.
2. Check the ingress line names this repo: `grep -h "uri:.*http" fuzzball/ready/*.fz | sort -u`.
3. If `twin-store` was recreated: publish the code first, `bash scripts/launch.sh --code` (the probe's sidecar command imports `icutwin` from `/store/code` and `/store/py`, which a new volume does not have yet), then stage job 4's probe and its sidecar (`RUNBOOK.md` section 4). On a volume that still holds the staged probe, skip this step.
4. `bash scripts/launch.sh --all --restart`. `--all` alone publishes the code but leaves a running `t7-twin` on the code it loaded at start; `--restart` reloads it, and is skipped when nothing is running. This overwrites `/store/code` on the shared volume, so the team's code there is replaced.

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
| 5 | Coming off life support is not forecast. A "comes off support" prediction would need a new model task |
| 6 | The page proposals not applied: the page's blue and three type sizes against DESIGN.md (`docs/UI_REVIEW.md` section 3). The standard flag lines 20 / 40 / 60 are applied (D26, PR #24) |

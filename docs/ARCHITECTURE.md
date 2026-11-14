# Architecture: the team's guide

How Lookahead is built, where each part runs, and how to start it. Every figure has an editable HTML source next to its PNG in [`diagrams/`](diagrams/). JSON shapes: [`../backend/docs/CONTRACT.md`](../backend/docs/CONTRACT.md). Runbook: [`../backend/docs/LIVE_DEMO.md`](../backend/docs/LIVE_DEMO.md).

**Nothing is hosted in the cloud.** The real app runs on two local Lenovo PGX machines, on site, and Fuzzball starts every part of it. A developer laptop can run a demo copy with synthetic data. GitHub holds code only.

This is the rural-ICU case: a hospital with one unit and no cloud contract can run the whole product on two desk-size machines it owns.

## What runs where

![What runs where](diagrams/hosting.png)

"Local Lenovo PGX (Fuzzball)" means the two on-site GB10 machines. "Developer laptop" is a separate place. Fuzzball places CPU work on either machine; each machine has one GPU.

| Component | Machine | Run by | Port / URL | Data it can see |
|---|---|---|---|---|
| Board page | Clinician's browser, hospital network | served by the board server | the board's HTTPS endpoint | unit counts, room entries (room numbers only) |
| Board server (`app/board.py`), with the chat agent | Local Lenovo PGX, CPU | Fuzzball workflow `t7-twin`, service `board` | 8080; team-scoped HTTPS endpoint `web` | `forecast.json`, `rooms.json`, `capacity.json` |
| Dispatcher (`app/dispatcher.py`) | Local Lenovo PGX, CPU | `t7-twin`, service `dispatcher` | 9000, inside the workflow only | run log, workflow list; no patient data |
| Nemotron 3 Nano (vLLM) | Local Lenovo PGX, GPU 1 of 2, held | `t7-twin`, service `nemotron` | 8000, inside the workflow only | what the chat tools return: counts and room entries |
| Forecast run, with the patient model | Local Lenovo PGX, CPU then GPU 2 of 2 then CPU | Fuzzball workflow `t7-forecast`, jobs `precheck`, `extract`, `score` | none | the 25 demo patients, staged tokens, model, probes |
| Setup workflows | Local Lenovo PGX; `t7-fit` uses one GPU, the others CPU | Fuzzball workflows `t7-code`, `t7-fit`, `t7-ward`, in this order | none | code, training tokens, the 25 demo patients |
| Volume `mimic_clif` (exists, read only) | Fuzzball storage for team7 | Fuzzball volume | mounted at `/data` | the 25 demo patients and `name.parquet` in `dashboard_data/`, the trained patient model in `model_output/final/`, training tokens |
| Volume `twin-store` (to create) | Fuzzball storage for team7 | Fuzzball volume | mounted at `/store` | everything Lookahead writes: code, packages, probes, staged tokens, `rooms.json`, `forecast.json`, `capacity.json`, `runs.jsonl` |
| Volume `hfcache` (exists) | Fuzzball storage for team7 | Fuzzball volume | mounted at `/cache` | Nemotron weights |
| Local demo | Developer laptop | `uv run python app/board.py` | `http://localhost:8080` | synthetic `examples/` files |
| 25 demo patients | Already on the cluster, on `mimic_clif`; a local copy on the laptop | read by `t7-fit`, `t7-ward`, `t7-forecast` | `mimic_clif:/dashboard_data/`; `backend/data/local/unit25/`, git-ignored | real MIMIC-IV rows with fictional names; never in git |
| Code | GitHub | `sajor2000/icustrainciq` (page, `backend/`, docs); ICU-Twin (training) | github.com | code only; never data, weights or probes |

The demo has one user at a time. There is no login and no user id. `role` is a label on the log and the answer.

## Tech stack

| Layer | Technology | Version or pin | Why |
|---|---|---|---|
| Page | one HTML file, plain JavaScript and CSS, inline SVG icons | no build step, no third-party scripts | opens offline; the board server sends it as is |
| Board server, dispatcher | Python standard library `http.server` | Python 3.12 (`python:3.12-slim`) | nothing to install inside the service |
| Chat | NVIDIA Nemotron 3 Nano 30B FP8 on vLLM, tool calling | `nvcr.io/nvidia/vllm:25.12.post1-py3`; model commit `9bee1944…` | answers come from tool results; runs on the local GPU |
| Patient model | `icutwin` decoder, Gemma 4 text layers; one forward pass, then logistic probes | `transformers` 5.23.0, `scikit-learn` 1.9.1, `nvcr.io/nvidia/pytorch:25.11-py3` | one pass per patient takes minutes on one GPU |
| Data | CLIF 2.1 tables (MIMIC-IV in CLIF format), parquet | `clifpy` 2.1 or later, `polars` 2.1.0, `pyarrow` 26.0.1 | one table format for every site |
| Orchestration | Fuzzball workflows on 2 Lenovo PGX (GB10) | Fuzzball 4.3.1 | starts services and jobs, shares the two GPUs |
| Packaging | `uv`; hash-locked requirements for the cluster | `backend/uv.lock`, `backend/requirements/t7-*.txt` | the same versions on every run |
| Tests | `pytest`, `ruff` | `dev` extra in `backend/pyproject.toml` | guards and JSON shapes are tested without a cluster |

## Two models, two jobs

| | Patient model | Chat model |
|---|---|---|
| What it is | `icutwin`, a small decoder with Gemma 4 text layers | NVIDIA Nemotron 3 Nano |
| Who trained it | **We did**, on the two Lenovo machines, across both GPUs under Fuzzball | **NVIDIA.** We use it as it is; we did not train or fine-tune it |
| What it reads | each patient's chart as a sequence of events, the way a language model reads words | the forecast files, through tools |
| What it does | one pass per patient, then a small classifier per question gives the five predictions | answers questions in plain words; can ask the dispatcher for a new run when a user asks |
| What it never does | talk to users | predict anything about a patient |
| Where it runs | forecast job, GPU 2 | always-on service on vLLM, GPU 1 |

The trained model knows ICU data. The NVIDIA model knows language. Both run on the two local machines.

### How the patient model makes a prediction

1. **It learns the language of the ICU.** We trained it to read a patient's chart as a sequence of events (labs, vital signs, drugs, machines) and predict the next event, the way a language model predicts the next word.
2. **We take its last layer.** At 07:00 the model runs once over each patient's chart so far. We keep the output of its last layer: one vector that summarises the patient's state.
3. **Five small classifiers read that vector.** One for each event that matters to clinicians in the next 24 hours: starting a ventilator, starting a vasopressor, starting CRRT, leaving the ICU, and death. Each gives a percentage. The classifiers are fitted on past patients whose outcomes are known.
4. **The patients are added up** into what the unit will need, with a likely range.

Why this way: one pass per patient takes minutes on one GPU, with no need to generate thousands of possible futures. The five questions were chosen because they drive beds, machines and staff.

## 1. Technical architecture

![Technical architecture](diagrams/architecture.png)

The browser talks to one service, the board server. The board server reads three files from `twin-store`, asks Nemotron through the chat agent, and asks the dispatcher to start or report runs. The dispatcher starts `t7-forecast`, which runs our patient model on the second GPU. Storage is one volume to write, `twin-store`, and two that are only read: `mimic_clif` (demo patients, patient model) and `hfcache` (Nemotron weights). Patient rows stay inside the dashed zone. Source: [`diagrams/architecture.html`](diagrams/architecture.html).

## 2. API map

![API map](diagrams/api.png)

| Call | Body | Returns or starts |
|---|---|---|
| `GET /` | | the page (`app/static/index.html`) |
| `GET /api/forecast` | | `forecast.json`: five predictions as unit counts with 80% ranges |
| `GET /api/rooms` | | `rooms.json`: one entry per stage-ward room |
| `GET /api/runs` | | dispatcher status: next 07:00, `scheduled.state`, running update, last runs, demo clock |
| `GET /api/capacity` | | `life_support_patients`, `vents_free`, `updated_at` |
| `POST /api/rerun` | `{role, scope: "unit" or "room", room?}` | starts one forecast run; `{started, name}` or `{started: false, reason}` |
| `POST /api/capacity` | `{life_support_patients, vents_free?, role}` | saves `capacity.json`; whole numbers 0 to 50 |
| `POST /api/ask` | `{question, role, room?, seen_made_at?}` | `{answer, made_at, trace?}` |

Every POST needs `Content-Type: application/json` and `X-Lookahead: 1`. If the browser sends an `Origin` header, it must match `Host`. Anything else gets 403. The dispatcher has two internal endpoints, `GET /status` and `POST /run`; only the board server and its chat agent call them. Source: [`diagrams/api.html`](diagrams/api.html).

## 3. How the board starts a Fuzzball job

![Update the unit, end to end](diagrams/trigger.png)

1. The user presses "Update the unit". The page sends `POST /api/rerun`.
2. The board server checks the POST rule and passes the request to the dispatcher (`POST /run`).
3. The dispatcher checks its guards: one forecast at a time, 20 minutes between updates of the same scope.
4. Fuzzball 4.3 has no workflow parameters. The dispatcher fills six tokens (`@SCOPE@`, `@ROOM@`, `@HOURS@`, `@WARD_FLAG@`, `@CLIF_DIR@`, `@NAMES@`) in `t7-forecast.fz` and runs `fuzzball workflow start` on the copy.
5. Three jobs run: `precheck` (CPU), `extract` (GPU: winnow at the cut, one forward pass), `score` (CPU: probes, `rooms.py`, `aggregate.py`, `clif_now.py`).
6. `score` writes `rooms.json`, then `forecast.json`. Each file is written whole.
7. The page polls `/api/runs` every 30 seconds during a run, and every 5 minutes otherwise. When `made_at` changes it reloads and redraws.

Room variant: `{scope: "room", room: 12}` rewrites that one room in `rooms.json`. It is refused until a whole-unit run exists. Source: [`diagrams/trigger.html`](diagrams/trigger.html).

## 4. The 07:00 run

![The 07:00 run, end to end](diagrams/sequence.png)

The dispatcher is the clock. At 07:00 (America/Chicago) it starts a unit run by itself. If a GPU workflow is running, or the start fails, it tries again each minute for 10 minutes. A dispatcher that starts after 07:00 with no run since the cut runs it once. Source: [`diagrams/sequence.html`](diagrams/sequence.html).

`GET /api/runs` reports the 07:00 run in `scheduled.state`: `pending`, `ok`, `failed` or `missed`. Check it after 07:15.

## 5. Frontend: what the page shows

![What the page shows and which call feeds it](diagrams/frontend.png)

The page is one file. Its title is "Lookahead · ICU forecast, next 24 hours". It has two tabs, **Bed board** and **Unit strain**, and a **Now | Next 24 h** switch. Now shows life support running at 07:00. Next 24 h shows the forecast: one status per room (Worsening, Watch, Not improving, Leaving, Steady), a "Worry first" row, and chances as percentages. Icons stand for ventilator, vasopressor, CRRT and leaving. A room opens its own page. "Ask Lookahead" is a chat widget at the bottom right, with Unit or Room context. Source: [`diagrams/frontend.html`](diagrams/frontend.html).

## 6. Backend: modules and files

![Backend modules and files](diagrams/backend.png)

Three services run all day in `t7-twin`. Setup workflows `t7-code`, `t7-fit` and `t7-ward` run first; `t7-forecast` does the scoring. They hand off through four files in `twin-store`: `rooms.json`, `forecast.json`, `capacity.json` and `runs.jsonl`. `mimic_clif` is only read. `clif_now.py` supplies the Now side from raw CLIF tables. Source: [`diagrams/backend.html`](diagrams/backend.html).

## 7. How to run it on the cluster

![How to run it on the cluster](diagrams/workflow.png)

Grey is done. Coral is to do first. White is ready to run. Nothing has run end to end yet.

| # | Step | GPU | State |
|---|---|---|---|
| 0 | The 25 demo patients, their fictional names and the trained patient model are on `mimic_clif` | | Done |
| 1 | Create the one new volume: `fuzzball volume create team7 twin-store --size 50GiB` | | To do first |
| 2 | `t7-code`: publish this repo's `backend/` at a pinned commit, and the Python packages | none | Ready |
| 3 | `t7-fit`: fit the five probes, once per model | one GPU job | Ready |
| 4 | `t7-ward`: check the cohort and the names, stage the 25 rooms | none | Ready |
| 5 | `t7-twin`: board server, dispatcher, Nemotron | GPU 1, held | Ready |
| 6 | First unit forecast: press "Update the unit", or wait for 07:00. The dispatcher starts `t7-forecast` | GPU 2, minutes | Ready |
| 7 | Open the board: `fuzzball workflow connect --name board --endpoint web <t7-twin id>` | | Last |

"Ready" means the file in `backend/fuzzball/ready/` passes validation on the live server once `twin-store` exists. Only one GPU job runs beside Nemotron. The live list with blockers is in [`../HANDOFF.md`](../HANDOFF.md). Source: [`diagrams/workflow.html`](diagrams/workflow.html).

## Demo patients

- **What:** a CLIF-format extract of 25 real MIMIC-IV hospitalizations. 19 CLIF tables, a one-column id file `dashboard_patients_unit25.parquet`, and `name.parquet`.
- **Names:** fictional. The names on the board are invented.
- **Where:** already on the cluster, in `mimic_clif:/dashboard_data/`. Nothing needs to be copied. A local copy stays in `backend/data/local/unit25/`, which is git-ignored.
- **Rules:** real patient data. Local only. Never in git; this repo is public. Logs print counts only. `mimic_clif` is only read.
- **On the board:** runs use `--real-ward`. The board shows "Real MIMIC-IV · local only".

## Before the live demo

1. `twin-store` exists.
2. `t7-code` has published the code and the packages.
3. `t7-fit` has saved the probes.
4. `t7-ward` has staged the 25 rooms.
5. `t7-twin` is up: Nemotron, board server, dispatcher.
6. The first unit forecast has landed. Press "Update the unit", or wait for 07:00.
7. Open the board. Check both tabs, Now and Next 24 h, one room page and the chat.

Until step 6 the board shows the Now side and "forecast not ready".

## What the board predicts

Five predictions for the next 24 hours, 07:00 to 07:00: invasive ventilation (IMV), vasopressor, CRRT, leaving the ICU, death. Life support that is on now comes from raw CLIF tables (`backend/app/clif_now.py`).

## Data boundary

| Where | Holds | Never holds |
|---|---|---|
| `mimic_clif` (only read) | the 25 demo patients, training tokens, the trained patient model | anything Lookahead writes |
| `twin-store`, folders `stage/` and `train/` | tokens, features, per-stay scores; treat as restricted | |
| `rooms.json`, `forecast.json`, board server, Nemotron, browser | unit counts with ranges; room entries by room number, with invented names | patient rows, stay ids, real names |
| Laptop, GitHub | code, synthetic `examples/`, the open MIMIC-IV Demo in `backend/clif_demo` | anything from the cluster volumes |

The default ward is the open MIMIC-IV Demo. Real MIMIC-IV rooms need `--real-ward` and stay on the local machines.

## Run it locally

From `backend/`:

```bash
uv run --extra dev --extra model pytest -q
uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080
```

Open http://localhost:8080. Without Nemotron and the dispatcher, the chat and the update buttons say they are not available. The rest of the board works.

## Run it on the cluster

Lane 2 starts and stops the shared `t7-*` workflows. Ask before starting anything. The files are in `backend/fuzzball/ready/`, fully rendered for the 25 demo patients.

```bash
fuzzball volume create team7 twin-store --size 50GiB        # once
cd backend
# one step at a time, in this order: t7-code, t7-fit, t7-ward, t7-twin. Wait for each to finish before the next.
fuzzball workflow validate fuzzball/ready/t7-code.fz && fuzzball workflow start fuzzball/ready/t7-code.fz --name t7-code
fuzzball workflow connect --name board --endpoint web <t7-twin id>
```

1. `t7-code`: publishes the code and the Python packages. Run it again after every code change.
2. `t7-fit`: fits the probes. Run it once per model.
3. `t7-ward`: stages the 25 rooms. Run it again when the ward changes.
4. `t7-twin`: starts Nemotron, the board server and the dispatcher. It stays up.

Forecasts start from the board or at 07:00. The first one can also be started by hand: `fuzzball/ready/t7-forecast-unit.fz` as `--name t7-forecast-manual`. Training (`t7-build`) lives in the ICU-Twin repo and is finished. `t7-smoke` is no longer on the run path.

## Who uses it

Every role's morning, step by step: [`USER_JOURNEY.md`](USER_JOURNEY.md).

## Why it is built this way

See [`DECISIONS.md`](DECISIONS.md).

# What icustrainciq changed, for the ICU-Twin agent

Read this if you are a coding agent working in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin) and you want to bring this repo's work across, or to know why a file here no longer matches yours.

Compared on 2026-11-15:

| Repo | Commit |
|---|---|
| ICU-Twin | `fac343d` (merge of `55df710`, Dema's final board) |
| icustrainciq `main` | `ef95989` (after PRs #16, #19, #20, #23) |

## 1. How the two repos line up

| ICU-Twin | icustrainciq |
|---|---|
| `app/`, `fuzzball/`, `icutwin/`, `scripts/`, `tests/`, `requirements/` | the same folders under `backend/` |
| `app/static/index.html` | `backend/app/static/index.html`, a byte copy of `mockups/command-center.html` (edit the mockup, then copy) |
| `docs/` | split: board and decisions in `docs/`, cluster and contract in `backend/docs/` |
| `workflows/job_1` to `job_4` (training, probe) | not here: training stays in ICU-Twin |

To port a file, apply its diff with the `backend/` prefix removed. Run this repo's tests for that area first, so you know what the change is meant to do.

## 2. Is icustrainciq up to date with ICU-Twin?

Yes, for everything that runs the board.

- **Page.** The page is ICU-Twin `55df710` with this repo's layers on top (section 4.9). ICU-Twin has had no page commit since.
- **`app/`, `fuzzball/`, `icutwin/`.** Synced at ICU-Twin `360cb31` (PR #19). ICU-Twin's only later commits are `55df710` (the page, ported) and `457134e` (its own `AGENTS.md`, `CLAUDE.md` and "superseded" banners on five pre-event plans that do not exist here).
- **Left out on purpose:** `workflows/job_*`, `fuzzball/t7-build.fz`, `scripts/train_full.sh`, `tokenize_full.sh`, `extract_split.py`, `sglang_*.py`, `reach_*.py`, `examples/train_fuzzball*.yaml`, `tests/test_repo_hygiene.py`. They train or benchmark the model.

## 3. Files that differ

Lines that differ (`diff | grep -c '^[<>]'`), ICU-Twin `fac343d` against `main` `ef95989`:

| File | Lines | Section |
|---|---|---|
| `app/chat_agent.py` | 544 | 4.2, 4.3 |
| `app/aggregate.py` | 363 | 4.4, 4.8 |
| `app/board.py` | 262 | 4.2, 4.3, 4.8 |
| `app/static/index.html` | 236 | 4.9 |
| `scripts/run_cohort.py` | 210 | 4.2, 4.6 |
| `app/clif_now.py` | 87 | 4.4, 4.8 |
| `icutwin/scoring/rep_based.py` | 73 | 4.5 |
| `app/dispatcher.py` | 70 | 4.7 |
| `app/rooms.py` | 69 | 4.4, 4.8 |
| `app/stage_ward.py` | 26 | 4.2 |
| `icutwin/scoring/extractor.py` | 24 | 4.5 |
| `icutwin/scoring/winnower.py` | 24 | 4.6 |
| `fuzzball/t7-code.fz` | 22 | 4.1 |
| `scripts/render_fz.py` | 13 | 4.7 |
| `icutwin/scoring/metrics.py` | 12 | 4.10 |
| `icutwin/tokenizer/helpers.py` | 8 | 4.6 |
| `fuzzball/t7-twin.fz` | 7 | 4.3 |
| `fuzzball/t7-fit.fz` | 6 | 4.6 |
| `fuzzball/t7-forecast.fz` | 4 | 4.6 |
| `scripts/make_ready.sh` | 4 | 4.1 |
| `fuzzball/t7-ward.fz` | 2 | 4.6 |

Files only here: `app/capacity.py`, `app/demo_context.py`, `app/evidence.py`, `icutwin/scoring/provenance.py`, `fuzzball/t7-lookahead-prepare.fz`, `t7-lookahead-chat.fz`, `t7-lookahead-forecast.fz`, `scripts/prepare_lookahead_cohort.py`, `scripts/package_lookahead_demo.py`, and the tests `test_capacity.py`, `test_staffing.py`, `test_demo_context.py`, `test_demo_chat_app.py`, `test_demo_package.py`, `test_page_browser.py`.

`fuzzball/ready/` differs in every file: it is rendered from the templates for this repo's pinned commit. Never copy it; run `scripts/make_ready.sh` in your own repo.

## 4. The changes, by topic

Each topic says what changed, why, and what to take with it.

### 4.1 Which repo the cluster publishes

`t7-code.fz` and `make_ready.sh` fetch `sajor2000/icustrainciq` and publish its `backend/` folder to `/store/code`. **Do not port.** ICU-Twin publishes its own repo root.

### 4.2 Chat grounded in one published snapshot

**What.** The chat answers from one validated file, `context.json`: the same 25 rooms, the Now side and the forecast, under one `snapshot_id` and `cohort_id`.

- `app/demo_context.py` builds, validates and atomically writes the snapshot. It refuses stay ids, source dates and mixed snapshots. A roster stay that has left the ICU keeps its room slot with `present: false`.
- `app/evidence.py` writes every number in a chat answer from the tool results. The model picks tools; its own prose is never the source of a number.
- `app/chat_agent.py` has closed tool schemas, a cap of 8 tool calls and 12,000 characters, a request deadline, and a fallback when the model is down or rejects tools.
- `app/board.py` adds `--context` (serve `/api/context`; `/api/forecast` and `/api/rooms` become projections of it) and `--require-real-data`.
- `scripts/run_cohort.py` adds `--context-out`, `--tokenized-output`, `--no-extract`, `--cut-time`, `--names`, `--unit-name`. `app/stage_ward.py` accepts a given room map.
- The three `t7-lookahead-*.fz` workflows run this path on a separate restricted volume, `demo-context`.

**Why.** A unit answer and a room answer could come from different runs. The model could also state a number the forecast did not contain.

**Take with it.** `demo_context.py`, `evidence.py`, `chat_agent.py` and `board.py` together, with `test_demo_context.py`, `test_demo_chat_app.py`, `test_chat_agent.py`. Docs: `backend/docs/CHAT_AGENT.md`, `backend/docs/LOOKAHEAD_DEMO.md`, `CHATBOT_HANDOFF.md`.

**Works without it.** The board and chat still run from plain `forecast.json` and `rooms.json` when `--context` is not given.

### 4.3 Real MIMIC-IV rooms only in real-ward mode

**What.** `app/board.py` has `--real-ward`. Without it, a ward whose `ward.source` is `"mimic-iv"` is served counts-only: `/api/rooms` returns `{"rooms": [], "counts_only": true}`, `check_first` is empty, and the chat's `get_room` refuses. In real-ward mode the chat sends a room's fields to Nemotron only for a room the user asked about, with no clock fields.

**Why.** Decision D19 (`docs/DECISIONS.md`) allows real rooms only in an explicit mode. The board used to serve them whenever the files carried them.

**Take with it.** One line in `t7-twin.fz`: the board command ends with `@WARD_FLAG@`, which renders `--real-ward` for the cohort and nothing for the open demo. **If you port the `board.py` change without this line, the cohort board shows no rooms and no room chat.**

### 4.4 Unknown stays unknown

**What.** In `aggregate.py`, `rooms.py` and `clif_now.py`:

- A support whose current state raw CLIF cannot tell is `null` in `on_now`, never `false`. Unit counts add `now_known_*` and `now_unknown_*`.
- A stay with no score for a support it could start makes that unit count unavailable (`available: false`, `null` numbers), not a count that takes it as 0. The room's `any_life_support` is `null` and its `level` is `"unavailable"`.
- A patient already on one support does not blank the combined new-patient count.
- A support started and stopped before the cut has no score by the probe's rule. That is "not a new start", not missing data.
- A stay back in the ICU exactly at its cut is present (`in <= cut < out`).

**Why.** A missing observation was being shown as "off" or as zero risk.

**Take with it.** `test_lookahead.py`, `test_cohort.py`, `test_clif_now.py`, and the `forecast.json` and `rooms.json` sections of `backend/docs/CONTRACT.md`.

### 4.5 Which weights made the features

**What.** `icutwin/scoring/provenance.py` (stdlib only) holds `weights_digest` and a sidecar for each features file, `features-<split>-<model>.meta.json`. `extractor.py` writes it, including after `--merge` of shards. `rep_based.apply_probes` refuses features made with other weights, or with none recorded.

**Why.** The probe file is tied to the weights and the cut columns tie features to labels, but nothing tied features to weights. Stale features could be scored with a refit probe.

**Take with it.** All three files together. **Features extracted before this change are refused: run `icutwin-extract` again.** Training-side fitting is not checked, so `job_4_probe` is unaffected.

### 4.6 Logs hold counts only

**What.**

- `winnower.py` has `--counts-only`: it logs the number of stays per split and no outcome rates.
- `t7-fit.fz`, `t7-ward.fz` and `t7-forecast.fz` pass it on the ward winnow line. The training winnow keeps its rates.
- `icutwin/tokenizer/helpers.py`: `Logger.setLevel` clears the level cache. The logger is created directly, so `setLevel("WARNING")` after the first message did nothing.
- `scripts/run_cohort.py` winnows counts-only.

**Why.** For a 25-stay ward an outcome rate is a clinical value about a few patients.

**Take with it.** The winnower change and the three workflow lines must ship in the same `t7-code` publish. A workflow that passes `--counts-only` to an older winnower fails at that job.

### 4.7 Dispatcher

- `@CUT@` token and `replay_cut()`: the replay cut is fixed when a run is dispatched and passed to the job. Only `t7-lookahead-forecast.fz` uses it. `scripts/render_fz.py` gains `--cut`.
- A template whose header has `# needs: ward-ids` is refused when the dispatcher was started without `--ward-ids`.
- Run names are `t7-lookahead-forecast-unit-MMDD-HHMM` and `-roomN-`. The busy check still matches `t7-forecast`.
- `"ICU team"` is an accepted role.

### 4.8 Capacity and staffing

**What.** `app/capacity.py` stores machine totals (`vents_total`, `crrt_total`) and derives free machines on read; nothing derived is stored. `aggregate.py` adds `machines`, `staffing_now` and `staffing_next_24h` to `forecast.json`. `clif_now.py` counts vasoactive infusions for the 1:1 nursing rule (D23). `POST /api/capacity` accepts the totals. The chat gains `get_staffing`.

**Take with it.** `test_capacity.py`, `test_staffing.py`, and "capacity.json and /api/capacity" and "staffing" in `backend/docs/CONTRACT.md`. The page does not show a staffing card (D25); the numbers stay in the API.

### 4.9 The page, on top of `55df710`

Dema's design is unchanged. The additions:

| Addition | Where to look in the script |
|---|---|
| Reads `/api/context` first, falls back to `/api/forecast` and `/api/rooms`; refuses mixed snapshots | `loadAll` |
| Unknown current support is shown as unknown, never "No life support" | `unknownList`, `anyNew`, `noScore`, `noEst` |
| An ended roster slot: "Not in the ICU", no forecast, no vitals | `present===false` branches |
| A skipped event reads "no data", never 0; death never ranks a bed | `naq`, `vqn`, `RISKK` |
| Machine totals from the server; the saved total stays when use exceeds it; "N over" | `machSpare`, `machFree`, `machTotal`, `serverMachines` |
| Counts-only ward: machines in use come from the unit count | `inUse` |
| Close clears the chat and drops answers still on their way | `chatGen`, `asks` |

Browser tests: `backend/tests/test_page_browser.py` (run with `--with playwright`).

### 4.10 Smaller fixes

- `icutwin/scoring/metrics.py`: a non-finite estimate is left out of the metrics, not scored as zero risk.
- `app/rooms.py`: reads only the ward's rows of the CLIF tables; a record after the cut is never "recent history".

## 5. A safe order to port

1. 4.10, then 4.6 (winnower and logger first, then the three workflow lines).
2. 4.5, then re-extract the ward.
3. 4.4.
4. 4.8.
5. 4.2 and 4.3 together, with the `t7-twin.fz` line.
6. 4.9: take the page whole, then copy it to `app/static/index.html`.
7. Re-render `fuzzball/ready/` and run `fuzzball workflow validate` on each file.

After each step: `uv run --extra dev --extra model pytest -q` and `ruff check app tests scripts`.

## 6. Not yet proven

- **No workflow here has run on the cluster.** The rendered files with `--counts-only` and `--real-ward` have not been through `fuzzball workflow validate` since those edits. A test (`test_rendered_team_workflows_pass_only_arguments_their_scripts_accept`) shows each script accepts the flags it is given.
- `t7-forecast.fz` works out its display cut inside the job. A run that crosses 07:00 can pair the request's offset with the next morning. The lookahead workflow avoids this with `@CUT@`; the team's template does not yet.
- The lookahead workflows use a second volume, `demo-context`. The team's plan is one volume, `twin-store`.

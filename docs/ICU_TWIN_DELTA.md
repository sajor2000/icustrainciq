# What icustrainciq changed against ICU-Twin, and what to do about each change

Read this before the team's morning meeting on 2026-11-15. The demo runs from [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin). This repo (icustrainciq) holds work that ICU-Twin does not have. For each piece the team has to choose: port it before the demo, port it after, or keep it here only.

Section 1 is the decision table. Section 2 is what ICU-Twin has that this repo does not. The rest is detail for whoever does the porting.

Compared on 2026-11-15, every claim checked against both repos:

| Repo | Commit |
|---|---|
| ICU-Twin `main` | `fac343d` (merge of `55df710`, Dema's final board). No commit since |
| icustrainciq | `main` at `ef95989` (after PRs #16, #19, #20, #23) plus the final pull request ("Final: one-pager, docs, repo flow, UI refinements on Dema's page") |

**The rule for this morning: nothing in this repo is on the cluster.** The team ran `launch.sh` from ICU-Twin. Do not run `launch.sh` from this repo; its `ready/` files would overwrite the team's code on the shared volume.

## 1. Decisions

How to read the columns:

- **Risk to the running demo** is the risk of porting it now. *None*: it cannot change what the cluster does. *Low*: it changes code the demo runs, is covered by tests, and has a clear undo. *Needs live check*: it has never run on the cluster, so it must be watched once there before the demo relies on it.
- **Recommendation** is this repo's suggestion. The owner decides.

### 1.1 The page (owner: Dema)

One file. Details, pictures and undo for every row: [`UI_REVIEW_FOR_DEMA.md`](UI_REVIEW_FOR_DEMA.md).

| Change | Why | Risk to the running demo | Recommendation | How to port |
|---|---|---|---|---|
| Death hidden on bed tiles; one unit count in the alert line; Deaths card is a unit count only | Bug fixed (D13: death never marks a bed; ICU-Twin ranks the top beds with death in the list) | Low | Port before demo | The page file (below) |
| A skipped event reads "no data", never 0; unknown life support stays "unknown" | Bug fixed | Low | Port before demo | The page file |
| "See first" row: the three beds from Dema's top-beds rule | Feature (faster read at 07:00) | Low | Port before demo if Dema approves | The page file |
| "Update the unit" progress strip: Queued, Running on the GPU, Scoring, Done, "Updated HH:MM", failures in plain words | Feature | **Needs live check**: never watched against a real Fuzzball run | Port before demo only if one update is watched on the cluster first; otherwise after | The page file |
| Chat: clearer suggested questions; the chat opens above an open bed (it was under the pop-up and could not be clicked) | Polish and a bug fixed | Low | Port before demo | The page file |
| Escape closes one panel at a time; 44 px targets; quieter tiles; phone layout; header reads "ICU Lookahead" | Bug fixed and polish | Low | Port before demo | The page file |
| Machine totals read from the server; the saved total stays when use exceeds it ("1 over") | Bug fixed | Low on ICU-Twin's server (it has no totals, so the page keeps them on the device) | Port with the page | The page file |
| Standard flag lines 20 / 40 / 60 with "Reset to standard" (ICU-Twin: 25%, presets 50 / 25 / 10) | Decision D26, applied here (J.C. merged PR #24) | Low, but it changes which beds are flagged on stage: rehearse with it | Port with the page if Dema agrees; otherwise revert the six lines first | The page file; `UI_REVIEW_FOR_DEMA.md` change 14 |

**How to port the page:** `cp mockups/command-center.html <ICU-Twin>/app/static/index.html`, or review [`patches/icu-twin-page.patch`](patches/icu-twin-page.patch) first. It runs on ICU-Twin's `board.py` and `dispatcher.py` unchanged. It is all or nothing unless a change is undone here first (each entry in `UI_REVIEW_FOR_DEMA.md` says how).

### 1.2 The four small fixes before the demo

| Change | Area | Why | Risk to the running demo | Recommendation | Owner | How to port |
|---|---|---|---|---|---|---|
| Drop non-finite vital signs | backend | Bug fixed: one NaN or infinite reading makes `rooms.json` invalid JSON and the board shows no rooms | Low | **Port before demo** | Kaveri | [`patches/icu-twin-clif-now-vitals.patch`](patches/icu-twin-clif-now-vitals.patch) on `app/clif_now.py` (`rooms.py` needs nothing) |
| A skipped event reads "no data" | page | Bug fixed | Low | Port before demo | Dema | With the page |
| Death out of the risk ranking | page | Bug fixed (D13) | Low | Port before demo | Dema | With the page; or one line: `const RISKK = ["imv","vasopressor","crrt"];` |
| Demo script matches the final page | docs | Polish | None | Port before demo | J.C. | Copy `docs/submission/DEMO_SCRIPT.md` |

### 1.3 Backend, chat and workflows

| Change | Area | Why | Risk to the running demo | Recommendation | Owner | How to port |
|---|---|---|---|---|---|---|
| Chat grounded in one published snapshot (PR #16): `demo_context.py`, `evidence.py`, a bounded `chat_agent.py`, `board.py --context` | chat | Feature, and a bug fixed (a unit answer and a bed answer could come from different runs; the model could state a number the forecast did not contain) | **Needs live check** (548 changed lines in `chat_agent.py`; tested here on synthetic data only) | Port after demo, with `app/capacity.py` (section 5.8) | J.C. | Section 5.2 |
| The three `t7-lookahead-*.fz` workflows and the `demo-context` volume | workflows | Feature | **Needs live check: never run on the cluster**, and they use a second volume the team's plan does not have | Keep here only until after the demo | Kaveri | Section 5.2 |
| Real MIMIC-IV rooms only with `--real-ward` (D19); `t7-twin.fz` passes `@WARD_FLAG@` | backend, workflows | Bug fixed (privacy: the board served real rooms whenever the files carried them) | **Needs live check**: if `board.py` is ported without the `t7-twin.fz` line, the cohort board shows no rooms | Port after demo, both together | Kaveri | Section 5.3 |
| `--counts-only` on the ward winnow in `t7-fit`, `t7-ward`, `t7-forecast`, and the flag in `winnower.py` | workflows, scoring | Bug fixed (privacy: outcome rates of a 25-stay ward went into workflow logs) | **Needs live check**: the workflow line and the winnower must ship in one publish, or the job fails | Port after demo | Kaveri, Vaishvik | Section 5.6 |
| Unknown stays unknown (`on_now` null, `available: false`, no "0" for a missing score) | backend | Bug fixed | Low, but it changes `forecast.json` and `rooms.json` shapes the page reads; take the page with it | Port after demo | Kaveri | Section 5.4 |
| Features tied to the weights that made them (`provenance.py`, extractor sidecar, `apply_probes` refuses a mismatch) | scoring | Bug fixed (stale features could be scored with a refit probe) | **Needs live check**: features extracted before the change are refused until re-extracted | Port after demo | Vaishvik | Section 5.5 |
| A non-finite score is left out of the metrics, not counted as zero risk | scoring | Bug fixed | None for the demo (metrics only) | Port after demo | Vaishvik | Section 5.10 |
| Staffing and capacity: machine totals, 1:1 and 1:2 nursing, RT 1:6 (D23), `get_staffing` in the chat | backend, chat | Feature | Low (new keys; the page draws machine capacity only) | Port after demo | Kaveri, J.C. | Section 5.8 |
| Dispatcher: `@CUT@`, `# needs: ward-ids`, "ICU team" role | backend | Feature and small fixes | Low | Port after demo | Kaveri | Section 5.7 |
| `GET /api/context` answers 200 when no context is configured | backend | Polish (no failed request in the browser console) | None | Port after demo, with the chat grounding | J.C. | One line in `board.py` |
| `t7-code.fz` and `make_ready.sh` publish `sajor2000/icustrainciq` | workflows | This repo's own pin | Would replace the team's code on the volume | **Keep here only. Never port** | Kaveri | Section 5.1 |
| CodeRabbit review fixes (PRs #14, #16, #19, #20, #23) | all | Bugs fixed | Varies; each is one of the rows above or docs only | As the row it belongs to | each owner | [`WHAT_WE_FIXED.md`](WHAT_WE_FIXED.md); ready-to-paste patches for teammates' code in [`UPSTREAM_REVIEW_NOTES.md`](UPSTREAM_REVIEW_NOTES.md) (written before PR #16 merged: check each against ICU-Twin first). No Greptile review is recorded in this repo |

### 1.4 The rescued branch `save/backend-review-fixes`

Nine commits that are on GitHub (`origin/save/backend-review-fixes`) and on neither `main` nor ICU-Twin.

| Change | Area | Why | Risk to the running demo | Recommendation | Owner | How to port |
|---|---|---|---|---|---|---|
| The 24 h outcome window starts at the cut (`7e001f3`) | scoring | Bug fixed | n/a: **already on `main` and in ICU-Twin** in the team's own form (`winnower.py`, "counted from the cut itself") | Nothing to do | Vaishvik | |
| Probes pair features with labels by stay id (`e370067`) | scoring | Bug fixed | n/a: the join by `hospitalization_id` is on `main`; the weights check is section 5.5 | Nothing more to do | Vaishvik | |
| End-to-end smoke test with no network, GPU or model (`8826826`, `test_smoke_end_to_end.py`) | backend tests | Feature | None (a test) | Port after demo, rebased: it was written against an older `board.py` | J.C. | Commit `8826826` |
| Degraded mode: `t7-twin` without Nemotron, the chat answers one plain line (`7f87365`) | workflows, chat | Feature (a fallback if the chat model will not load) | **Needs live check**: never run | Keep on the branch; decide after the demo | Kaveri | Commit `7f87365` |
| Capacity POST sends totals only (`5dd72ca`); README and figures commits | page, docs | | n/a: superseded by what is on `main` | Nothing to do | | |

### 1.5 Docs, figures and the submission (owner: J.C.)

None of these can affect the cluster.

| Change | Why | Risk | Recommendation | How to port |
|---|---|---|---|---|
| `docs/RESULTS.md`: held-out results per task, with ranges, and the chart `results-auroc.png` drawn from that table | Feature. ICU-Twin has no results page | None | Port before demo (one file and one image), or link to it here | Copy `docs/RESULTS.md`, `docs/diagrams/results-auroc.*` |
| The one-pager (`docs/submission/one-sheet.*`) and the demo script | Polish: five team members, final page screenshots, AUROC 0.77–0.93, "ran end to end… with one launch script" | None | Print from here. Copy the demo script to ICU-Twin (row 1.2) | `docs/submission/` |
| The Pages site (`docs/index.html`, served at sajor2000.github.io/icustrainciq) | Feature | None | Keep here only | |
| Eight figures written by one script (`docs/diagrams/make_figures.py`) in the board's colours, with night copies | Polish. ICU-Twin has thirteen older figures of its own | None | Keep here only | |
| README, HANDOFF, ARCHITECTURE, FRONTEND_SPEC, DESIGN, DECISIONS D24 to D27 | Docs follow the final code and page | None | Keep here only; ICU-Twin keeps its own | |
| Old plans moved to `docs/archive/` | Repo flow | None | Keep here only | |

## 2. What ICU-Twin has that this repo does not

Checked with `git ls-tree` at `fac343d`. This repo does not train the model and cannot stand in for ICU-Twin.

| In ICU-Twin only | What it is |
|---|---|
| `workflows/job_1_data_move` to `job_4_probe` (with `job_3_1_package`) | Data move, tokenizing, training, packaging and the probe fit. The model and the probe on the cluster come from these |
| `fuzzball/t7-build.fz`, `scripts/train_full.sh`, `tokenize_full.sh`, `extract_split.py`, `examples/train_fuzzball.yaml`, `train_fuzzball_continue.yaml` | Training and tokenizing runs |
| `scripts/sglang_parity.py`, `sglang_rank.py`, `sglang_smoke.py`, `reach_bench.py`, `reach_smoke_timing.py` | Benchmarks |
| `tests/test_repo_hygiene.py` | Its own repo check |
| `docs/TEAM_START.md`, `SETUP_GUIDE.md`, `FUZZBALL_CLI.md`, `FUZZBALL_PLAN.md`, `FUZZBALL_RUNS.md`, `CHECKS.md`, `QUESTIONS.md`, `SLIDES.md`, `ACKNOWLEDGMENTS.md`, and the folders `docs/plans`, `docs/superpowers`, `docs/mockups` | Team start guides, cluster notes, the slides outline, acknowledgments, pre-event plans |
| Thirteen figures under `docs/diagrams/` (backend, deployment, sequence, training-and-science and others) | Its own figures |
| `.claude/skills/` (fuzzball-ops, scaling-bench, team-git, twin-demo), `.mcp.json`, `.cursor/`, `.codex/`, `.python-version` | Agent and tool setup |

Everything that runs the board is here: `app/`, `fuzzball/`, `icutwin/`, `scripts/`, `tests/` and `requirements/` were synced at ICU-Twin `360cb31` (PR #19), and ICU-Twin's only later commits are the page (`55df710`, ported) and docs (`457134e`).

## 3. How the two repos line up

| ICU-Twin | icustrainciq |
|---|---|
| `app/`, `fuzzball/`, `icutwin/`, `scripts/`, `tests/`, `requirements/` | the same folders under `backend/` |
| `app/static/index.html` | `backend/app/static/index.html`, a byte copy of `mockups/command-center.html` (edit the mockup, then copy) |
| `docs/` | split: board and decisions in `docs/`, cluster and contract in `backend/docs/` |
| `workflows/job_1` to `job_4` (training, probe) | not here: training stays in ICU-Twin |

To port a file, apply its diff with the `backend/` prefix removed. Run this repo's tests for that area first, so you know what the change is meant to do.

## 4. Files that differ

Lines that differ (`diff | grep -c '^[<>]'`), ICU-Twin `fac343d` against this repo with the final pull request:

| File | Lines | Section |
|---|---|---|
| `app/chat_agent.py` | 548 | 5.2, 5.3 |
| `app/static/index.html` | 478 | 5.9 |
| `app/aggregate.py` | 363 | 5.4, 5.8 |
| `app/board.py` | 264 | 5.2, 5.3, 5.8 |
| `scripts/run_cohort.py` | 210 | 5.2, 5.6 |
| `app/clif_now.py` | 87 | 5.4, 5.8 |
| `icutwin/scoring/rep_based.py` | 73 | 5.5 |
| `app/dispatcher.py` | 70 | 5.7 |
| `app/rooms.py` | 67 | 5.4, 5.8 |
| `app/stage_ward.py` | 26 | 5.2 |
| `icutwin/scoring/extractor.py` | 24 | 5.5 |
| `icutwin/scoring/winnower.py` | 24 | 5.6 |
| `fuzzball/t7-code.fz` | 22 | 5.1 |
| `scripts/render_fz.py` | 13 | 5.7 |
| `icutwin/scoring/metrics.py` | 12 | 5.10 |
| `icutwin/tokenizer/helpers.py` | 8 | 5.6 |
| `fuzzball/t7-twin.fz` | 7 | 5.3 |
| `fuzzball/t7-fit.fz` | 6 | 5.6 |
| `fuzzball/t7-forecast.fz` | 4 | 5.6 |
| `scripts/make_ready.sh` | 4 | 5.1 |
| `fuzzball/t7-ward.fz` | 2 | 5.6 |

Eleven test files differ with them (`test_chat_agent.py`, `test_dispatcher.py`, `test_board.py`, `test_lookahead.py`, `test_clif_now.py`, `test_rep_probes.py`, `test_winnower.py`, `test_cohort.py`, `test_metrics.py`, `test_rep_based.py`, `test_names.py`).

Files only here: `app/capacity.py`, `app/demo_context.py`, `app/evidence.py`, `icutwin/scoring/provenance.py`, `fuzzball/t7-lookahead-prepare.fz`, `t7-lookahead-chat.fz`, `t7-lookahead-forecast.fz`, `scripts/prepare_lookahead_cohort.py`, `scripts/package_lookahead_demo.py`, and the tests `test_capacity.py`, `test_staffing.py`, `test_demo_context.py`, `test_demo_chat_app.py`, `test_demo_package.py`, `test_page_browser.py`.

`fuzzball/ready/` differs in every file: it is rendered from the templates for this repo's pinned commit (`617edc0`, older than the templates; it must be re-rendered after the final pull request merges and before any launch from this repo). Never copy it; run `scripts/make_ready.sh` in your own repo.

## 5. The changes, by topic

Each topic says what changed, why, and what to take with it.

### 5.1 Which repo the cluster publishes

`t7-code.fz` and `make_ready.sh` fetch `sajor2000/icustrainciq` and publish its `backend/` folder to `/store/code`. **Do not port.** ICU-Twin publishes its own repo root.

### 5.2 Chat grounded in one published snapshot

**What.** The chat answers from one validated file, `context.json`: the same 25 rooms, the Now side and the forecast, under one `snapshot_id` and `cohort_id`.

- `app/demo_context.py` builds, validates and atomically writes the snapshot. It refuses stay ids, source dates and mixed snapshots. A roster stay that has left the ICU keeps its room slot with `present: false`.
- `app/evidence.py` writes every number in a chat answer from the tool results. The model picks tools; its own prose is never the source of a number.
- `app/chat_agent.py` has closed tool schemas, a cap of 8 tool calls and 12,000 characters, a request deadline, and a fallback when the model is down or rejects tools.
- `app/board.py` adds `--context` (serve `/api/context`; `/api/forecast` and `/api/rooms` become projections of it) and `--require-real-data`.
- `scripts/run_cohort.py` adds `--context-out`, `--tokenized-output`, `--no-extract`, `--cut-time`, `--names`, `--unit-name`. `app/stage_ward.py` accepts a given room map.
- The three `t7-lookahead-*.fz` workflows run this path on a separate restricted volume, `demo-context`.

**Why.** A unit answer and a room answer could come from different runs. The model could also state a number the forecast did not contain.

**Take with it.** `demo_context.py`, `evidence.py`, `chat_agent.py`, `board.py` **and `capacity.py`** together, with `test_demo_context.py`, `test_demo_chat_app.py`, `test_chat_agent.py`, `test_capacity.py`. `chat_agent.py` and `board.py` import `capacity` unconditionally and ICU-Twin does not have that file, so without it the board does not start (`ModuleNotFoundError`). Section 5.8 (capacity and staffing) is therefore a prerequisite of this bundle, not a later step. Docs: `backend/docs/CHAT_AGENT.md`, `backend/docs/LOOKAHEAD_DEMO.md`, `CHATBOT_HANDOFF.md`.

**Works without it.** The board and chat still run from plain `forecast.json` and `rooms.json` when `--context` is not given.

### 5.3 Real MIMIC-IV rooms only in real-ward mode

**What.** `app/board.py` has `--real-ward`. Without it, a ward whose `ward.source` is `"mimic-iv"` is served counts-only: `/api/rooms` returns `{"rooms": [], "counts_only": true}`, `check_first` is empty, and the chat's `get_room` refuses. In real-ward mode the chat sends a room's fields to Nemotron only for a room the user asked about, with no clock fields.

**Why.** Decision D19 (`docs/DECISIONS.md`) allows real rooms only in an explicit mode. The board used to serve them whenever the files carried them.

**Take with it.** One line in `t7-twin.fz`: the board command ends with `@WARD_FLAG@`, which renders `--real-ward` for the cohort and nothing for the open demo. **If you port the `board.py` change without this line, the cohort board shows no rooms and no room chat.**

### 5.4 Unknown stays unknown

**What.** In `aggregate.py`, `rooms.py` and `clif_now.py`:

- A support whose current state raw CLIF cannot tell is `null` in `on_now`, never `false`. Unit counts add `now_known_*` and `now_unknown_*`.
- A stay with no score for a support it could start makes that unit count unavailable (`available: false`, `null` numbers), not a count that takes it as 0. The room's `any_life_support` is `null` and its `level` is `"unavailable"`.
- A patient already on one support does not blank the combined new-patient count.
- A support started and stopped before the cut has no score by the probe's rule. That is "not a new start", not missing data.
- A stay back in the ICU exactly at its cut is present (`in <= cut < out`).

**Why.** A missing observation was being shown as "off" or as zero risk.

**Take with it.** `test_lookahead.py`, `test_cohort.py`, `test_clif_now.py`, and the `forecast.json` and `rooms.json` sections of `backend/docs/CONTRACT.md`.

### 5.5 Which weights made the features

**What.** `icutwin/scoring/provenance.py` (stdlib only) holds `weights_digest` and a sidecar for each features file, `features-<split>-<model>.meta.json`. `extractor.py` writes it, including after `--merge` of shards. `rep_based.apply_probes` refuses features made with other weights, or with none recorded.

**Why.** The probe file is tied to the weights and the cut columns tie features to labels, but nothing tied features to weights. Stale features could be scored with a refit probe.

**Take with it.** All three files together. **Features extracted before this change are refused: run `icutwin-extract` again.** Training-side fitting is not checked, so `job_4_probe` is unaffected.

### 5.6 Logs hold counts only

**What.**

- `winnower.py` has `--counts-only`: it logs the number of stays per split and no outcome rates. ICU-Twin `fac343d` has no such flag.
- `t7-fit.fz`, `t7-ward.fz` and `t7-forecast.fz` pass it on the ward winnow line. The training winnow keeps its rates.
- `icutwin/tokenizer/helpers.py`: `Logger.setLevel` clears the level cache. The logger is created directly, so `setLevel("WARNING")` after the first message did nothing.
- `scripts/run_cohort.py` winnows counts-only.

**Why.** For a 25-stay ward an outcome rate is a clinical value about a few patients.

**Take with it.** The winnower change and the three workflow lines must ship in the same `t7-code` publish. A workflow that passes `--counts-only` to an older winnower fails at that job.

### 5.7 Dispatcher

- `@CUT@` token and `replay_cut()`: the replay cut is fixed when a run is dispatched and passed to the job. Only `t7-lookahead-forecast.fz` uses it. `scripts/render_fz.py` gains `--cut`.
- A template whose header has `# needs: ward-ids` is refused when the dispatcher was started without `--ward-ids`.
- Run names are `t7-lookahead-forecast-unit-MMDD-HHMM` and `-roomN-`. The busy check still matches `t7-forecast`.
- `"ICU team"` is an accepted role.

### 5.8 Capacity and staffing

**What.** `app/capacity.py` stores machine totals (`vents_total`, `crrt_total`) and derives free machines on read; nothing derived is stored. `aggregate.py` adds `machines`, `staffing_now` and `staffing_next_24h` to `forecast.json`. `clif_now.py` counts vasoactive infusions for the 1:1 nursing rule (D23). `POST /api/capacity` accepts the totals. The chat gains `get_staffing`.

`GET /api/context` without a context answers `200 {"context_mode": false}` (it was 404), so the page's probe leaves no failed request in the console.

**Take with it.** `test_capacity.py`, `test_staffing.py`, and "capacity.json and /api/capacity" and "staffing" in `backend/docs/CONTRACT.md`. The page does not show a staffing card (D25); the numbers stay in the API.

### 5.9 The page, on top of `55df710`

Dema's design is unchanged. Two layers sit on it. The first was on `main` before the final pull request:

| Addition | Where to look in the script |
|---|---|
| Reads `/api/context` first, falls back to `/api/forecast` and `/api/rooms`; refuses mixed snapshots | `loadAll` |
| Unknown current support is shown as unknown, never "No life support" | `unknownList`, `anyNew`, `noScore`, `noEst` |
| An ended roster slot: "Not in the ICU", no forecast, no vitals | `present===false` branches |
| A skipped event reads "no data", never 0; death never ranks a bed | `naq`, `vqn`, `RISKK` |
| Machine totals from the server; the saved total stays when use exceeds it; "N over" | `machSpare`, `machFree`, `machTotal`, `serverMachines` |
| Counts-only ward: machines in use come from the unit count | `inUse` |
| Close clears the chat and drops answers still on their way | `chatGen`, `asks` |

The second layer is the final pull request's refinements (D27): death hidden on tiles, the See first row, the update progress strip, the chat questions, the bug fixes. Each has its own entry, pictures and undo in [`UI_REVIEW_FOR_DEMA.md`](UI_REVIEW_FOR_DEMA.md).

Browser tests: `backend/tests/test_page_browser.py` (`uv run --extra dev --extra model --with playwright python -m pytest -q tests/test_page_browser.py`).

### 5.10 Smaller fixes

- `icutwin/scoring/metrics.py`: a non-finite estimate is left out of the metrics, not scored as zero risk.
- `app/rooms.py`: reads only the ward's rows of the CLIF tables; a record after the cut is never "recent history".

## 6. A safe order to port, after the demo

Before the demo, only sections 1.1 and 1.2. Afterwards:

1. 5.10, then 5.6 (winnower and logger first, then the three workflow lines).
2. 5.5, then re-extract the ward.
3. 5.4.
4. 5.8 (it brings `app/capacity.py`, which 5.2 imports).
5. 5.2 and 5.3 together, with the `t7-twin.fz` line. Never before 5.8.
6. 5.9: take the page whole, then copy it to `app/static/index.html`.
7. Re-render `fuzzball/ready/` and run `fuzzball workflow validate` on each file.

After each step: `uv run --extra dev --extra model pytest -q` and `ruff check app tests scripts`.

## 7. Not yet proven

- **No workflow file as rendered from this repo has run on the cluster.** The team's run on 2026-11-14 used ICU-Twin's files. The files here with `--counts-only` and `--real-ward` have not been through `fuzzball workflow validate` since those edits. A test (`test_rendered_team_workflows_pass_only_arguments_their_scripts_accept`) shows each script accepts the flags it is given.
- **The update progress strip has not been watched against a real run.** It reads `running.state` and `stuck` from `/api/runs`, which ICU-Twin's dispatcher already sends.
- **The `t7-fit` fallback alone does not make a forecast run.** `t7-forecast` requires job 4's `/data/tokenized_output/train_for_inference.parquet`; `t7-fit` writes its own under `/store/train` (`backend/docs/LIVE_DEMO.md` section 9.1). This is true in ICU-Twin too.
- `t7-forecast.fz` works out its display cut inside the job. A run that crosses 07:00 can pair the request's offset with the next morning. The lookahead workflow avoids this with `@CUT@`; the team's template does not yet.
- The lookahead workflows use a second volume, `demo-context`. The team's plan is one volume, `twin-store`.

# First run on real Fuzzball: test plan

> **Updated 2026-11-14 (storage change).** Paths in this file were brought in line with the workflow files; where an older paragraph still disagrees, `FUZZBALL_VALIDATION.md` and `../../HANDOFF.md` ("To run it on the cluster") win.
> - One volume to create, `twin-store`, not three: `clif_work` and `tooling` are gone. Packages are at `/store/py`, the stage ward at `/store/stage`, training features at `/store/train`.
> - `mimic_clif` is mounted at `/data` and only read: the model is `/data/model_output/final`, the training tokens `/data/tokenized_output`, the cohort `/data/dashboard_data`.
> - The cohort is **already on the cluster**; there is no copy step.
> - Code is published by `t7-code` from this repo (`backend/`), not by `t7-build` or `t7-smoke`. There is no `t7-build` in this repo: read it as "training" (ICU-Twin repo, workflows `job-3-*`).
> - Do not render by hand or with `sed`: start the files in `fuzzball/ready/` (`scripts/make_ready.sh`).

For the team, to run **only after training (`t7-build`) has finished**. Written 2026-11-14 from the files in this repo and the Fuzzball 4.3 documentation. **Nothing in this plan has been run on the cluster.** No `fuzzball` command and no MCP call was made while writing it, because the model was training.

Read with: `LIVE_DEMO.md` (runbook), `COMPUTE_PLAN.md` (who gets which GPU), `FUZZBALL_43_REVIEW.md` (the docs review; its finding numbers F1 to F14 and U1 to U14 are used below).

Command syntax was checked against these pages, not memory:

| Command | Page (prefix `https://docs.ciq.com/fuzzball/4.3/`) |
|---|---|
| `fuzzball workflow validate <file>` | `quick-start/uqs-initial-workflow` |
| `fuzzball workflow start <file>`, `fuzzball workflow stop <id>` | `quick-start/uqs-starting-and-stopping-workflows` |
| `fuzzball workflow describe <id>`; status words Pending, Started, Finished, Errored, Canceled | `quick-start/uqs-interacting-with-workflows/uqs-workflow-status` |
| `fuzzball workflow list --order-by -created`, `fuzzball workflow log <id> <job> -n 50` (add `-f` to follow) | `quick-start/uqs-interacting-with-workflows/uqs-retrieve-logs` |
| `fuzzball workflow endpoints <id> [service] [endpoint]`, `fuzzball workflow events <id>` | `advanced-features/workflow-endpoints` |
| `fuzzball workflow exec <id> <job> <command>` (running jobs only) | `advanced-features/shell-exec` |
| `exclusive`: "If true, job gets exclusive node access." | `appendices/workflow-syntax` |
| volume ingress: `s3://`, `https://`, `hf://`, inline `file://`; no upload from a laptop | `volumes/vols-operations/vols-ops-ingress` |

One flag is **not** in the 4.3 pages: `--name` on `workflow start`. The dispatcher and every command below use it. Check it first: `fuzzball workflow start --help` (U2).

## 0. The first live check

**With `t7-twin` up, does a unit forecast leave Pending within two scheduler intervals?** (The default interval is 60 s, so about 2 minutes. The real interval here is unknown.)

Why first: until today the forecast `extract` and Nemotron both set `exclusive: true`. In Fuzzball 4.3 that reserves the whole node, so with Nemotron alone on one node and the board and dispatcher on the other, the forecast could never be placed (`COMPUTE_PLAN.md` finding 1, review F1). The files no longer set it on `extract`. This was predicted from the docs and fixed in the files; only the scheduler can confirm.

How (step 5 below): press "Update the unit", then

```bash
fuzzball workflow list --order-by -created          # the newest t7-forecast-MMDD-HHMM
fuzzball workflow describe <forecast-id>            # precheck Finished, extract Started within about 2 minutes
```

If `extract` is still Pending after 2 minutes:

1. `fuzzball workflow why <forecast-id> <allocation-id>` and `fuzzball queue show --mine` (`scheduler-admin/queue-observability`). Expect `INSUFFICIENT_RESOURCES` and what holds the node.
2. Do nothing else for 5 minutes: the dispatcher stops a forecast that is still pending after 5 minutes and says so in `/api/runs` (`stuck`).
3. Degraded option, `COMPUTE_PLAN.md` mode F: board and forecasts, no chat. Stop `t7-twin`, start `fuzzball/ready/t7-twin-nochat.fz` under the same name (`fuzzball workflow validate fuzzball/ready/t7-twin-nochat.fz && fuzzball workflow start fuzzball/ready/t7-twin-nochat.fz --name t7-twin`), update the unit. It is `t7-twin` without the `nemotron` service: the same board and dispatcher, no GPU held. The chat answers "Chat is not available right now."; everything else works. Never run it beside `t7-twin` (two dispatchers).
4. Do not "fix" it by adding `exclusive` anywhere.

## 1. Before anything

| Check | Command | Pass |
|---|---|---|
| Training has ended | `fuzzball workflow list --order-by -created` | `t7-build` Finished. No other `t7-*` workflow Pending or Started |
| Our two nodes | `fuzzball node list` | both healthy, 20 cores, about 128 GB, `nvidia.com/gpu: 1` each |
| Volumes | `fuzzball volume list` | `mimic_clif`, `hfcache` and `twin-store` exist (`twin-store` is the one to create: `FUZZBALL_VALIDATION.md`) |
| Model and code published | job log of `t7-code`; `FUZZBALL_VALIDATION.md` for the model | `t7-code` prints the commit and the file count for `/store/code` and the size of `/store/py`; the model is `/data/model_output/final` |
| The code on `twin-store` is this commit | whoever publishes code | `/store/code/fuzzball/t7-ward.fz` and `/store/code/app/ward_check.py` exist (they are new) |
| `--name` exists | `fuzzball workflow start --help` | the flag is listed |
| The cohort is on the volume (only for the final cohort) | done 2026-11-14 | `/data/dashboard_data/` (volume `mimic_clif`) holds the tables, the id file and `name.parquet`; `t7-ward` job `load` checks it |
| Local tests | `cd backend && uv run --extra dev --extra model pytest -q` | all pass; they cover every Fuzzfile's rendering, YAML, images, job order |

**How `/store/code` gets updated:** `t7-code` (`fuzzball/ready/t7-code.fz`) publishes `backend/` of one pinned commit of this repo and the hash-locked packages. Run it first and after every merge (`scripts/make_ready.sh`, then start it): every workflow below runs the code on the volume, not your checkout.

## 2. Fill the tokens

Fuzzball 4.3 Fuzzfiles have no parameters, so each file is a template. One tool fills every token and refuses a file with a token left:

```bash
cd backend
python scripts/render_fz.py --check fuzzball/*.fz        # which tokens each file has
```

| File | Tokens | Render |
|---|---|---|
| `t7-code.fz` | `@CODE_REF@`, `@CODE_SHA256@` | `scripts/make_ready.sh` writes all of these to `fuzzball/ready/`; start those files |
| `t7-fit.fz` | `@CLIF_DIR@`, `@WARD_IDS@` | `fuzzball/ready/t7-fit.fz` (final cohort); `python scripts/render_fz.py fuzzball/t7-fit.fz -o /tmp/t7-fit.fz` for the open demo ward |
| `t7-ward.fz` | `@CLIF_DIR@`, `@WARD_IDS@`, `@NAMES@` | `fuzzball/ready/t7-ward.fz` |
| `t7-twin.fz` | `@DISPATCH_WARD@` | `fuzzball/ready/t7-twin.fz` (the dispatcher line already carries the cohort) |
| `t7-forecast.fz` | `@SCOPE@`, `@ROOM@`, `@HOURS@`, `@WARD_FLAG@`, `@CLIF_DIR@`, `@NAMES@` | the dispatcher renders it; by hand only as a fallback (`LIVE_DEMO.md` 9.5) |

Code ref and checksum (only `t7-smoke` and the ICU-Twin `t7-build` need them):

```bash
REF=<40-hex commit sha on GitHub>
SHA=$(curl -sL https://codeload.github.com/vaishvikc/ICU-Twin/tar.gz/$REF | sha256sum | cut -d' ' -f1)
```

## 3. The workflows, in order

For every workflow: validate the **rendered** file, start it with `--name`, note the id it prints (a bare id, or `Workflow "<id>" started.`), then watch.

```bash
fuzzball workflow validate /tmp/<file>.fz
fuzzball workflow start /tmp/<file>.fz --name <name>
fuzzball workflow describe <id>                 # job states
fuzzball workflow log <id> <job> -n 50          # add -f to follow a running job
fuzzball workflow events <id>                   # scheduling events
fuzzball workflow stop <id>                     # stop it
```

Logs print counts and file names only. If a log ever shows a patient row, an id or a name, stop the workflow and tell the team.

### Step 1: `t7-smoke` (only if the stack was never checked on these nodes)

Skip it when `t7-build` has already published a model: its `seed` job then does nothing. It needs one GPU and no `t7-twin`.

| | |
|---|---|
| Start | `fuzzball workflow start /tmp/t7-smoke.fz --name t7-smoke` |
| Jobs | `prefetch` and `setup` (CPU, together), then `train-demo` (GPU), `sglang` (GPU), `seed` (CPU) |
| Success | all Finished; `prefetch` log ends with the size of `/cache/hf`; `seed` log says "seeded" or "a model is already published; not seeding" |
| Fails early | "CODE_REF / CODE_SHA256 not set" or "code tarball does not match": render again with the right values |

### Step 2: `t7-fit` (once per model)

Run it **before** `t7-twin` is up: its `stage` and `extract` jobs together ask for 24 cores.

| | |
|---|---|
| Start | `fuzzball workflow start /tmp/t7-fit.fz --name t7-fit` |
| Jobs | `stage` (CPU) and `extract` (one GPU) side by side, then `fit` (CPU) |
| Success | all Finished. `stage` log: counts, "vocab: identical", "stage rooms: 25". `extract` log: a count of `features-*.parquet`. `fit` log: "probes saved: N" |
| On the volumes | `/store/probes/mdl-icutwin/manifest.json`; `/store/stage/stage_ward.csv`; `/store/stage/tokenized_output/` |
| If `cmp` fails in `stage` | the stage vocabulary differs from the training one: the code on `/store/code` is not the code that tokenized the training data. Stop |

### Step 3: `t7-ward` (the final cohort; skip to keep the open demo ward)

CPU only. Start it only when no forecast is running: it replaces the tokens a forecast reads. The dispatcher refuses updates while a `t7-ward` is active.

```bash
fuzzball workflow validate fuzzball/ready/t7-ward.fz && fuzzball workflow start fuzzball/ready/t7-ward.fz --name t7-ward
```

| | |
|---|---|
| Jobs | `load`, then `tokenize` |
| `load` success | one JSON line: `"ward_ids": 25`, `"ward": "mimic-iv"`, `"named": 25`, `"unnamed": 0`, `"missing_optional": []`, and `"ignored"` listing the tables no token is made from (`ecmo_mcs`, `input`, `output`, `microbiology_culture`, `patient_assessments_raw_gcs`, `patient_procedures`, `position`). Then "parquet files: 21" |
| `load` fails | "no ward CLIF folder": `/data/dashboard_data` is not there (is `mimic_clif` the volume?). "required CLIF table(s) not found": the folder is incomplete. "holds N stays, expected 25": wrong id file |
| `tokenize` success | counts from the tokenizer, "vocab: identical", "stage rooms: 25" |
| On the volume | `/store/stage/stage_ward.csv` (25 rooms), `/store/stage/tokenized_output/` replaced whole |
| Compare with the laptop | the laptop run (`README.md`) and this job use the same seed, so the room map is the same. At the 24 h cut the laptop shows 25 rooms present |

### Step 4: `t7-twin`

For the cohort use `fuzzball/ready/t7-twin.fz`: its dispatcher line already ends with `--real-ward --clif-dir /data/dashboard_data --names /data/dashboard_data/name.parquet`. No hand edit.

```bash
fuzzball workflow validate fuzzball/t7-twin.fz
fuzzball workflow start fuzzball/t7-twin.fz --name t7-twin
fuzzball workflow describe <twin-id>                    # nemotron, board, dispatcher Started
fuzzball workflow log <twin-id> dispatcher -n 50        # CLI downloaded, its sha256, no DISPATCHER UNAVAILABLE
fuzzball workflow endpoints <twin-id> board web         # the board's URL
```

| | |
|---|---|
| Success | three services Started. Nemotron takes minutes (probe budget about 21 minutes). The board answers before Nemotron is ready |
| Dispatcher log | a WARNING with the CLI's sha256 the first time: put it in `FB_CLI_SHA256` in `t7-twin.fz` for the next start |
| `DISPATCHER UNAVAILABLE: ...` in the log | the service is up but starts nothing; the board says "dispatcher unavailable". Fix `FB_UI_URL` or the checksum, restart `t7-twin` |
| Placement | Nemotron on one node; board and dispatcher both on the other (`describe`). If they landed on different nodes Nemotron stays Pending: stop and start again |
| Only one node (one GPU) is up | start `fuzzball/ready/t7-twin-nochat.fz` as `--name t7-twin` instead: two services Started (`board`, `dispatcher`), no Nemotron, the GPU stays free for forecasts. Go back to `t7-twin.fz` when the second node returns (stop one, start the other) |
| The URL | `endpoints` prints it; a team7 member signed in to the Web UI can also use the Connect button on the workflow page. The endpoint is `scope: group`: other callers need a token (`fuzzball workflow endpoints generate-token <endpoint-id>`) |

### Step 5: the first unit forecast

Press "Update the unit" on the board (or wait for 07:00). **This is the first live check, section 0.**

```bash
fuzzball workflow list --order-by -created              # t7-forecast-MMDD-HHMM
fuzzball workflow describe <forecast-id>                # precheck, extract, score
fuzzball workflow log <forecast-id> score -n 50
```

| | |
|---|---|
| Success | `precheck` "prechecks ok"; `extract` prints a count of feature files; `score` prints two JSON lines of counts and `made_at ... rows 5` |
| On `twin-store` | `/store/rooms.json`, then `/store/forecast.json` (written last), `/store/runs.jsonl` with one new line, `/store/rendered/t7-forecast-*.fz` |
| `precheck` fails | "run t7-fit first", "run t7-build first", or "no ward CLIF folder at ...": the step named has not run, or `--clif-dir` is wrong |
| Write down | seconds waiting before `extract`, seconds in `extract`, total. Nothing has been timed on these nodes |

### Step 6: one room

Open a room, press "Update this room" (needs the unit run first). A new `t7-forecast-roomN-MMDD-HHMM` appears. Only that room's `updated_at` changes; `forecast.json` is untouched. Pressing again within 20 minutes is refused in plain words.

## 4. On the board

| Check | Pass |
|---|---|
| Rooms | 25 tiles, rooms 1 to 25 (`GET /api/rooms`: 25 entries, `dropped` 0 at the morning cut) |
| Ward label | "Real MIMIC-IV · local only" for the cohort; "Open MIMIC-IV Demo" otherwise |
| Now side | the counts on life support match the laptop run of the same ward at the same clock (`scripts/run_cohort.py` prints `now_by`) |
| Next 24 h | every room has a level and percentages; unit counts have ranges; `forecast_state` is `ready` (`GET /api/forecast`) |
| Names | each tile shows its made-up name; `rooms.json` has `"names": "fictional"` |
| Dates | no year of 2100 or later anywhere on the page or in the two files |
| Chat | "How is room 12?" answers with frequencies; "update room 12" starts a run only on that ask |
| Runs | `GET /api/runs`: `next_scheduled` is tomorrow 07:00, `stuck` is null, `ward` is `real` |

## 5. Stop, roll back, clean up

| What | How |
|---|---|
| Stop one workflow | `fuzzball workflow stop <id>` (asynchronous: it reads Started for a moment, then Canceled) |
| A forecast that hangs | the dispatcher stops it after 5 minutes pending or 45 minutes in all; by hand: `workflow stop` |
| Back to the open demo ward | render `t7-ward.fz` with no options, start it, remove `--real-ward --clif-dir ... --names ...` from the dispatcher line, restart `t7-twin`, update the unit |
| Take the cohort off the cluster | delete `/data/dashboard_data/`, `/store/stage/tokenized_output/`, `/store/stage/stage_ward.csv`, then `/store/rooms.json` and `/store/forecast.json` (they hold the cohort's room entries), from a one-line CPU job or `fuzzball workflow exec` in a running job that mounts both volumes. Then restage the open demo ward |
| Rendered copies | `/store/rendered/` keeps the last 30; `/tmp/*.fz` on the laptop can go |
| Old probes | `t7-fit` overwrites `/store/probes/mdl-icutwin`; probes are tied to the weights by checksum, so a new model needs a new `t7-fit` |
| Never | `fuzzball workflow stop` on `t7-build` while it trains; start a forecast by hand while `t7-twin` is up (only the dispatcher starts them) |

## 6. Never run on the cluster yet

Nobody should assume any of this was tested. As of 2026-11-14:

- `t7-ward.fz`: new today. Never validated, never started.
- `t7-fit.fz`, `t7-forecast.fz`, `t7-smoke.fz`, `t7-twin.fz` **as they are now**: each changed today (ward tokens, no `exclusive`, sizes, the dispatcher bootstrap, the board loop). Whatever ran before was an older file. `fuzzball workflow validate` has not been run on any of today's files.
- `scripts/render_fz.py`, `app/ward_check.py`, `app/fake_names.py`, `stage_ward.py --ward-ids`: run on a laptop and in tests only.
- The dispatcher's bounded wait (`workflow stop` after 5 minutes pending) and its degraded `--unavailable` mode: tested against a fake CLI only.
- The cohort with a real model: `scripts/run_cohort.py --model --probes` is covered by a test with synthetic features and synthetic probes. No real weights have scored these 25 stays, on a laptop or on the cluster.
- The cohort is on `mimic_clif:/dashboard_data/` (done 2026-11-14); `t7-ward` job `load` has not yet checked it.
- A unit or room forecast for a real ward (`--real-ward`) on the cluster.

## 7. Live checks nobody could do from the docs

From the review (U1 to U14) and the compute plan. Do them in this order during the first run and write the answers into `CLUSTER_FACTS.md`.

| # | Check | How |
|---|---|---|
| 1 | Does a unit forecast leave Pending beside `t7-twin`? (section 0; U7) | `workflow describe`, `workflow why` |
| 2 | Does `fuzzball workflow validate` pass on each rendered file, and does it check that volumes exist? (U1) | validate all five |
| 3 | Is `--name` a flag of `workflow start`? (U2) | `fuzzball workflow start --help` |
| 4 | What does `workflow start` print? (U3) | the first start; the dispatcher accepts both forms |
| 5 | Keys and status spelling of `workflow list -o json`, above all for a pending workflow (U4). The dispatcher treats `PENDING`, `UNSPECIFIED`, `QUEUED` and an empty status as pending | `fuzzball workflow list -o json` once |
| 6 | Does `workflow list` cut the list off? A hidden running workflow would get past the guard (U5) | `fuzzball workflow list --help` |
| 7 | Does a queued workflow block updates? The dispatcher counts any unfinished `t7-build`, `t7-fit`, `t7-smoke`, `t7-ward` as busy, queued or not, and never stops those. `/api/runs` shows `running.state` | keep the queue empty; do not submit a retrain while the demo is up |
| 8 | How much memory does vLLM take at `--gpu-memory-utilization 0.85` on unified memory, against Nemotron's 100 GB request? Is a request also a limit? | `free -g` inside the `nemotron` service (`workflow exec`); `nvidia-smi` shows no memory on GB10 |
| 9 | Peak memory and run time of `extract` for 25 stays (starting values 8 cores, 48 GB, 10 minutes) | `free -g`, the job's duration |
| 10 | What happens when a readiness probe runs out of tries? (U6) | watch a cold Nemotron start |
| 11 | May team7 create an ephemeral volume? (`t7-smoke`; U8) | the smoke run |
| 12 | Does the `subdomain` endpoint resolve? If not, use `type: path` (U9) | open the URL from `workflow endpoints` |
| 13 | `FB_UI_URL`, the CLI checksum, and whether the CLI fits on `/dev/shm` in a 2 GB service (U10, U11, review F5) | the first dispatcher log. Fallback: a 1 GB ephemeral volume mounted only by the dispatcher |
| 14 | Do `nvcr.io` pulls need an image secret? (U12) | the first GPU job |
| 15 | Can other teams' jobs reach our nodes' ports 8000, 8080, 9000 without the endpoint check? (U13, review F6) | ask CIQ |
| 16 | Does losing a node fail all of `t7-twin`? (U14) | ask CIQ; do not test on demo day |
| 17 | Scheduler interval, preemption, backfill, which node is picked when both fit | ask CIQ; `COMPUTE_PLAN.md` section 8 |

**Images are pinned by tag, not by digest** (review F7): `nvcr.io/nvidia/pytorch:25.11-py3`, `nvcr.io/nvidia/vllm:25.12.post1-py3`, `lmsysorg/sglang:v0.5.21`, `python:3.12-slim`. The docs recommend digests for reproducibility. This is a recommendation, not a blocker: the arm64 digests have to be read on the cluster or from the registries, and `python:3.12-slim` is the one that moves.

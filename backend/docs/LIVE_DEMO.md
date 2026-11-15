# Demo day: how ICU Lookahead runs live, end to end

Read this if you want the demo-day design: what is real on stage, the minute-by-minute plan, the fallbacks and the forecast CLI flags. To start or relaunch the app, use [`RUNBOOK.md`](RUNBOOK.md).

**Status:** The team ran ICU Lookahead end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, and it worked. Not run: PR #16's `t7-lookahead-*` workflows and `t7-twin` without Nemotron.

Sections 0 to 8 are the design as written on 2026-11-14; section 9 holds the later decisions and wins where they differ. Where a paragraph disagrees with this table, the table wins.

| Topic | Current state (code on `main`) |
|---|---|
| How to run | `scripts/launch.sh` first ([`RUNBOOK.md`](RUNBOOK.md)); the manual workflow steps are the fallback |
| Volumes | `twin-store` is the one volume ICU Lookahead writes (code, packages, stage ward, forecast files). `mimic_clif` is only read, at `/data`. `hfcache` holds the Nemotron weights. `clif_work` and `tooling` are not used |
| Probe | Fitted by job 4 in vaishvikc/ICU-Twin and staged at `/store/train/probe-final.joblib` with `probe-final.meta.json`. `t7-fit` is the fallback |
| Names | Generated per room number by `app/fake_names.py` (`--names fake`). `name.parquet` is no longer read |
| Code on the cluster | Published by `t7-code` from this repo's `backend/` at a pinned commit. Training (`job_2` to `job_4`) is in vaishvikc/ICU-Twin; there is no `t7-build` here |
| Schedule and cut | One run at 07:00; each patient is cut 24 h after ICU arrival; five predictions on the board |

Status: design plus the code that already exists (2026-11-14, branch `t7/fb-live-demo`; the later decisions are in section 9 and win where they differ: 07:00 run, unit and room updates, demo clock, capacity). It answers one question: **after the model is trained, what happens on the day, minute by minute, and what is still missing?** Section 7 is the gap list. Section 8 is what J.C. must decide.

Companions: `docs/DECISIONS.md` (D2 probe scoring, D3 cut at 24 h after ICU arrival, D6 privacy line, D9 dispatcher, D10 which unit), `docs/CLUSTER_FACTS.md`, `.claude/skills/fuzzball-ops/SKILL.md`, and the frontend repo (`docs/INTEGRATION.md`, `FRONTEND_SPEC.md`, `FRONTEND_PLAN.md`, `ARCHITECTURE.md`). The chat agent (`app/chat_agent.py`) and the board server (`app/board.py`) are on `main`; this file states what they need from the backend.

Fuzzball facts below were checked against the 4.3 docs on 2026-11-14: in-workflow API access (`https://docs.ciq.com/fuzzball/4.3/advanced-features/in-workflow-api-access`), workflow endpoints (`.../workflow-endpoints`) and connecting to services (`.../workflow-connect`). Cluster state was read with read-only calls only (`workflow list`, `volume list`, `node list`).

---

## 0. The day in one picture

| Layer | What runs | Where | When |
|---|---|---|---|
| Model | `icutwin` decoder, trained by `t7-build` (both GPUs), published to `twin-store` | `twin-store/model`, code in `twin-store/code` | once, before the demo |
| Probes | one logistic probe per task, **fit once on MIMIC training stays**, saved | `twin-store/train/probe-final.joblib` | once, right after training (new, section 1.3) |
| Stage ward | 25 open MIMIC-IV Demo stays, rooms 1 to 25, tokenized and cut 24 h after ICU arrival | `/store/stage/` on `twin-store` (volume, never git) | once; rerun is idempotent |
| Forecast run | `t7-forecast`: one forward pass per stage-ward room on one GPU, apply the saved probes, write `rooms.json`, then `forecast.json` | GPU 1 for minutes, CPU for the rest | 07:00 (dispatcher), on request (board or chat), or by hand |
| Twin | `t7-twin`: Nemotron on GPU 2, the board (`app/board.py`, HTTPS endpoint), the dispatcher | always on | up before 07:00 on demo day |
| Browser | one static page served by the board | presenter laptop, team devices | during the demo |

What the audience sees: a 25-room board, the unit rows with 80% ranges, a strain ratio, a room drawer, a chat. What is true behind it: every room is a real, de-identified, openly licensed ICU stay replayed as a ward, scored by a model that never saw it, using probes fit on credentialed data that appears on screen only as counts.

---

## 1. "Real patients": what is real and what is not

### 1.1 The line

| Thing | Source | On screen | Notes |
|---|---|---|---|
| Training, tuning, held-out evaluation | credentialed MIMIC-IV-Ext-CLIF on `mimic_clif`, training tokens in `mimic_clif:/tokenized_output` | **counts only** (D6): how many stays, held-out AUROC and calibration per task, the typical-day baseline | never a row, a timeline or a per-patient score |
| Stage ward (rooms 1 to 25) | open MIMIC-IV Demo in CLIF (`clif_demo/`, openly licensed, tracked in the repo; 100 patients, 310 hospitalizations) | **per room** (probabilities, tags, last 12 h of events, chat) | the demo patients are removed from every training split by `icutwin.exclude_demo` (in `t7-build`, by patient), so the model and probes have never seen them |
| The unit (strain index, unit rows, margin) | the same 25 rooms (D10 option A, recommended) | counts with 80% ranges | one population on one screen |
| "07:00" | notional | labels say 07:00 to 07:00 | each stay's cut is 24 h after its own ICU arrival, on different calendar dates; the board is a **replay**, not a live census. Label it so (section 8, decision 4) |
| Rerun | the same patients, the same model, the same probes | a new `made_at` | numbers repeat unless the model or probes change; a rerun proves the Fuzzball path, not new information |

### 1.2 How 25 selected stays become the stage ward

The 25 stays were first selected on a team machine (at least 24 h in the ICU, median-sickness band, seed 20261114). That selection must be **reproducible from open data inside the cluster**, so `app/stage_ward.py` implements it from the `clif_demo/` tables alone (no GPU, no model, no network, runs in seconds):

```bash
python app/stage_ward.py /store/code/clif_demo --out /store/stage/stage_ward.csv      # seed 20261114, n 25
```

Rule, as coded:

1. **Eligible**: the stay has an ICU row in `clif_adt`; at the first ICU arrival plus 24 h (the cut of `icutwin/config/winnowing.yaml`) it is still in that ICU row and still in hospital.
2. **Score 0 to 8** over the first 24 h after arrival, one point each: any vasopressor dose above zero (angiotensin, dopamine, epinephrine, norepinephrine, phenylephrine, vasopressin), invasive ventilation, any CRRT record, MAP < 65, lactate > 2, creatinine > 2, platelets < 100, and (SpO2 < 90 or FiO2 >= 0.6).
3. **Band**: scores between the 40th and 60th percentile of the eligible stays (numpy `lower` and `higher` at the edges). If the band holds fewer than 25 patients it widens by 5 percentile points a side and prints that it did.
4. **One stay per patient** (lowest hospitalization id), then a seeded draw (`numpy.random.default_rng(20261114).permutation`), and **room numbers 1 to 25 follow the draw**.

It prints counts and a 12-digit digest only. The CSV (`room, hospitalization_id, score`) goes to `/store/stage` on `twin-store`; `*.csv` is in `.gitignore`, and the test checks that no id reaches stdout.

Run on the repo's open `clif_demo/` on 2026-11-14 (counts only): 101 eligible stays from 82 patients; score counts 0..8 = 9, 19, 23, 13, 14, 15, 4, 3, 1; band p40 to p60 is scores 2 to 3 (36 stays, 32 patients); 25 selected (15 with score 2, 10 with score 3); digest `9021f82b3b5d`. Tokenizing the demo and winnowing it with `icutwin/config/winnowing.yaml` locally kept **25 of 25** selected stays (112 stays winnow in all, because the winnower also keeps stays that move ICU to ICU, which the selection does not).

**Reconcile with the team-machine list** (lane 3, minutes): print the digest of that list the same way (`stage_ward.digest`). If equal, done. If not, recommendation: adopt the script's list. The data is open, nothing clinical rests on which 25, and a list nobody can regenerate inside the cluster is the weaker claim.

While doing this, one bug on `main` surfaced and is **fixed on this branch** (flag for Vaishvik, hardware-pivot style note): `icutwin-winnow -c icutwin/config/winnowing.yaml` was refused with `unknown option(s) ['horizon_after_threshold_s']`, because the shipped `winnowing.yaml` only had that key as a comment. That would have stopped `t7-smoke` and `t7-build` at the winnow step. `winnowing.yaml` now lists the key (null), the winnower treats null as unset, and a test loads the example override.

### 1.3 The per-room scoring path

Today `rep_based.py` fits probes and scores held-out in one go and keeps nothing. Implemented on this branch (`icutwin/scoring/rep_based.py`, tests in `tests/test_rep_probes.py`):

- `icutwin-rep-score <tokenized_output> -m <model> -c examples/probe_tasks.yaml` saves every fitted probe in one `probe-<model>.joblib` (task -> probe; a task with one class in training has no probe and scores NaN), `probe-<model>.meta.json` (weights sha256) and `metrics-rep-based-<model>.json` (training counts and held-out metrics).
- `icutwin-rep-score <stage tokenized_output> -m <model> --apply-probes /store/train/probe-final.joblib --stay-ids /store/stage/stage_ward.csv` **never fits**: it reads `features-<split>-<model>.parquet` and `<split>_for_inference.parquet` for every split present, keeps the 25 ids, applies each probe with the same `_past` mask (a task that already happened before the cut is NaN, not a new event), and writes `scores-rep-based-<model>.parquet` in the layout `app/aggregate.py` already reads. It refuses probes saved for a different model name. The test checks the scores equal a direct `predict_proba` of the loaded probe.
- joblib pickles tie the probes to the scikit-learn in `/store/py`; keep `fit` and `apply` on the same packages (`/store/py`).

Pipeline on the day (all inside the cluster; this layout is now `fuzzball/t7-ward.fz` and `fuzzball/t7-forecast.fz`, gaps G2 and G3 are closed):

| Step | Command | Runs on | When |
|---|---|---|---|
| fit | `icutwin-extract /store/train -m /data/model_output/final` (train, tuning, held_out) then `icutwin-rep-score /store/train -m ... -c examples/probe_tasks.yaml` | GPU then CPU | **once** after `t7-build`; the slow, MIMIC-sized step, never repeated by a rerun |
| stage-select | `python app/stage_ward.py /store/code/clif_demo --out /store/stage/stage_ward.csv` | CPU | once (deterministic) |
| stage-tokenize | `printf 'clif_path: /store/code/clif_demo\ntimezone: US/Eastern\nfiletype: parquet\n' > site.yaml; icutwin-tokenize pipeline site.yaml` in `/store/stage`, then `icutwin-winnow tokenized_output` | CPU | once (2 s locally for tokenize) |
| vocab check | the stage `vocab.yaml` must equal the training `vocab.yaml` (`cmp`); the vocabulary is fixed by the token spec, so ids match, but check | CPU | once, and as a go/no-go item |
| **extract (rerun)** | `icutwin-extract /store/stage/tokenized_output -m /data/model_output/final` | **GPU 1**, model load plus about 100 short forward passes | every run |
| **apply (rerun)** | `icutwin-rep-score /store/stage/tokenized_output -m ... --apply-probes /store/train/probe-final.joblib --stay-ids /store/stage/stage_ward.csv` | CPU, seconds | every run |
| **rooms (rerun)** | `python app/rooms.py` (to build, G4): per room `room`, `age_band`, `on_now`, `risk_24h` (null where on), `recent` (last 12 h) from the stage scores and the open `clif_demo` tables; writes `/store/rooms.json` | CPU | every run, **before** forecast.json |
| **aggregate (rerun)** | `python /store/code/app/aggregate.py /store/stage/tokenized_output /store/forecast.json --beds 25 --score rep --baseline /store/train` | CPU | every run, **last** (it is the commit marker the page watches) |

`rooms.json` follows the contract in the frontend `FRONTEND_PLAN.md` (stage ward only, no identifiers, `age_band` not age, `null` in `risk_24h` means on now). Rooms and forecast must come from one run: both carry the same `made_at` family (UTC with offset), rooms first.

### 1.4 Which patients make up "the unit", and the strain baseline

**Recommendation, D10 option A**: the unit is the same 25 rooms. `aggregate.py` is pointed at the stage-ward scores with `--beds 25`; all 25 are used, so the draw is deterministic and there is no sampling noise from choosing beds. Real MIMIC-IV held-out stays power training, the held-out check (D7) and the backtest, and appear as counts only. Option B would put a real held-out unit beside demo rooms: two populations, and unit numbers a viewer could not tie to a room.

**Strain index** (implemented in `app/aggregate.py`, `strain_index`, tests in `tests/test_app.py`):

- `typical_day` = beds x the sum over the five board tasks of the training rate of a **new** event: the share of training stays (`train_for_inference.parquet`, cut 24 h after ICU arrival) with `<task>_future` true and no `<task>_past`, i.e. the mean `_future` rate among stays not already on. This is the same "already on is not new" rule the forecast uses, so numerator and denominator count the same thing. A multi-token task (leaving the ICU = ward or step-down) uses "any token".
- `ratio` = simulated total new events over the five tasks (independent Bernoulli draws, 10,000) divided by `typical_day`; p10, p50, p90.
- `band` from the p50 ratio, as in the board mockup: QUIET below 0.8, USUAL below 1.2, BUSY below 1.6, VERY BUSY above.
- `above_usual` = tasks whose forecast over typical reaches 1.25, largest first.
- If the baseline file is missing the key is **omitted** (the page shows "pending run"), not guessed.

`forecast.json` gains:

```json
"strain": {
  "beds": 25,
  "tasks": ["ventilator", "vasopressor", "crrt", "hypotension", "death", "icu_departure"],
  "typical_day": 7.25,
  "expected": 14.5,
  "ratio": {"p10": 1.7, "p50": 2.0, "p90": 2.3},
  "band": "VERY BUSY",
  "above_usual": ["ventilator", "vasopressor"],
  "per_task": {"ventilator": {"typical": 4.75, "expected": 9.5, "ratio": 2.0}},
  "baseline": "training stays: mean new-event rate per task x beds"
}
```

(The numbers above are the unit test's synthetic example, not a result.) Caveats to say out loud: the leaving-the-ICU forecast is the larger of two probabilities, a lower bound on "either", while its baseline is "either", so that row reads slightly low; the strain ratio is a forecast summary against the unit's own training norm, not a validated outcome score; the cut-offs are the mockup's, not clinically derived.

Also changed in `aggregate.py`: `made_at` now has a UTC offset (job containers are not on hospital time; a bare local string would make the page think the forecast is hours old or in the future), and `forecast.json` is written to a temp file and renamed, so the board never reads half a file.

One thing to check before the demo (G13): in the open demo stays, 95% already met `LABEL//hypotension_init` (MAP < 65 or SBP < 90) before the cut (`_past` rate from the local winnow log). If MIMIC training looks the same, that row will be near zero for almost every room and the strain ratio is dominated by the other five.

### 1.5 Forecast CLI

The ICU Lookahead forecast (five predictions, life support, yardstick; JSON in `docs/CONTRACT.md`) is written by two scripts. Both print counts only and write atomically. Paths below are examples on the cluster volumes.

**Unit run** (every run, last step; `forecast.json` is the commit marker the page watches):

```bash
python /store/code/app/aggregate.py /store/stage/tokenized_output /store/forecast.json \
    --beds 25 --baseline /store/train \
    --stage-csv /store/stage/stage_ward.csv \
    [--capacity /store/capacity.json] [--demo-clock-hours 6] [--cut-time ISO] [--tz America/Chicago] [--real-ward]
```

| Flag | Meaning |
|---|---|
| `--baseline DIR` | folder with the training `train_for_inference.parquet`; gives the "typical" yardstick (USUAL / BUSY / VERY BUSY). No file: `yardstick` is `null`, never a guess |
| `--capacity FILE` | JSON `{"life_support_patients", "vents_free", "set_at", "set_by_role"}`. If it exists the yardstick switches to `kind: "capacity"` (ON TRACK / TIGHT / SHORT); absent or unreadable, the typical yardstick applies. The services agent writes this file when the charge nurse sets capacity |
| `--stage-csv FILE` | `stage_ward.csv`; fills `check_first` with room numbers. Every stay id must be in the git-tracked `clif_demo/clif_hospitalization.parquet`, otherwise it refuses unless `--real-ward` is given |
| `--real-ward` | the room map is a real MIMIC-IV ward (decided 2026-11-14: approved, local only). `forecast.json` and `rooms.json` then carry `"ward": {"source": "mimic-iv", "label": "Real MIMIC-IV · local only"}` (default `open-demo`). Patient data stays on the cluster volumes; stdout holds counts only in both modes |
| `--demo-clock-hours H` | recorded as `demo_clock_hours`, and the default `cut_time` / `window` move with it (the last 07:00 plus H hours); the ward's cut itself moves in `icutwin-winnow` (below) |
| `--cut-time ISO` | cut with a UTC offset (a time without one is refused), taken as given; default is the 07:00 nearest to now in `--tz`. `--tz` defaults to `America/Chicago`, the event's zone and the one `t7-twin` runs in; pass it explicitly when the site differs. The board is a replay, so this label is notional |
| `--beds N`, `--seed S` | unit size (default 25: all stage rooms) and sampling seed |

**Room run** (`rooms.json`; before the unit run; `--real-ward` for a real ward, `--demographics <real CLIF folder>` then reads age and sex from it):

```bash
python /store/code/app/rooms.py /store/stage/tokenized_output \
    --model /data/model_output/final --probes /store/train/probe-final.joblib \
    --stay-ids /store/stage/stage_ward.csv --out /store/rooms.json
# one room (room scope): rewrite that room only, nothing else (needs the whole-ward rooms.json first)
python /store/code/app/rooms.py ... --room 7          # or --stay <hospitalization_id>
# room scope plus a new unit forecast from the whole ward
python /store/code/app/rooms.py ... --room 7 --recount --forecast /store/forecast.json \
    --baseline /store/train [--capacity /store/capacity.json] --demo-clock-hours 6
```

`rooms.py` applies the saved probes itself (`icutwin.scoring.rep_based.apply_probes`, never a refit). Use `--no-apply` when `apply_probes` already wrote `scores-rep-based-<model>.parquet`. A room-scope run scores only that stay into `scores-rep-room-<N>.parquet`, so the ward's scores file stays whole. It refuses stale features: `icutwin-extract` stores each row's cut (`last_valid`, `cut_s`) in the features file and `rooms.py` / `apply_probes` refuse any row whose stored cut is not the labels' cut (a demo-clock move, or a one-room re-extract that left other rooms at the old cut), so after a clock move the whole ward must be re-extracted. Probes and scores are tied to the model weights, not the folder name: `probe-<model>.meta.json` and a `scores-rep-based-<model>.meta.json` beside each scores file hold a sha256 of the weights, and `apply_probes` / `--no-apply` refuse a mismatch (refit or re-score). `--no-apply` reads `scores-rep-based-<model>.parquet` of the `--model` given, never another model's newest file. The last stdout line is JSON counts: `scope`, `rooms_written`, `rooms_in_file`, `dropped`, `recount`, `high`.

**Demo clock** (move the cut later or earlier than "24 h after ICU arrival"): the cut is made by the winnower, so a new offset is a three-step chain, all on the stage ward only:

```bash
icutwin-winnow /store/stage/tokenized_output --demo-clock-hours 6
icutwin-extract /store/stage/tokenized_output -m /data/model_output/final      # GPU, about 100 short passes
python /store/code/app/rooms.py ... --recount --forecast /store/forecast.json --demo-clock-hours 6
```

`--demo-clock-hours` (also `threshold.after_first_occurrence.offset_s` in the winnow config) is added to the 24 h; `duration_s + offset_s` must stay above 0 (a cut at or before ICU arrival is refused). Stays whose record ends before the new cut drop out of the winnow output; `rooms.py` reports how many in `dropped` (ward rooms with no entry, never negative) and leaves those rooms out of `rooms.json`. On the open demo data: 0 h keeps 112 stays, +12 h keeps 80, +48 h keeps 45 (all stays, not only the 25 rooms). A clock move changes every stay's cut, so re-extract the whole ward; for one room with an unchanged clock use `icutwin-extract --stay-ids`, and after a new capacity or a plain rerun `--room` needs no GPU.

**What "on now" means (decided 2026-11-14): what is running at the cut, from the last record before it.** `icutwin-winnow` writes three boolean columns from `at_cut` in `winnowing.yaml` (hardware/demo pivot, for Vaishvik), which `aggregate.py` and `rooms.py` use everywhere "on now" appears, and which make a support that stopped before the cut forecastable again:

| Support | Running at the cut when | Tokens it reads |
|---|---|---|
| IMV (`LABEL//imv_at_cut`) | the last respiratory-support device record before the cut is `imv` (a change to nippv, high flow, etc. is off) | `RESP//device_category//*` |
| Vasopressor (`LABEL//pressor_at_cut`) | for any listed pressor, its last non-null dose before the cut is > 0 (a null dose is unknown, so the previous dose carries); a dose of 0 is off. Same drug list as `LABEL//pressor_init` (includes dopamine and epinephrine) | `MED_CON//<drug>//*`, raw `value` column |
| CRRT (`LABEL//crrt_at_cut`) | **fallback**: a CRRT row in the 24 h before the cut. `CRRT//crrt_init` is a charted-row flag with no mode, stop or end value, so the tokens cannot show a stop | `CRRT//crrt_init` |

No continuous-infusion stop action (`mar_action`) reaches the tokens, so a pressor stop is only visible as a charted dose of 0 (a drug whose last record is a positive dose and then nothing is still counted as running). On the open demo data (112 stays): IMV running 30 (52 started before the cut, 22 stopped), pressor 19 (43 started, 24 stopped), CRRT 2 (2 started). Label files made before this change lack the columns; the code then falls back to "started before the cut" (`_past`).

A stopped support is scored again by the saved probe, which was fit on never-started stays, so that score is an extrapolation. `stopped_before_cut` in `rooms.json` marks those cases. ECMO and mechanical circulatory support have no token in `icutwin/config/tokens/` (the CLIF `ecmo_mcs` table is not tokenized), so `ecmo` is `null`, meaning "not available", everywhere.

`icutwin-extract --stay-ids stage_ward.csv` re-extracts only those stays and keeps the other stays' rows in the features file (use it after a one-room change with an unchanged clock; a clock move changes every stay's cut and needs the whole ward re-extracted).

---

## 2. Fuzzball flow on the day

### 2.1 Volumes (state on 2026-11-14, read with `volume list`)

| Volume | Exists now | Holds | Mounted by |
|---|---|---|---|
| `mimic_clif` | yes | credentialed CLIF parquet, the trained model (`model_output/final`), training tokens, the cohort (`dashboard_data/`); only read by us | training; read by fit, ward, forecast |
| `hfcache` | yes | Nemotron weights | `t7-smoke`, `t7-twin` |
| `datasets` | yes (shared, read-only for us) | open datasets | nothing of ours |
| `twin-store` | **no: the one volume to create** | everything we write: code, packages (`/store/py`), probes, `train/`, `stage/`, `forecast.json`, `rooms.json`, `capacity.json`, `runs.jsonl`. `stage/` and `train/` are row-level: treat it as restricted | code, fit, ward, forecast, twin |
| ~~`clif_work`~~ | dropped 2026-11-14 | its contents are on `twin-store` | |
| ~~`tooling`~~ | dropped 2026-11-14 | `/store/py` on `twin-store` | |

Every workflow stops at the missing volume, so creating `twin-store` is gap G1 (needs the team's go-ahead; `fuzzball volume create team7 twin-store --size 50GiB`, see `FUZZBALL_VALIDATION.md`). The board and the dispatcher mount only `twin-store`; since 2026-11-14 that volume also holds the staged tokens (the board serves only the JSON files and the page; the trade-off is in `FUZZBALL_VALIDATION.md`), which is why the room files must hold open-data fields only.

### 2.2 Order of workflows and the GPU clock

| # | Workflow | GPU 1 | GPU 2 | Time |
|---|---|---|---|---|
| 1 | `t7-smoke` (seeds a tiny model, prefetches Nemotron) | 1 | free | done before build |
| 2 | `t7-build` (tokenize, exclude demo, winnow, train, publish) | train rank 0 | train rank 1 | hours; gate 15:00 Sat |
| 3 | **fit** (extract train/tuning/held_out, save probes, held-out metrics) | 1, then CPU | free | once, after publish; measure it |
| 4 | `t7-twin` (Nemotron, board, dispatcher) | free | Nemotron | start as soon as build ends; stays up |
| 5 | `t7-forecast` (07:00, on request, by hand) | extract job | Nemotron | minutes |

Nothing that holds a GPU runs during training. The scheduler places work; it does **not** pin nodes. The forecast always lands on the node Nemotron is not on, because Nemotron's service holds its GPU exclusively. Consequence: the container image for the extract job (`nvcr.io/nvidia/pytorch:25.11-py3`) is pulled onto that node on first use. The T-60 rehearsal run (section 6) warms it; do not meet the pull for the first time on stage.

### 2.3 How the dispatcher starts `t7-forecast`

Superseded by section 9 (Lookahead): scopes, the template, the guards, the 07:00 retry and catch-up, the demo clock. What stays true from the in-workflow API docs:

- Fuzzball injects `FB_TOKEN`, `FB_API_HOST`, `FB_OPENAPI_URL` into every job and service. The token acts **as the submitting user** (team7), is bound to the workflow it was injected into, and covers start, validate, list, describe and stop of workflows, logs, volumes list/create, object cache and endpoint listing; it refuses secrets, volume deletion and admin. It **stops working the moment `t7-twin` finishes, fails or is cancelled**. In a service it expires after 7 days; the dispatcher refreshes it daily (`POST $FB_OPENAPI_URL/v4/workflows:refreshToken`, swapped in only on success). On demo day check the age of `t7-twin` (under 7 days).
- The CLI is downloaded by the service to container-local tmpfs (`/dev/shm`, not the shared `/store`) and checked against `FB_CLI_SHA256` when that is set (the service prints the hash it got when it is not; pin it in `t7-twin.fz`).
- The new workflow's parent is `t7-twin` (`fuzzball workflow list --parent <twin-id>`).

### 2.4 What a rerun costs

Superseded by section 9: the fit step is its own workflow (`t7-fit`), so an update is cheap (dispatcher CLI call, image pull cached after the rehearsal, model load plus about 100 forward passes on one GPU, probe application, rooms, aggregate). None of those timings has been measured on the GB10s: **record three numbers at the T-60 rehearsal** (`extract` seconds, total seconds from button to new `made_at`, GPU-hours from `fuzzball report charges workflow <id> -o json`) and put them on the page's "running, about N min" line. Python deps come from the hash-pinned lock in `/store/py` (no PyPI at update time).

### 2.5 A node goes offline (one already did during the data move)

`node list` today shows several nodes in a degraded health state and one cordoned, so assume it can happen again. Check **our** two nodes at T-60 (`fuzzball node list`, health and status).

| Situation | What happens | What to do |
|---|---|---|
| Node with the **forecast** GPU fails mid-run | the job fails (one-shot jobs have no automatic retry; `policy.restart: on-node-fault` is the only retry option) | dispatcher guard clears when the workflow errors; press Rerun; it lands on the free node; the board keeps the last good forecast |
| Node with **Nemotron** fails | Expect **all of `t7-twin` to fail**: on Fuzzball 4.3.1 a service that fails (a node fault, or an exit with an error) fails the workflow (release notes v4.3.1), so the board and dispatcher go with it and the endpoint URL is removed. Whether a node loss ends only the service on that node is not documented (`FUZZBALL_TEST_PLAN.md`, live check) | `fuzzball workflow describe <twin-id>`; restart `t7-twin` (the model reloads from `hfcache`, minutes) and read the new URL. If only one node is left, start the no-chat copy (`COMPUTE_PLAN.md` mode F). The files on `twin-store` are untouched, so the board comes back with the last forecast |
| Both GPUs end up on one node's workflows | the forecast job pends (`INSUFFICIENT_RESOURCES`) | `fuzzball workflow why <id> <alloc>`; free the GPU by stopping the stale workflow (lane 2 owns that) |
| The board or dispatcher is on the failed node | same as above: expect the whole workflow to fail | restart `t7-twin`; the dispatcher gets a new token and the board comes back on a new URL (`workflow endpoints`) |
| The board or dispatcher **process** crashes, or the dispatcher cannot install or verify the Fuzzball CLI | Nothing else is lost. Both scripts in `t7-twin.fz` loop and never exit with an error. A dispatcher without a usable CLI stays up degraded: `/api/runs` says `{"available": false, "reason": "dispatcher unavailable: ..."}`, its log says `DISPATCHER UNAVAILABLE`, `GET /health` on it is 503, no 07:00 run and no updates start | read `fuzzball workflow log <twin-id> dispatcher -n 50`; fix the cause (`FB_UI_URL`, `FB_CLI_SHA256`) and restart `t7-twin` at a quiet moment |
| A forecast run waits and never starts | the dispatcher stops a run still pending after 5 minutes, or not ended after 45; `/api/runs` has `stuck` with the reason; the next ask or the next 07:00 retry starts a new run | `fuzzball workflow why <id> <alloc>` to see what holds the GPU |
| Cluster API unreachable | dispatcher refuses ("cannot list workflows"); the board still serves the last files | section 6 fallbacks |

The board has no `depends-on` on Nemotron (G7), so a Nemotron that is still loading does not keep the board down. A Nemotron that **crashes** is different: `vllm serve` exiting with an error fails the workflow (row above).

---

## 3. Hosting the board page

### Recommended path (one): vendor the page into the backend, serve it from `twin-store`, hot-swap by file

1. The frontend repo stays the source (`web/index.html` at each milestone, per its F2). Lane 4 copies it into the backend as `app/static/index.html` by small PR to `vaishvikc/ICU-Twin`; Vaishvik merges. No build step, no CDN: the board image is `python:3.12-slim`, and the page must work with the cluster offline.
2. `app/board.py` (in progress, lane 4) serves it at `/`, plus `GET /api/rooms`, `room` on `/api/ask`. **Requirement for that PR: read the static file from disk on every request**, so a new page can go live without restarting `t7-twin` (which would bounce Nemotron and cost minutes).
3. Code reaches the cluster only through `/store/code`, and today that is replaced only by `t7-build`'s `publish` step (`t7-smoke`'s `seed` skips when a model exists). So add a tiny CPU workflow **`t7-sync`** (G9): ingress the GitHub tarball of a **tag**, copy to `/store/code.new`, swap directories (`mv code code.old; mv code.new code`), print file counts. A page-only update then takes one workflow run and no restart; a `board.py` change still needs `t7-twin` restarted.
4. Tag the frozen demo commit (Sunday 11:00 freeze); `t7-sync` pulls the **tag**, not `main`.
5. Open it with `fuzzball workflow endpoints <twin-id> board web` (URL) and `fuzzball workflow connect --name board --endpoint web <twin-id>` (opens it in the browser). The endpoint is `scope: group` (team7 only). Endpoint tokens: `fuzzball workflow endpoints generate-token <endpoint-id> --expiration 24h`, presented as an `Authorization` or `FB-Authorization` header; a token only works while `t7-twin` runs and dies with it. How a judge's **browser** (which cannot set headers) reaches a `group` endpoint is not verified: the demo laptop uses `connect` (G16).

Why not fetch the page at build or start time: it adds a GitHub dependency at the worst moment and an unpinned version; copying is auditable (the page in the PR is the page that runs) and matches the frontend plan.

### Fallbacks

| Where | Data | Chat and rerun | Use |
|---|---|---|---|
| Laptop, `?mock=1` or the backend against the example file (`uv run python app/board.py --forecast <example forecast.json> --port 8080`) | synthetic | mock replies / "Nemotron not answering" | **stage fallback** if the cluster is down: say plainly it is the same page on synthetic data |
| Cluster endpoint | stage-ward rooms, real counts | Nemotron, dispatcher | the demo |

Keep the laptop server running during the demo (`python3 -m http.server 8000` in the frontend repo, `#night`, `#room=7` deep links) so switching is one tab.

---

## 4. Requests from the board

Superseded by section 9 and `docs/CONTRACT.md` (the endpoints, bodies and fields), and by the sequence in `docs/CHAT_AGENT.md`. Two rules every client must follow:

- Every POST (`/api/rerun`, `/api/capacity`, `/api/ask`) sends `Content-Type: application/json` and `X-Lookahead: 1`; an `Origin` header, if the browser adds one, must match the page's own host. Anything else gets `403 {"ok": false, "reason": "request refused"}`; a body over 4096 bytes gets 413 and a bad `Content-Length` 400. Timeouts: 150 s for `/api/ask` and `/api/rerun`, never auto-retried.
- The page learns a run finished by `made_at` changing, or from `GET /api/runs` (`running`, `updating`, `scheduled`: ok, pending, failed or missed).

## 5. Chat: what the agent needs from the backend

The agent loop lives in `app/chat_agent.py` with the board changes in `app/board.py`, both **in progress** on `t7/ui-chat-agent`. This section is the backend's side of the contract; no file here edits either.

| Tool or context | Source | Content | Privacy |
|---|---|---|---|
| unit forecast | `/store/forecast.json` | the five `resources` (`team`, `p10`, `p50`, `p90`, `expected`), `already_started`, `made_at`, `beds`, `range`, `horizon`, `model`, `method` | counts only |
| strain | `forecast.json` `strain` | `typical_day`, `ratio` p10/p50/p90, `band`, `above_usual`, `per_task` | counts only; if absent say "pending run" |
| other tasks | `forecast.json` `other_tasks` | the eight research forecasts (`icu_transfer_in`, potassium, sodium, anemia, tachycardia, hypertension), team `research` | answer only when asked; never as staffing |
| one room | `/store/rooms.json`, selected by `room` | `risk_24h` (six, null = on now), `on_now`, `age_band`, `recent` (last 12 h) | stage ward only (D6); no identifiers by construction |
| runs | dispatcher `GET /status` | `next_scheduled`, `recent` (time, trigger, workflow, name, started) | role and ids only |
| rerun | dispatcher `POST /run {role}` | `{started, name, workflow}` or `{started: false, reason}` | the intent check stays server-side |
| held-out trust | `/store/heldout_metrics.json` (to build, G11) | per task AUROC and calibration on patients the probe never saw | counts and rates only |
| honesty | system prompt | name the horizon, quote the 80% range, evidence not cause, no treatment advice, "the forecast does not cover that", say these are replayed open demo patients | |

Failure behaviour the agent must keep: Nemotron unreachable returns a one-line "not answering yet" and the board keeps working; questions are never logged; a rerun answer states the dispatcher's reason verbatim.

---

## 6. Demo-day runbook (T-60 to T+5)

Run as the demo machine (read-only MCP is fine for looking; starting needs the shell or the `--allow-exec` server that is never committed). **Lane 2 owns starting and stopping the shared `t7-*` workflows; ask before starting anything.** Needs the event network.

### T-60: state of the world

```bash
fuzzball context list                                  # context hack, account team7
fuzzball node list                                     # OUR two nodes: READY and healthy (not CORDONED, not DEGRADED)
fuzzball volume list                                   # mimic_clif hfcache datasets twin-store
git fetch origin --tags && git checkout <demo-tag> && uv run --extra dev --extra model pytest -q
for f in fuzzball/t7-*.fz; do fuzzball workflow validate "$f"; done      # every file, off-site it times out
fuzzball workflow list --status started                # is t7-twin up? which workflow holds which GPU?
```

If `t7-twin` is not running:

```bash
fuzzball workflow start fuzzball/t7-twin.fz --name t7-twin
fuzzball workflow describe <twin-id>                   # nemotron, board and dispatcher Started
fuzzball workflow log <twin-id> dispatcher -n 50       # CLI downloaded, no auth error (G7 check)
fuzzball workflow endpoints <twin-id> board web        # the URL
fuzzball workflow connect --name board --endpoint web <twin-id>
```

Preflight on the volumes (an agent cannot read volumes, so a small CPU workflow prints counts: **to build**, G10): model dir present, `/store/train/probe-final.joblib` lists the expected tasks, stage CSV has 25 rows and digest `9021f82b3b5d` (or the reconciled one), stage `vocab.yaml` equals the training one, `forecast.json` and `rooms.json` exist and share a `made_at`, stage scores hold 25 of 25 rooms.

### T-45: rehearsal run on the real path

Press **Update the unit** on the board as "ICU nurse" (or `curl` the board, `POST /api/rerun {"role":"ICU nurse","scope":"unit"}`); then **Update this room** on one room:

```bash
fuzzball workflow list --parent <twin-id>              # a t7-forecast-MMDD-HHMM with t7-twin as parent
fuzzball workflow describe <forecast-id>               # extract Started on the free node, then CPU jobs
fuzzball workflow log <forecast-id> extract -n 100     # counts only
fuzzball report charges workflow <forecast-id> -o json # GPU-hours
```

Write down: extract seconds, total seconds, new `made_at`, `forecast.json` carrying `life_support`, `yardstick`, `check_first` and the five `resources`. This warms the image on the forecast node. Also read `GET /api/runs` and confirm the **07:00 schedule row** exists if the twin was up at 07:00.

### T-30: chat and fallbacks

- Ask "How many ventilators will we need in the next 24 hours?" and "Room 7: what is most likely?" (Nemotron answers from counts and that room). Ask "rerun the forecast" and expect the guard's "last run was recent" reason.
- Start the laptop fallback in the frontend repo: `python3 -m http.server 8000`, open `http://localhost:8000/mockups/command-center.html` in a second tab.

### T-15: go / no-go

| Check | Go | No-go action |
|---|---|---|
| Our two nodes ready | yes | restart on the other node; if only one node: board plus forecast on it, no Nemotron (chat off) |
| `t7-twin` started, `board`, `nemotron`, `dispatcher` Started | yes | `describe`, `log`; restart `t7-twin` (minutes for Nemotron) |
| `forecast.json` and `rooms.json` < 24 h old, same run, 25 rooms | yes | press Update the unit; if refused, read the reason |
| `life_support` and `yardstick` present | yes | check the aggregate flags in the `score` job; the page shows "pending run" (acceptable) |
| Chat answers in < 10 s | yes | chat off, say so; counts and rooms still work |
| Update starts a workflow | yes | render and start by hand: see section 9 |
| Board opens on the presenter laptop | yes | laptop fallback |
| Held-out numbers on a slide exist | yes | drop the slide, not the demo |

### T-5 and T+0

Close other workflows that hold a GPU (`workflow list --status started`), open the board on the presenter laptop (not localhost), clear the chat, pick the role. During the demo: if the live launch is by the agent, it uses the demo MCP server (`claude mcp add fuzzball-demo -- fuzzball mcp serve --allow-exec`, never committed) to start `t7-forecast.fz` on the GPU Nemotron does not hold.

### Fallbacks

| Failure | Do |
|---|---|
| Cluster or API down | present the laptop page, say it is the same page on synthetic data; never claim it is live |
| Nemotron down or slow | board works; the chat says so; keep rooms, strain, rerun |
| Update refused or workflow errors | show the reason; the last good forecast stays; start by hand; if the node is bad, see section 2.5 |
| `t7-twin` token or CLI problem | the update button shows the reason; render and start `t7-forecast.fz` by hand (section 9) or through the demo MCP |
| `rooms.json` missing | room drawer on mock generator labelled SYNTHETIC |
| Stage list differs from the team's | use the script's list; say the digest |

### T+5

Record workflow ids and the three timings for the slides (every number from a run). Do **not** stop `t7-twin` until judging ends. After judging: stop workflows, delete what holds patient rows (`mimic_clif`, and `stage/` and `train/` on `twin-store`) per the wipe checklist in `docs/FUZZBALL_PLAN.md`; keep code, figures, aggregate results and the open stage-ward files.

---

## 7. Gap list: what is missing in code today

Size: XS under an hour, S a few hours, M most of a day.

| # | Gap | Owner lane | Size | State |
|---|---|---|---|---|
| G1 | Volume `twin-store` did not exist when checked on 2026-11-14 afternoon; every workflow stops without it. `clif_work` and `tooling` are no longer used | 2 | XS | create it once: `RUNBOOK.md`, section 1 |
| G2 | **fit** step after `t7-build`: extract all splits, `icutwin-rep-score`, drop the per-run refit from `t7-forecast.fz` | 3 + 2 | M | **done**: `fuzzball/t7-fit.fz` (validated), `t7-forecast.fz` only applies probes |
| G3 | **`t7-forecast.fz` v2**: stage-select, stage tokenize+winnow (cached), extract on the stage dir, `--apply-probes`, rooms, aggregate with `--baseline`; install polars/numpy into `/store/py` instead of `pip install` per run | 3 + 2 | M | **done** except the argument spelling of rooms.py and aggregate.py (TODO in the `score` job); no `pip` at run time, deps from `/store/py` |
| G4 | `app/rooms.py`: writes `rooms.json` (on now, five probabilities, level, last 12 h of readable events from the open demo tokens), rooms before forecast; with test | 3 | M | done (t7/fc-lookahead-forecast), contract in `docs/CONTRACT.md`, flags in section 1.5 |
| G5 | `app/stage_ward.py` | 3 | done | here, with tests; reconcile digest with team list (XS) |
| G6 | `app/board.py`: serve `app/static/index.html` read per request, `GET /api/rooms`, `room` on ask; chat agent loop | 4 | M | in progress (`t7/ui-chat-agent`) |
| G7 | `t7-twin.fz`: drop `depends-on nemotron` on the board; dispatcher CLI to a mounted volume (docs: binary larger than the writable layer); confirm `FB_UI_URL` | 2 | S | **done** in `t7-twin.fz`: board no longer depends on Nemotron, CLI on container-local tmpfs (`/dev/shm`, passed as `--cli "$CLI"`); `FB_UI_URL` still to confirm |
| G8 | Dispatcher: add `t7-smoke` and the fit workflow to the busy prefixes; `/status` shows whether a forecast is active | 2 + 4 | S | **done**: `t7-smoke`, `t7-fit` in the busy list; `/status` has `running` and `updating` |
| G9 | `t7-sync.fz`: code-only update from a git tag into `/store/code` (atomic directory swap) | 2 | S | open |
| G10 | `t7-preflight.fz`: CPU job that prints counts for the go/no-go list | 2 | S | open |
| G11 | Held-out metrics file (AUROC and calibration per task, counts only) for D7 and the chat | 3 | S | open (`summarize_preds` only logs) |
| G12 | Strain index and baseline | 3 | done | here, with tests; frontend reads `strain` (XS, lane 4), and its band words should come from the backend |
| G13 | `hypotension_init` is already true before the cut in about 95% of open-demo stays; check the MIMIC training rate and decide whether the board row stays | 1 + Vaishvik | S | open |
| G14 | Winnow override bug (`unknown option horizon_after_threshold_s`) | Vaishvik review | done | fixed here, tested |
| G15 | `made_at` with offset, atomic JSON writes | 3 | done | here, tested |
| G16 | How a judge's browser opens a `scope: group` endpoint (headers cannot be set from a URL); verify at T-60 | 2 | S | open |
| G17 | Time-to-run numbers, image warm-up, node health check of our two nodes | 2 | XS | at T-60 |

---

## 8. Open decisions for J.C.

1. **D10**: confirm option A (the 25 stage-ward rooms are the unit). Everything above assumes it.
2. **Hosting**: vendored static page, read from `/store/code` per request, `t7-sync` from a git tag (section 3). Alternative is fetching at start (rejected above).
3. **Stage-ward list**: adopt `app/stage_ward.py`'s selection (digest `9021f82b3b5d`) if it differs from the team-machine list.
4. **Honest framing**: label the board "replay of open demo patients" and say that a rerun repeats numbers unless the model changes. Or build a visible change (not planned).
5. **Hypotension row** (G13) once the MIMIC training rate is known.
6. **Strain definition**: five board tasks including death and leaving the ICU in the sum; mockup band cut-offs (0.8, 1.2, 1.6); "forecast summary, not a validated score".
7. **Go-ahead to create the volume `twin-store`** (G1; one volume, not three) and to run the fit step on the GPU after training.
8. **Who opens the board**: presenter laptop through `workflow connect` only, or a verified way for other devices (G16).

---

## 9. Later decisions: 07:00 run, unit and room updates, demo clock, capacity (runbook)

Decided by J.C. on 2026-11-14 (`docs/DECISIONS.md` D9). Code: `app/dispatcher.py`, `app/board.py`, `app/chat_agent.py`, `fuzzball/t7-forecast.fz`, `fuzzball/t7-fit.fz`, `fuzzball/t7-twin.fz`.

### 9.1 Order of workflows (one-time, then daily)

1. Training (vaishvikc/ICU-Twin, both GPUs) writes the model to `mimic_clif:/model_output/final/`; job 4 fits the probe; `t7-code` publishes this repo's `backend/`.
2. **`t7-fit`** (fallback, only when job 4 has not staged a probe): `stage` (CPU: stage-ward list, tokens, winnow, vocabulary check), `extract` (GPU, train/tuning/held_out), `fit` (CPU: probes saved to `/store/train/probe-final.joblib`). An update refuses to hold the GPU if the probes or the stage tokens are missing ("run t7-fit first").
3. `t7-twin` (Nemotron, board, dispatcher). The board no longer waits for Nemotron.
4. Daily: the dispatcher starts `t7-forecast` at **07:00 sharp** (dispatcher clock, zone-aware `America/Chicago`, so daylight saving moves nothing; window 07:00 to 07:00). If another run is active, the cluster cannot be listed, or the start fails, it retries every minute for 10 minutes and logs every attempt and the outcome to `runs.jsonl`. The 07:00 run ignores the 20 minute gap. A dispatcher that starts after 07:00 with no scheduled run since the cut runs it once (catch-up). Until it lands the board keeps the previous forecast and `/api/runs` says `updating: true`; a failed or missed scheduled run shows in `/api/runs` as `scheduled.state` = `failed` or `missed`: check it after 07:15 on demo day.

### 9.2 Updates on demand

| Who asks | Scope | Result |
|---|---|---|
| board "Update the unit", or chat "update the unit" / "rerun the forecast" | `unit` | extract, apply probes, `rooms.json`, `forecast.json` last |
| board "Update this room", or chat "update room 12" | `room` + number | extract, apply probes to that room, `rooms.json` only |

`t7-forecast.fz` is a **template**: Fuzzball 4.3 has no workflow parameters and `workflow start` has no `--set` (docs.ciq.com/fuzzball/4.3, workflow syntax; `fuzzball workflow start --help`), so the dispatcher replaces all six tokens, `@SCOPE@`, `@ROOM@`, `@HOURS@`, `@WARD_FLAG@`, `@CLIF_DIR@`, `@NAMES@`, refuses to start a copy that still has a token, and starts the copy (kept under `/store/rendered`, last 30). Names: `t7-forecast-MMDD-HHMM` (unit), `t7-forecast-room12-MMDD-HHMM`.

Guards (all tested without a cluster): one run at a time (any scope, `t7-forecast*`, `t7-build`, `t7-smoke`, `t7-fit`); 20 minutes between updates of one scope; the room gap is per room and a unit update also counts for every room. Refusals are plain words, for example "Updated 12 minutes ago. You can update again at 13:17.", "Room 12 updated 7 minutes ago. You can update again at 13:17.", "Another update is running (...); the two GPUs are in use. Try again in a few minutes." The gap is kept across a dispatcher restart (read from `runs.jsonl`) and is cleared when the listed run is seen to have failed within the gap. Two requests at once cannot both start (the first is tracked until the list shows it). A room update before any whole-ward run is refused ("No room data yet. Update the unit first, then a single room."). A forecast run is an update of the open demo ward by default; `--real-ward` on the dispatcher command (lane 2 only) renders `--real-ward` into the runs, for real MIMIC-IV room views, local only (D6). The log has time, role (or `schedule`), scope, room, workflow id and name; nothing else.

### 9.3 Demo clock

The stage ward is a replay: every room's cut is notionally 07:00. Each update advances the ward's cut by the time elapsed since the last 07:00 (dispatcher clock): an update at 11:30 passes `--demo-clock-hours 4.5` to `aggregate.py` and `rooms.py`; the 07:00 run passes 0. `/api/runs` returns the current offset and a label such as "Ward clock 11:30 (07:00 + 4.5 h)", and each last-run row carries its own. Say on stage that the ward is a replay and the clock moves; numbers change because the cut moves, not because new patients arrive.

### 9.4 Capacity

The charge nurse enters two whole numbers from 0 to 50 (life-support patients the unit can carry, ventilators free) with a role: `POST /api/capacity` writes `/store/capacity.json` (atomic); the next unit update passes it to `aggregate.py --capacity`; the page can also read `GET /api/capacity` to show TIGHT or SHORT now. The log line has time and role only, never the numbers. The chat reads it with `get_capacity`.

### 9.5 Start an update by hand (if the dispatcher or token is broken)

```bash
python scripts/render_fz.py fuzzball/t7-forecast.fz --scope unit -o /tmp/t7-forecast-manual.fz
fuzzball workflow validate /tmp/t7-forecast-manual.fz && fuzzball workflow start /tmp/t7-forecast-manual.fz --name t7-forecast-manual
```

`scripts/render_fz.py` is the code the dispatcher uses. It fills every token and exits 1, writing nothing, if one is left (a plain `sed` of four tokens leaves `@CLIF_DIR@` and `@NAMES@` in the file, and `precheck` then fails). Room: `--scope room --room 12 --hours 4.5`. The final cohort: add `--real-ward --clif-dir /data/dashboard_data --names /data/dashboard_data/name.parquet`. Without Python, all six tokens by hand:

```bash
sed 's/@SCOPE@/unit/;s/@ROOM@/0/;s/@HOURS@/0/;s/@WARD_FLAG@//;s/@NAMES@//;s#@CLIF_DIR@#/store/code/clif_demo#' fuzzball/t7-forecast.fz > /tmp/t7-forecast-manual.fz
grep -c '@[A-Z_]*@' /tmp/t7-forecast-manual.fz    # must print 0
```

Always pass `--name t7-forecast-...`: the dispatcher's one-run-at-a-time guard goes by the name, and an unnamed run is named after its file. Ask lane 2 before starting anything.

### 9.5a Final cohort (the 25 demo patients)

Nothing in this section is started until training (`t7-build`) has finished. Step by step, with commands: `FUZZBALL_TEST_PLAN.md`.

**What it is.** A CLIF extract of 25 real MIMIC-IV stays: 19 `clif_*.parquet` tables, `dashboard_patients_unit25.parquet` (one column, `hospitalization_id`) and `name.parquet` (made-up names; it holds real ids; no longer read, names are generated per room number). On the laptop it is `backend/data/local/unit25/`, which git ignores. It never goes into the repo, a commit, a log, a screenshot or a public host.

**Where it is on the cluster.** `/data/dashboard_data/` on the team volume `mimic_clif`, since 2026-11-14 (19 tables, the id file, `name.parquet`). The workflows only read it. Never the code tree.

**Getting it there: done.** A teammate's workflow built the folder on the cluster and `name.parquet` (made-up names) was placed by two small jobs; nothing is left to copy.

Check it with `t7-ward` job `load` (counts only), not by listing files by hand.

**Order after training finishes.**

1. `t7-fit` (once per model): saves the probes. It stages the open demo ward by default.
2. `t7-ward`, rendered for the cohort: job `load` checks the folder, the table list, the 25 ids and the names file; job `tokenize` builds the room map and the tokens with the training vocabulary and swaps them into `/store/stage/`.
3. `t7-twin` from `fuzzball/ready/t7-twin.fz` (its dispatcher line already ends in `--real-ward --clif-dir /data/dashboard_data --names fake`: names are generated per room number, `name.parquet` is no longer read).
4. The first unit forecast ("Update the unit", or 07:00). It writes `rooms.json` and `forecast.json` with `"ward": {"source": "mimic-iv", ...}`.

```bash
fuzzball workflow validate fuzzball/ready/t7-ward.fz && fuzzball workflow start fuzzball/ready/t7-ward.fz --name t7-ward
```

Rendered with no options, `t7-ward` puts the open demo ward back.

**Rooms.** Rooms 1 to 25 follow a seeded shuffle of the ids (`stage_ward.py --ward-ids`, seed 20261114): the same map on the laptop and on the cluster, and a room number says nothing about the id or the admission date.

**One day for all 25.** Each patient is cut on that patient's own clock (first ICU arrival + 24 h + the demo clock); the board shows all of them at one 07:00 (`CONTRACT.md`, "Shared demo day"). When the demo clock advances, every patient advances by the same hours, and a patient whose ICU stay has ended drops out of the ward. The cohort thins quickly, so pick the clock from `scripts/run_cohort.py ... --cut-table 0,6,12,24,48,72` on the laptop (counts only; the numbers stay out of this public repo).

**Until the model exists** the laptop run shows the Now side with every prediction pending (`README.md`, "Run the final cohort on a laptop").

### 9.6 Rehearsal additions at T-45

Press "Update this room" on one room and "Update the unit" 21 minutes later; check refusal wording by pressing again early; set capacity and watch the next unit update carry it; read `GET /api/runs` for `last.unit`, `last.room`, `demo_clock_label`, `next_scheduled` (next 07:00).

### 9.7 Pinned code, locked deps, pinned model (supply chain)

`t7-build.fz` and `t7-smoke.fz` do not pull a moving branch. Their ingress is the tarball of one commit, `https://codeload.github.com/vaishvikc/ICU-Twin/tar.gz/<CODE_REF>`, and the setup (and prefetch) step checks its sha256 before unpacking; a file that still has the placeholders refuses to run. Before `validate` / `start`:

```bash
REF=<40-hex commit sha, already on GitHub, containing requirements/t7-*.txt>
SHA=$(curl -sL https://codeload.github.com/vaishvikc/ICU-Twin/tar.gz/$REF | sha256sum | cut -d' ' -f1)
for f in t7-build t7-smoke; do sed "s/@CODE_REF@/$REF/g;s/@CODE_SHA256@/$SHA/g" fuzzball/$f.fz > /tmp/$f.fz; done
fuzzball workflow validate /tmp/t7-build.fz && fuzzball workflow start /tmp/t7-build.fz
```

(`CODE_REF` and `CODE_SHA256` are those two tokens; Fuzzball 4.3 has no variables.) GitHub does not promise byte-identical archives forever: on a mismatch, check the commit, then recompute the hash. Python packages install from `requirements/t7-model.txt`, `t7-gen.txt`, `t7-prefetch.txt` (hash-pinned, aarch64 Linux, Python 3.12, `pip install --no-deps --require-hashes`; regenerate from the `.in` files with the command in each header, then drop torch, triton and the nvidia wheels). Nemotron is pinned to Hugging Face commit `9bee19446c0dfd01f356e10979d225b2a6621944` (looked up 2026-11-14 through the model API) in both `t7-smoke` (download) and `t7-twin` (`--revision`, `--code-revision`). The dispatcher's Fuzzball CLI is checked against `FB_CLI_SHA256` (env in `t7-twin.fz`; unset: warning and the hash it got).

### 9.8 Who can press what

There is no login. `role` is advisory: it labels the log and the answer, and it is not authorization. The guards against a stray or hostile page are the `X-Lookahead` header, JSON content type and Origin match on every POST, the 20 minute gap, the one-run-at-a-time rule, and the team-scoped endpoint. Responses carry `X-Frame-Options: DENY`, a strict `Content-Security-Policy` and `X-Content-Type-Options: nosniff`.

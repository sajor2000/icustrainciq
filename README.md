# ICU Horizon: From bench to bedside

A bed board that tells a small ICU at 07:00 what the next 24 hours will need. Team7, CIQ × NVIDIA × Lenovo Local AI Hackathon, Chicago, Nov 14–15, 2026.

> **The demo runs from the team's ICU-Twin repo ([github.com/vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin)). Do not run `launch.sh` from this repo; its `ready/` files would overwrite the team's code on the shared volume.**

## For the team

| Read | For |
|---|---|
| [`docs/ICU_TWIN_DELTA.md`](docs/ICU_TWIN_DELTA.md) | **The morning decision:** every change in this repo against ICU-Twin, its risk to the running demo, and what to port before or after the demo |
| [`docs/UI_REVIEW.md`](docs/UI_REVIEW.md) | Each change to the team's board page, with before and after pictures and how to undo it |
| [`HANDOFF.md`](HANDOFF.md) | Where things stand, who owns what, the morning steps |
| [`docs/HOW_WE_USED_CIQ.md`](docs/HOW_WE_USED_CIQ.md) | **Exactly how we used CIQ Fuzzball, the Lenovo PGX machines and NVIDIA software**, read from the team's demo code (`t7/fb-job5-launch`): every workflow, image, volume and GPU |
| [`docs/MODEL_EXPLAINED.md`](docs/MODEL_EXPLAINED.md) | The model we trained (it speaks EHR, not English) and how its last hidden layer gives the five predictions, in two minutes for judges |
| [`docs/submission/AB_TEST.md`](docs/submission/AB_TEST.md) | Two one-page handouts, A (HTML) and B (LaTeX), for the team to pick one |
| [`docs/proposals/`](docs/proposals/README.md) | A proposed README for ICU-Twin and what we found reading its code; nothing applied there |

**Project page with every figure and screenshot:** https://sajor2000.github.io/icustrainciq/ · **Taking this over?** Start with [`HANDOFF.md`](HANDOFF.md).

## The problem

A small or rural hospital has one ICU, a few ventilators and dialysis machines, no data-science team and no cloud contract for patient data. When the unit runs short, the nearest help is a transfer hours away. The team learns it is short when it already is.

ICU Horizon answers one question each morning: who is on life support now, who is likely to need it by tomorrow, and does the unit have the machines and staff for that. It runs in the building, so patient data never leaves.

> **Key.** ICU: the intensive care unit. Life support: a machine or drug that does the work of a failing organ. Ventilator: breathes for the patient. Vasopressor: a drug drip that holds blood pressure up. CRRT: continuous dialysis, for failed kidneys.

## How we used the stack

![Two Lenovo machines run by CIQ Fuzzball: one GPU serves NVIDIA Nemotron 3 Nano, the other runs our patient model](docs/diagrams/stack.png)

- **Lenovo ThinkStation PGX × 2, each with an NVIDIA GB10.** The whole product runs on these two desk-size machines. Nothing is in the cloud.
- **CIQ Fuzzball 4.3.** In the team's demo code, five workflows: jobs 1 to 4 move the CLIF data in, tokenize it, train our model on both GPUs and fit six probes; job 5 (`t7-launch`) infers the 25-patient ward on one GPU, writes the forecast, then serves the board and Nemotron. Three volumes on VAST storage: `mimic_clif` (patient data and the trained model), `hfcache` (Nemotron weights) and `twin-store` (the forecast). A new forecast means starting job 5 again. Details: [`docs/HOW_WE_USED_CIQ.md`](docs/HOW_WE_USED_CIQ.md). This repo's older `t7-*` workflows and dispatcher, described below, are not the demo path.
- **NVIDIA Nemotron 3 Nano on vLLM.** It answers questions in the chat. We use it as it is; we did not train it. It reads the forecast and predicts nothing.
- **Our patient model.** We trained it on the two machines, across both GPUs, on MIMIC-IV in CLIF format. It runs in the forecast job on one GPU while Nemotron holds the other.

Two models, two jobs: ours knows ICU data and makes the forecast; NVIDIA's knows language and explains it.

## What we did

![Chart data, our patient model, five classifiers, the board, the chat](docs/diagrams/flow.png)

- **Trained a patient model** that reads a chart as a sequence of events. At 07:00 it reads each patient once; we keep its last layer.
- **Fitted five small classifiers** on that layer: ventilator, vasopressor, CRRT, leaving the ICU, death, each as a chance for the next 24 hours. Training fits them once, beside the model (job 4), and the forecast applies the saved file; it never refits. The cohort is ICU patients, cut 24 hours after ICU arrival.
- **Built the board** (the team's final board design): every bed shows life support now, then the next 24 hours. A "See first" row names the three beds most likely to need a new life support. An event shows in a circle with its chance once it reaches the threshold set in Settings, and the bed's person icon turns red and pulses when a new life support reaches it. Death never marks a bed: it is one count for the unit, and a row when a bed is opened. A bed opens a pop-up with its five chances and the last 12 hours of vital signs. Unit strain has one card per event, with the unit forecast and its range, against the ventilators and CRRT machines the unit has. Now and Next 24 h switch with a swipe. "Update the unit" shows the job's progress (Queued, Running on the GPU, Scoring, Done). Names on the tiles are generated and fictional.
- **Built the services**: a board server, a dispatcher that starts the 07:00 run and the on-request runs, and a chat agent that answers from the forecast through tools.
- **Wrote the Fuzzball workflows**: publish the code (`t7-code`), stage the unit (`t7-ward`), the forecast (`t7-forecast`: a check, one model pass on one GPU, scoring) and the services (`t7-twin`), as ready-to-run files in `backend/fuzzball/ready/`. `t7-fit` stays only as a fallback for when training's job 4 has not run. One script, `backend/scripts/launch.sh`, runs what is needed and prints the board's link.
- **Tested it**: 459 backend tests pass: 431 with `cd backend && uv run --extra dev --extra model pytest -q`, and 28 more that drive the page in a real browser (`uv run --extra dev --extra model --with playwright python -m pytest -q`).
- **Where it stands**: it ran end to end on the two Lenovo machines under Fuzzball with one launch script (the team's run on 2026-11-14, from ICU-Twin). The demo patients and the trained model are on the cluster. The steps, what each leaves on the cluster and the failures already met there are in the [runbook](backend/docs/RUNBOOK.md). The board also runs on a laptop with made-up data.

## How well it predicts

On held-out patients (cut at ICU arrival + 24 h, event in the next 24 h): AUROC **0.93** for death, **0.88** for leaving to step-down, **0.88** for CRRT start, **0.80** for leaving to a ward, **0.78** for ventilator start and **0.77** for vasopressor start. Full table with ranges, AUPRC and Brier: [`docs/RESULTS.md`](docs/RESULTS.md).

![Held-out AUROC by task, with 95% ranges](docs/diagrams/results-auroc.png)

## How this forecast was made

Not a medical device and not prospectively validated. The board shows staffing and machine needs, not treatments.

**A native model.** The predictions come from one model we trained ourselves (the team calls it GEM), from scratch, on our own vocabulary of patient-event tokens (about 1,200: lab bins, drug starts, transfers, time gaps, a clock token) built from MIMIC-IV-Ext-CLIF patient timelines. It is not fine-tuned and starts with no pretrained weights, from Google or from NVIDIA. We borrowed the layer pattern of NVIDIA Nemotron 3.5 Bolt E4B (Gemma4 text), not a copy of the model. In ICU-Twin `icutwin/config/decoder.yaml`, size m has 16 layers, every sixth one full attention (the last layer is always full) and the rest sliding-window, with grouped-query attention, key/value shared across the last layers, per-layer input embeddings and logit softcapping. The config defines three sizes: s (12.3M parameters at a vocabulary of 1,200), m (about 35M) and l (about 70M). Training uses size m with a time-to-next-token loss added to next-token loss. The config plans 3 epochs. The checkpoint packaged as the model folder is step 2616 of 4351 from run `ep2-20261114c`; the training runs were canceled (`backend/docs/FUZZBALL_VALIDATION.md`, `HANDOFF.md`). Which checkpoint is the demo model is still an open decision (`HANDOFF.md`, open decision 3).

**From chart to prediction.**
1. *Read the chart.* The patient's last 4,096 events before the cut become a list of tokens. The cut is 24 hours after ICU arrival when the classifiers are fit, and 07:00 on the board. On `main` today the winnow step cuts at ICU arrival + 24 h; the separate `examples/winnow_24h.yaml` config is gone (PR 19, merged).
2. *One pass through the model.* It reads the list once and does not write out the next 24 hours. At the last event it holds a summary of the patient so far, the hidden state of the last layer (`icutwin/scoring/extractor.py`, `hidden_states[-1]` at the last real token).
3. *Small classifiers on that summary.* A probe is a small classifier on the hidden state: standardized features into logistic regression with cross-validation (`icutwin/scoring/rep_based.py`). There are six heads (ward, step-down, IMV, vasopressor start, CRRT start, death; `examples/probe_tasks.yaml`) for five board predictions; ward plus step-down is ICU discharge. Each was fit on past stays, labelled by what really happened in the 24 hours after the cut, skipping stays where the event had already happened. A patient with the support already running gets no new-start prediction for it. The forecast reads the fitted probes from `/store/train/probe-final.joblib`, which comes from job 4 (`workflows/job_4_probe` in ICU-Twin) with a provenance sidecar (`probe.meta.json`) that `apply_probes` checks against the model; `t7-fit` is the fallback when job 4 has not run (`backend/docs/RUNBOOK.md`). The board shows each chance as a whole percentage ("23%", "<5%") on every screen (D14).
4. *Add up the patients.* `app/aggregate.py` turns per-patient chances into unit counts with a likely range (8 in 10), a model-based range that treats patients as independent. The board flags a bed at 40% (worsening), 20% (watch) and 60% (leaving) by default (D13, D14). The page presets 40 / 20 / 10 and has a "Reset to standard"; D22 adds a per-device toggle for the flag line, kept on that device only.

The first design generated about 100 sampled futures per patient and counted outcomes; we dropped it (decision D2) for one forward pass per patient.

**Results.** Held-out AUROC runs from 0.77 (vasopressor start) to 0.93 (death) across the six heads: [`docs/RESULTS.md`](docs/RESULTS.md). It is a retrospective check on one dataset, MIMIC-IV. `docs/RESULTS.md` does not say which checkpoint it scored. Backtest against persistence and GB10 run times: Not ready yet. The job 4 status table in ICU-Twin has no recorded run.

**Fuzzball: what ran, and what is only written.** Two Lenovo ThinkStation PGX nodes (NVIDIA GB10, one GPU each); the scheduler places work, so nothing is pinned to a named node, and no node names are recorded in the repos.

*Ran on the cluster:*
- Data move: the CLIF files went through the team-only object cache onto the persistent volume `mimic_clif` (`workflows/job_1_data_move` in ICU-Twin; `docs/FUZZBALL_RUNS.md`).
- A training run on both nodes (the `workflows/job_3_train` shape: `multinode`, 2 nodes, data-parallel). It was stopped at the checkpoint above.
- Packaging that checkpoint into the model folder `final/`, with a load test that printed `LOADTEST OK` (`workflows/job_3_1_package`).
- Probe fitting and held-out scoring: `docs/RESULTS.md` says the model was trained and run on the two local PGX machines, but the job status tables record no job 4 or `t7-fit` run, so which workflow produced the numbers is not recorded here.
- The whole app, end to end, with `launch.sh` on 2026-11-14: the team ran it from the ICU-Twin repo (`HANDOFF.md`, Status). The list below is about this repo's own rendered workflow files, which have not run.

*Written, validated against the cluster with a stand-in for the missing volume, not yet run* (`backend/fuzzball/ready/`, `HANDOFF.md`; `FUZZBALL_VALIDATION.md` says no workflow in this repo has run, and `twin-store` was missing on 2026-11-14; the ready files must be re-rendered after the sync merge):
- `t7-code` publishes the board code, `t7-fit` (fallback to job 4) fits the probes, `t7-ward` stages the 25 open-demo rooms, `t7-forecast` is built to run one update (extract on one GPU, score on CPU).
- `t7-twin` is built to hold three services: Nemotron 3 Nano on one GPU (chat), the board on port 8080 (https endpoint, group scope) and a dispatcher.
- The dispatcher is designed to start the forecast early enough to be ready for 07:00 rounds (it is set to start at 07:00 and retry for 10 minutes; decision D9 says 06:30) and on "Update the unit": it fills a copy of the Fuzzfile and runs `workflow start`, one run at a time, 20 minutes between updates of the same scope. It is designed to use the workflow token Fuzzball injects because Fuzzball 4.3 has no built-in cron. Both are design to confirm on the cluster.

Volumes: `mimic_clif` (credentialed data, the model, training tokens), `twin-store` (code, probes, forecast files), `hfcache` (Nemotron weights), and scratch volumes Fuzzball removes at the end of a workflow. Results an agent reads back leave through the object cache, which never overwrites. More: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**Privacy.** Real MIMIC-IV stays counts-only by default. D19 allows real-ward views locally under the team's data agreement. Rooms shown by default are the open MIMIC-IV Demo stage ward (D6).

## The board

![Bed board, Next 24 h: a See first row with the three highest-risk beds, then each bed with life support now and the events at their thresholds; a red person icon marks a bed with a new life support at its threshold](docs/screenshots/beds-next.png)

| Now: life support running at 07:00 | Unit strain: one card per event, against the unit's machines |
|---|---|
| ![Bed board, Now](docs/screenshots/beds-now.png) | ![Unit strain, Next 24 h](docs/screenshots/strain-next.png) |

![Ask ICU Horizon: the chat answers from the forecast](docs/screenshots/chat-widget.png)

![Update the unit: Queued, Running on the GPU, Scoring, Done](docs/screenshots/update-progress.png)

## Where the patient data lives

The patient tables stay on Fuzzball volumes inside the two machines. The clinician's browser gets the unit counts and one entry per room: the five chances, the last events the model read and 12 hours of vital signs. The chat model gets tool results only. GitHub holds code only.

![Patient tables stay on Fuzzball volumes inside the two machines; unit counts and room entries reach the clinician's browser; the chat model sees tool results only](docs/diagrams/data-boundary.png)

## Run it

```bash
# 1. The board with made-up data (own terminal; it keeps running)
python3 -m http.server 8000        # open http://localhost:8000/mockups/command-center.html#synthetic

# 2. Backend tests, from the repo root
(cd backend && uv run --extra dev --extra model pytest -q)

# 3. The board server on example data (own terminal; it keeps running)
(cd backend && uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080)

# 4. On the cluster: run these from the team's ICU-Twin checkout, NOT from this repo (see the notice at the top).
#    The same script lives here in backend/scripts/ for reference (backend/docs/RUNBOOK.md).
bash scripts/launch.sh             # start what is missing, wait for the board, print its HTTPS link
bash scripts/launch.sh --forecast  # run a fresh forecast first
bash scripts/launch.sh --link      # print the link of the running board
bash scripts/launch.sh --restart   # stop t7-twin and start it again
bash scripts/launch.sh --all       # publish code, stage the unit, forecast, then the board
```

## More

- **Project page:** https://sajor2000.github.io/icustrainciq/ (how it predicts, all screenshots, architecture, run steps)
- **[`HANDOFF.md`](HANDOFF.md):** where things stand, who owns what, the morning steps
- **[`docs/ICU_TWIN_DELTA.md`](docs/ICU_TWIN_DELTA.md):** this repo against ICU-Twin, and what to port
- **[`docs/RESULTS.md`](docs/RESULTS.md):** held-out results per task
- **[`docs/ONE_PAGER.md`](docs/ONE_PAGER.md):** the model and how Fuzzball ran it, in one page for judges ([HTML](docs/ONE_PAGER.html))
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md):** what runs where, tech stack, endpoints
- **[`docs/submission/`](docs/submission/):** the one-sheet and the five-minute demo script
- **[`backend/README.md`](backend/README.md):** the backend, module by module
- **Design system:** [`DESIGN.md`](DESIGN.md) is the one source for the board, the figures and the project page
- **Model training:** [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin)
- **Runbook:** [`backend/docs/RUNBOOK.md`](backend/docs/RUNBOOK.md): set up, publish code and relaunch the board on the cluster (`backend/scripts/launch.sh`)

## Team 7 - CLIF

We built ICU Horizon together, as one team. Names and affiliations as listed by the [CLIF Consortium](https://clif-icu.com/team).

| Name | Affiliation |
|---|---|
| J.C. Rojas, MD, MS | Rush University |
| Kaveri Chhikara, MS | UChicago Medicine |
| Vaishvik Chaudhari, MS | Rush University |
| Dema Therese, MS | UChicago Medicine |
| Zewei ('Whiskey') Liao, MS | UChicago Medicine |

Demo data only: the mockup uses made-up patients, and names on the board are fictional. ICU Horizon is a research prototype, not a medical device; it supports decisions and recommends no treatment.

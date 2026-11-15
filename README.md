# ICU Lookahead: see the next 24 hours of your ICU, on machines you own

A bed board that tells a small ICU at 07:00 what the next 24 hours will need. Team7, CIQ × NVIDIA × Lenovo Local AI Hackathon, Chicago, Nov 14–15, 2026.

**Project page with every figure and screenshot:** https://sajor2000.github.io/icustrainciq/ · **Taking this over?** Start with [`HANDOFF.md`](HANDOFF.md).

## The problem

A small or rural hospital has one ICU, a few ventilators and dialysis machines, no data-science team and no cloud contract for patient data. When the unit runs short, the nearest help is a transfer hours away. The team learns it is short when it already is.

ICU Lookahead answers one question each morning: who is on life support now, who is likely to need it by tomorrow, and does the unit have the machines and staff for that. It runs in the building, so patient data never leaves.

> **Key.** ICU: the intensive care unit. Life support: a machine or drug that does the work of a failing organ. Ventilator: breathes for the patient. Vasopressor: a drug drip that holds blood pressure up. CRRT: continuous dialysis, for failed kidneys.

## How we used the stack

![Two Lenovo machines run by CIQ Fuzzball: one GPU serves NVIDIA Nemotron 3 Nano, the other runs our patient model](docs/diagrams/stack.png)

- **Lenovo ThinkStation PGX × 2, each with an NVIDIA GB10.** The whole product runs on these two desk-size machines. Nothing is in the cloud.
- **CIQ Fuzzball 4.3.** Workflows fit the classifiers, stage the unit and run each forecast. Services keep the board server, the dispatcher and the chat model up. Volumes hold the patient data, the model and the results. The board's "Update the unit" button starts a Fuzzball job.
- **NVIDIA Nemotron 3 Nano on vLLM.** It answers questions in the chat. We use it as it is; we did not train it. It reads the forecast and predicts nothing.
- **Our patient model.** We trained it on the two machines, across both GPUs, on MIMIC-IV in CLIF format. It runs in the forecast job on the second GPU.

Two models, two jobs: ours knows ICU data and makes the forecast; NVIDIA's knows language and explains it.

## What we did

![Chart data, our patient model, five classifiers, the board, the chat](docs/diagrams/flow.png)

- **Trained a patient model** that reads a chart as a sequence of events. At 07:00 it reads each patient once; we keep its last layer.
- **Fitted five small classifiers** on that layer: ventilator, vasopressor, CRRT, leaving the ICU, death, each as a chance for the next 24 hours.
- **Built the board**: every bed shows now, then the next 24 hours, with one status; "Worry first" lists the beds to see first; Unit strain adds the patients up with a range and compares them with tonight's machines and staff.
- **Built the services**: a board server, a dispatcher that starts the 07:00 run and the on-request runs, and a chat agent that answers from the forecast through tools.
- **Wrote the Fuzzball workflows**: setup (`t7-code`, `t7-fit`, `t7-ward`), services (`t7-twin`) and the forecast (`t7-forecast`), as ready-to-run files in `backend/fuzzball/ready/`. The six files on the run path passed `fuzzball workflow validate` against the live cluster, with a stand-in for the one volume still to create.
- **Tested it**: 249 backend tests pass (`cd backend && uv run --extra dev --extra model pytest -q`).
- **Where it stands**: the demo patients and the trained model are on the cluster. Nothing of ours has run end to end on the cluster yet; the board runs today on a laptop with made-up data. The run list is in [`HANDOFF.md`](HANDOFF.md).

## How well it predicts

On held-out patients (cut at ICU arrival + 24 h, event in the next 24 h): AUROC **0.93** for death, **0.88** for leaving to step-down, **0.88** for CRRT start, **0.80** for leaving to a ward, **0.78** for ventilator start and **0.77** for vasopressor start. Full table with ranges, AUPRC and Brier: [`docs/RESULTS.md`](docs/RESULTS.md).

## How this forecast was made

Not a medical device and not prospectively validated. The board shows staffing and machine needs, not treatments.

**A native model.** The predictions come from one model we trained ourselves (the team calls it GEM), from scratch, on our own vocabulary of patient-event tokens (about 1,200: lab bins, drug starts, transfers, time gaps, a clock token) built from MIMIC-IV-Ext-CLIF patient timelines. It is not fine-tuned and starts with no pretrained weights, from Google or from NVIDIA. We borrowed the layer pattern of NVIDIA Nemotron 3.5 Bolt E4B (Gemma4 text), not a copy of the model. In ICU-Twin `icutwin/config/decoder.yaml`, size m has 16 layers, every sixth one full attention (the last layer is always full) and the rest sliding-window, with grouped-query attention, key/value shared across the last layers, per-layer input embeddings and logit softcapping. The config defines three sizes: s (12.3M parameters at a vocabulary of 1,200), m (about 35M) and l (about 70M). Training uses size m with a time-to-next-token loss added to next-token loss. The config plans 3 epochs. The checkpoint packaged as the model folder is step 2616 of 4351 from run `ep2-20261114c`; the training runs were canceled (`backend/docs/FUZZBALL_VALIDATION.md`, `HANDOFF.md`). Which checkpoint is the demo model is still an open decision (`HANDOFF.md`, open decision 3).

**From chart to prediction.**
1. *Read the chart.* The patient's last 4,096 events before the cut become a list of tokens. The cut is 24 hours after ICU arrival when the classifiers are fit, and 07:00 on the board. On `main` today the winnow step cuts at ICU arrival + 24 h; the separate `examples/winnow_24h.yaml` config is gone (PR 19, merged).
2. *One pass through the model.* It reads the list once and does not write out the next 24 hours. At the last event it holds a summary of the patient so far, the hidden state of the last layer (`icutwin/scoring/extractor.py`, `hidden_states[-1]` at the last real token).
3. *Small classifiers on that summary.* A probe is a small classifier on the hidden state: standardized features into logistic regression with cross-validation (`icutwin/scoring/rep_based.py`). There are six heads (ward, step-down, IMV, vasopressor start, CRRT start, death; `examples/probe_tasks.yaml`) for five board predictions; ward plus step-down is ICU discharge. Each was fit on past stays, labelled by what really happened in the 24 hours after the cut, skipping stays where the event had already happened. A patient with the support already running gets no new-start prediction for it. The forecast reads the fitted probes from `/store/train/probe-final.joblib`, which comes from job 4 (`workflows/job_4_probe` in ICU-Twin) with a provenance sidecar (`probe.meta.json`) that `apply_probes` checks against the model; `t7-fit` is the fallback when job 4 has not run (`backend/docs/RUNBOOK.md`). The board shows each chance as a whole percentage ("23%", "<5%") on every screen (D14).
4. *Add up the patients.* `app/aggregate.py` turns per-patient chances into unit counts with a likely range (8 in 10), a model-based range that treats patients as independent. The board flags a bed at 40% (worsening), 20% (watch) and 60% (leaving) by default (D13, D14); D22 adds a per-device toggle for the flag line.

The first design generated about 100 sampled futures per patient and counted outcomes; we dropped it (decision D2) for one forward pass per patient.

**Results.** Held-out AUROC runs from 0.77 (vasopressor start) to 0.93 (death) across the six heads: [`docs/RESULTS.md`](docs/RESULTS.md). It is a retrospective check on one dataset, MIMIC-IV. `docs/RESULTS.md` does not say which checkpoint it scored. Backtest against persistence and GB10 run times: Not ready yet. The job 4 status table in ICU-Twin has no recorded run.

**Fuzzball: what ran, and what is only written.** Two Lenovo ThinkStation PGX nodes (NVIDIA GB10, one GPU each); the scheduler places work, so nothing is pinned to a named node, and no node names are recorded in the repos.

*Ran on the cluster:*
- Data move: the CLIF files went through the team-only object cache onto the persistent volume `mimic_clif` (`workflows/job_1_data_move` in ICU-Twin; `docs/FUZZBALL_RUNS.md`).
- A training run on both nodes (the `workflows/job_3_train` shape: `multinode`, 2 nodes, data-parallel). It was stopped at the checkpoint above.
- Packaging that checkpoint into the model folder `final/`, with a load test that printed `LOADTEST OK` (`workflows/job_3_1_package`).
- Probe fitting and held-out scoring: `docs/RESULTS.md` says the model was trained and run on the two local PGX machines, but the job status tables record no job 4 or `t7-fit` run, so which workflow produced the numbers is not recorded here.

*Written, validated against the cluster with a stand-in for the missing volume, not yet run* (`backend/fuzzball/ready/`, `HANDOFF.md`; `FUZZBALL_VALIDATION.md` says no workflow in this repo has run, and `twin-store` was missing on 2026-11-14; the ready files must be re-rendered after the sync merge):
- `t7-code` publishes the board code, `t7-fit` (fallback to job 4) fits the probes, `t7-ward` stages the 25 open-demo rooms, `t7-forecast` is built to run one update (extract on one GPU, score on CPU).
- `t7-twin` is built to hold three services: Nemotron 3 Nano on one GPU (chat), the board on port 8080 (https endpoint, group scope) and a dispatcher.
- The dispatcher is designed to start the forecast early enough to be ready for 07:00 rounds (it is set to start at 07:00 and retry for 10 minutes; decision D9 says 06:30) and on "Update the unit": it fills a copy of the Fuzzfile and runs `workflow start`, one run at a time, 20 minutes between updates of the same scope. It is designed to use the workflow token Fuzzball injects because Fuzzball 4.3 has no built-in cron. Both are design to confirm on the cluster.

Volumes: `mimic_clif` (credentialed data, the model, training tokens), `twin-store` (code, probes, forecast files), `hfcache` (Nemotron weights), and scratch volumes Fuzzball removes at the end of a workflow. Results an agent reads back leave through the object cache, which never overwrites. More: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**Privacy.** Real MIMIC-IV stays counts-only by default. D19 allows real-ward views locally under the team's data agreement. Rooms shown by default are the open MIMIC-IV Demo stage ward (D6).

## The board

![Bed board, Next 24 h: each bed shows now, then the forecast](docs/screenshots/beds-next.png)

| Now: life support running at 07:00 | Unit strain: the unit added up |
|---|---|
| ![Bed board, Now](docs/screenshots/beds-now.png) | ![Unit strain, Next 24 h](docs/screenshots/strain-next.png) |

![Ask ICU Lookahead: the chat answers from the forecast](docs/screenshots/chat-widget.png)

## Run it

```bash
# 1. The board with made-up data (own terminal; it keeps running)
python3 -m http.server 8000        # open http://localhost:8000/mockups/command-center.html#synthetic

# 2. Backend tests, from the repo root
(cd backend && uv run --extra dev --extra model pytest -q)

# 3. The board server on example data (own terminal; it keeps running)
(cd backend && uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080)
```

## More

- **Project page:** https://sajor2000.github.io/icustrainciq/ (how it predicts, all screenshots, architecture, run steps)
- **[`HANDOFF.md`](HANDOFF.md):** where things stand, who owns what, the cluster run list
- **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md):** what runs where, tech stack, endpoints
- **[`docs/submission/`](docs/submission/):** the one-sheet and the five-minute demo script
- **[`backend/README.md`](backend/README.md):** the backend, module by module
- **Design system:** [`DESIGN.md`](DESIGN.md) is the one source for the board, the figures and the project page
- **Model training:** [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin)
- **Runbook:** [`backend/docs/RUNBOOK.md`](backend/docs/RUNBOOK.md): set up, publish code and relaunch the board on the cluster (`backend/scripts/launch.sh`)

## Team 7 - CLIF

All four are members of the [CLIF Consortium](https://clif-icu.com/team); the roles and institutions in the second column are as listed there.

| Name | CLIF Consortium | On this project |
|---|---|---|
| J.C. Rojas, MD | Founding Vice-Chair, Steering Committee · Rush University | Product, board and chat, Fuzzball workflows, docs ([sajor2000](https://github.com/sajor2000)) |
| Kaveri Chhikara, MS | Vice-chair for Software Development, Steering Committee · UChicago Medicine | Forecast pipeline on the cluster, dispatcher, launch script and runbook |
| Vaishvik Chaudhari, MS | Vice-chair and Technical Lead, Steering Committee · Rush University | The patient model: tokenizer, training, the ICU + 24 h cut, probes ([vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin)) |
| Dema Therese, MS | UChicago Medicine | Board design: bed tiles coloured by status, event cards, bed pop-up with vitals, settings, the capacity model |

Demo data only: the mockup uses made-up patients, and names on the board are fictional. ICU Lookahead is a research prototype, not a medical device; it supports decisions and recommends no treatment.

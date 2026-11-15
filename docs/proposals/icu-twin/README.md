# ICU-Twin · ICU Horizon

**Five predictions for every ICU patient, for the next 24 hours, made on two computers inside the hospital.**

Team 7 · CLIF · CIQ × NVIDIA × Lenovo Local AI Hackathon · Chicago · Nov 14–15, 2026

ICU-Twin is the code; ICU Horizon is the bed board it serves. A patient model we trained from scratch reads each ICU patient's chart as a sequence of clinical events. Six small classifiers on that model give five chances for the next 24 hours, and the board adds them up into what the unit will need. Everything runs on two NVIDIA GB10 machines under CIQ Fuzzball. No patient data leaves the cluster.

## The five predictions

Each is the chance the event happens in the next 24 hours, for a patient cut 24 hours after ICU arrival. Held-out AUROC on MIMIC-IV in CLIF, with 95% bootstrap ranges:

| Prediction | Who plans for it | Classifier (`examples/probe_tasks.yaml`) | Held-out AUROC |
|---|---|---|---|
| Starts a ventilator | Respiratory therapy | `RESP//device_category//imv` | 0.780 (0.747–0.812) |
| Starts a vasopressor | Pharmacy | `LABEL//pressor_init` | 0.771 (0.739–0.802) |
| Starts CRRT | ICU team | `LABEL//crrt_init` | 0.881 (0.850–0.910) |
| Leaves the ICU | Bed manager | `ADT//TRANSFER_IN//ward` + `ADT//TRANSFER_IN//stepdown` | 0.799 (0.790–0.808) · 0.885 (0.872–0.898) |
| Dies | ICU team | `HOSP//discharge_category//expired` | 0.930 (0.912–0.946) |

Six classifiers, five predictions: leaving the ICU adds the ward and step-down classifiers. A stay where the event already happened before the cut gets no probability. Death is a unit count; it never marks a bed.

## How it works

1. **Tokenize: the model speaks EHR, not English.** CLIF tables become one event timeline per ICU stay. The vocabulary is 1,231 clinical-event tokens (each value binned into one of ten bins), not English words.
2. **Represent.** The decoder (Nemotron 3.5 Bolt E4B layer design, Gemma 4 text; 16 layers, hidden size 384, 36.2M parameters, trained from scratch) reads the timeline once. Its last hidden state is the patient's state.
3. **Predict.** One logistic classifier per task on that state gives the probability. Adding a task needs a new classifier, not a new model.
4. **Add up.** `app/aggregate.py` sums the patients into unit counts with an 80% range, against the unit's ventilators and CRRT machines.
5. **Explain.** NVIDIA Nemotron 3.5 Bolt E4B (4-bit, on llama.cpp) answers questions about the board by calling read-only tools. It predicts nothing.

## How we used the CIQ, NVIDIA and Lenovo stack

| Piece | What it does here |
|---|---|
| 2 × Lenovo ThinkStation PGX, 1 × NVIDIA GB10 each | All compute. Training and probe fitting use both GPUs; the demo uses one for our model, then one for Nemotron |
| CIQ Fuzzball 4.3 | Five workflows (below). Orchestrate schedules jobs, images and volumes; Substrate runs the containers on the GB10s. Driven through the Fuzzball MCP server and CLI |
| VAST storage | Backs the persistent Fuzzball volumes below; the object cache is the only way in or out |
| NGC `pytorch:25.11-py3` | Training, packaging, probe fitting and inference |
| llama.cpp server (`ghcr.io/ggml-org/llama.cpp:server-cuda13`) + NVIDIA Nemotron 3.5 Bolt E4B, 4-bit GGUF | The chat, served on one GPU (8 cores, 32 GB) with tool calling |

| Workflow | What it does | Compute |
|---|---|---|
| `job_1_data_move` | Copies the CLIF parquet files onto the `mimic_clif` volume | CPU |
| `job_2_tokenize` | Tokenizes, splits train / tuning / held-out, removes the demo cohort | CPU, 20 cores |
| `job_3_train` | Trains on 2 nodes with PyTorch DDP (Fuzzball `multinode`) | 2 GPUs |
| `job_3_1_package` | Packages the newest checkpoint into `final/` and load-tests it | CPU |
| `job_4_probe` | Extracts patient vectors on both GPUs, fits the six classifiers, scores held-out patients | 2 GPUs |
| `job_5_launch` | Infers the 25-patient ward, writes the forecast, serves the board and Nemotron | 1 GPU, then 1 GPU |

| Volume | Holds |
|---|---|
| `mimic_clif` | CLIF data, tokens, the model, the classifiers, the Python venv (read only in job 5) |
| `twin-store` | The staged ward, `rooms.json`, `forecast.json` |
| `hfcache` | Nemotron weights at a pinned revision |
| object cache | In: our code and the CLIF tarball. Out: logs, metrics, summaries (counts only) |

Each workflow's README has its steps, guards and start command. The full feature-by-feature account is in [`HOW_WE_USED_CIQ.md`](https://github.com/sajor2000/icustrainciq/blob/main/docs/HOW_WE_USED_CIQ.md).

## Run the demo (job 5)

```bash
git archive -o icutwin_code.tar $(git stash create || echo HEAD)
# object_put source_path=icutwin_code.tar uri=fb://group/staging/icutwin_code.tar force=true
# stop the previous t7-launch, then:
# workflow_start path=workflows/job_5_launch/workflow.fz name=t7-launch values={"Tag": "launch-20261115a"}
# open the board endpoint: workflow_endpoints
```

A new forecast means stopping `t7-launch` and starting it again with a new `Tag`. Job 5 reads the classifiers from `twin-store:/train/probe-final.joblib` with its `.meta.json`; copy them there once per model from job 4's `final/`.

## Run it locally

```bash
uv sync --extra model --extra dev
uv run pytest -q

icutwin-tokenize pipeline examples/mimic.yaml
icutwin-train     tokenized_output -o model_output --size m
icutwin-winnow    tokenized_output
icutwin-extract   tokenized_output -m model_output/mdl-icutwin
icutwin-rep-score tokenized_output -m model_output/mdl-icutwin
```

Multi-GPU: `torchrun --nproc_per_node=N -m icutwin.model.decoder tokenized_output -o model_output`. Config lives in `icutwin/config/*.yaml`; pass `-c my.yaml` to override.

## Repository

| Folder | Holds |
|---|---|
| `icutwin/` | CLIF tokenizer, decoder model, probe scoring |
| `app/` | Ward inference (`infer_ward.py`), rooms and unit forecast, bed board server (`board.py`), chat agent |
| `workflows/` | Fuzzball jobs 1–5, each with its own README |
| `clif_demo/` | MIMIC-IV Demo in CLIF (open data; tests and the demo ward) |
| `slides/` | The pitch deck |

## Team 7 · CLIF

| Name | Affiliation |
|---|---|
| J.C. Rojas, MD, MS | Rush University |
| Kaveri Chhikara, MS | UChicago Medicine |
| Vaishvik Chaudhari, MS | Rush University |
| Dema Therese, MS | UChicago Medicine |
| Zewei ('Whiskey') Liao, MS | UChicago Medicine |

We built it together, as one team.

## Limits

Trained on one hospital's data (MIMIC-IV), EHR data only, retrospective, not prospectively validated. Research prototype, not a medical device; it recommends no treatment.

See [`ACKNOWLEDGMENTS.md`](ACKNOWLEDGMENTS.md) for the CLIF Consortium, Speaking CLIF and the open-source projects the scoring code builds on.

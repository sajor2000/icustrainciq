# How we used the CIQ, NVIDIA and Lenovo stack

Read this to see exactly what ICU Horizon ran on, and how. Every fact here comes from the team's demo code: [github.com/vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin), branch `t7/fb-job5-launch` (commit `875358a`, read on 2026-11-15), files `workflows/job_*/workflow.fz` and their READMEs. Nothing in that branch was changed to write it.

## In one paragraph

Two Lenovo ThinkStation PGX machines, each with one NVIDIA GB10, run CIQ Fuzzball 4.3. Five Fuzzball workflows do all the work. Jobs 1 to 4 run once: they move the CLIF data onto the cluster, turn it into event tokens, train our patient model across both GPUs and fit six small classifiers on it. Job 5 is the only workflow the demo runs. It infers the 25-patient ward on one GPU, writes the forecast, then keeps two services up: the bed board, and NVIDIA Nemotron 3.5 Bolt E4B on llama.cpp for the chat, on one GPU. Patient data stays on Fuzzball volumes. The object cache is the only way in or out: our code goes in, logs and counts come out.

## The hardware

| Item | What we used |
|---|---|
| Machines | 2 × Lenovo ThinkStation PGX (NVIDIA DGX Spark design) |
| GPU | 1 × NVIDIA GB10 per machine, arm64, CUDA 13.0, driver 580 |
| Where | On site at the event. Nothing ran in the cloud |
| Storage | The team's Fuzzball volumes, provisioned on VAST storage at the event (per the team; not visible in the code) |
| How the GPUs were split | Training and probe fitting: both GPUs, one per machine, through Fuzzball `multinode`. Demo: one GPU for our model's inference, then one GPU for Nemotron |

## The software

| Layer | What we used | Where in the code |
|---|---|---|
| Scheduler | CIQ Fuzzball 4.3, Fuzzfile `version: v4` | every `workflows/job_*/workflow.fz` |
| GPU image | `nvcr.io/nvidia/pytorch:25.11-py3` (NGC). Newer tags need a newer driver than the cluster's 580 | jobs 3, 3.1, 4, 5 |
| Chat serving | The running job 5 (`t7-launch`, started 2026-11-15) serves Nemotron with the llama.cpp server image `ghcr.io/ggml-org/llama.cpp:server-cuda13-b11459`. The workflow file at commit `875358a` names `nvcr.io/nvidia/vllm:25.12.post1-py3`; the team switched after that commit | job 5, service `nemotron` |
| Chat model | NVIDIA Nemotron 3.5 Bolt E4B, 4-bit GGUF (`nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB`, `Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf`, revision `1db54d5`), 65,536-token context, used as is, not trained by us. The workflow file at commit `875358a` named Nemotron 3 Nano 30B-A3B FP8 on vLLM; the running workflow uses this model | job 5, service `nemotron` (1 GPU, 8 cores, 32 GB) |
| Our patient model | A decoder with the layer design of NVIDIA Nemotron 3.5 Bolt E4B (Gemma 4 text), trained from scratch: 16 layers, hidden size 384, 1,231 event tokens, 36,232,032 parameters | `icutwin/model/decoder.py`, job 3.1 load test |
| Python packages | `uv`, one persistent virtual environment on the volume, `mimic_clif:/.tooling/venv-ngc2511`, rebuilt only when `uv.lock` changes | job 3 `setup`; jobs 4 and 5 refuse a venv built for another `uv.lock` |
| Data format | CLIF (Common Longitudinal ICU data Format), MIMIC-IV in CLIF | `icutwin/tokenizer/` |
| Board | Python standard library only (`app/board.py`), one static HTML page | job 5, service `board` |

## The Fuzzball features we used

| Fuzzball feature | How we used it |
|---|---|
| **Persistent volumes** (`use: team7`, on the event's VAST storage per the team; the Fuzzfiles name only the volume) | `mimic_clif`: CLIF data, tokens, the model, its classifiers, the venv. `twin-store`: the staged ward and the forecast files the board reads. `hfcache`: Nemotron weights |
| **Ephemeral volumes** (`use: ephemeral`) | A scratch copy of our code for each run, deleted when the workflow ends |
| **Object cache** (`fuzzball://group/...`) | The only way in or out. In: `staging/clif_parquet.tar` (job 1) and `staging/icutwin_code.tar` (jobs 2 to 5). Out: logs, metrics and summaries under a new `Run` or `Tag` folder per run (it never overwrites) |
| **Ingress / egress** on volumes | Code and data come in through `ingress`; logs, `MANIFEST.json`, `probe_metrics.json` and the launch summary leave through `egress` when the workflow ends |
| **Jobs with `depends-on`** | Each workflow is a chain: job 5 is `load` → `infer` → `score`, then the services |
| **`multinode`, `implementation: generic`** | Job 3 trains with PyTorch DDP (`torch.distributed.run --nnodes 2`), job 4 extracts patient vectors on both GPUs, half the stays each |
| **GPU requests** (`devices: nvidia.com/gpu: 1`) | One GPU per job or service; `exclusive: true` on training and on Nemotron. Job 5's `infer` is not exclusive: in 4.3 that would reserve a whole node |
| **Services** (`persist: true`) | Job 5's `board` and `nemotron` stay up after the jobs finish |
| **Readiness probes** | `nemotron`: HTTP `/v1/models` on 8000. `board`: TCP on 8080 |
| **Endpoints** | `board` is published as endpoint `web`, `type: subdomain`, `scope: group`, `protocol: http` (the Fuzzball proxy terminates TLS) |
| **Template values** | `{{ .Run }}` and `{{ .Tag }}` name each run's output folder; a new value every run |
| **Policies** | Time limits on every job; `restart: on-node-fault` on jobs that are safe to repeat (1, 2) |

## The five workflows

| Workflow | Jobs inside | Shape | Reads | Writes |
|---|---|---|---|---|
| **1 · Data move** | `copy-in` | CPU, 1 core, `alpine:3.20` | object cache `staging/clif_parquet.tar` | `mimic_clif:/clif/` (16 CLIF tables) |
| **2 · Tokenize** | `tokenize` | CPU, 20 cores, 110 GiB, `uv` image | `mimic_clif:/clif/` | `mimic_clif:/tokenized_output/` (train, tuning, held-out; the demo cohort removed) |
| **3 · Train** | `setup` (1 GPU), `train` (`multinode` 2 × 1 GPU, 20 cores, 110 GiB) | 2 GPUs, DDP, up to 12 h | tokens | `mimic_clif:/model_output/<Run>/` checkpoints |
| **3.1 · Package** | `package` (CPU), `loadtest` (CPU) | CPU | the newest checkpoint | `mimic_clif:/model_output/final/` (weights, `vocab.yaml`, `MANIFEST.json`); prints `LOADTEST OK` |
| **4 · Probe** | `winnow` (CPU), `extract` (`multinode` 2 × 1 GPU), `probe` (CPU) | 2 GPUs | `final/`, tokens | `final/probe.joblib`, `final/probe_metrics.json` (held-out AUROC, AUPRC, Brier) |
| **5 · Launch** (`t7-launch`) | `load` (2 cores, 8 GB), `infer` (1 GPU, 8 cores, 48 GB), `score` (4 cores, 16 GB), services `nemotron` (1 GPU, 8 cores, 32 GB) and `board` (2 cores, 4 GB) | 1 GPU at a time | `mimic_clif:/dashboard_data/` (25 stays, read only), `final/`, `twin-store:/train/probe-final.joblib` | `twin-store:/rooms.json`, `twin-store:/forecast.json`, object cache `launch/<Tag>/summary.txt` |

## What job 5 does, step by step

1. **`load`** (CPU, 10 min limit). Unpacks the code, checks the venv against `uv.lock`, then checks that the code's token list matches the model's `final/vocab.yaml` (it stops if not). Checks the 25 demo stays, the classifiers and the training labels. A missing input fails here, before a GPU is booked.
2. **`infer`** (1 GPU, 30 min limit). `app/infer_ward.py`: CLIF tables → one event timeline per stay → cut 24 hours after ICU arrival → one pass through the model → the saved classifiers → six probabilities per stay. Nothing is fitted. It prints counts only.
3. **`score`** (CPU). `app/rooms.py` writes one entry per room; `app/aggregate.py` adds the rooms up into unit counts with a likely range and writes `forecast.json` last, the file the page watches.
4. **`nemotron`** (service, 1 GPU). Starts after `score`, so the inference GPU is free first. Serves the local copy from `hfcache` (llama.cpp server in the running workflow).
5. **`board`** (service, CPU). Starts after `score`. Serves the page and the API on port 8080; the chat works once Nemotron is ready.

**A new forecast** means stopping `t7-launch` and starting it again with a new `Tag`. There is no dispatcher and no 07:00 timer in this path, so the board's update button answers "no dispatcher configured".

## What ran on the cluster

Read from Fuzzball as team 7 on 2026-11-15 (read only; nothing was started, stopped or changed). Times are UTC.

| Workflow run | When | Result |
|---|---|---|
| `job_1_data_move` | Nov 14, 15:20, 40 s | finished |
| `job-2-tokenize` | Nov 14, 17:38 to 17:45 | finished |
| `job-3-train ep2-20261114c` (2 GPUs, DDP) | Nov 14, 19:11 to 20:13 | stopped by the team after about an hour; checkpoint kept |
| `job-3-1-package ep2-20261114c` | Nov 14, 20:19 to 20:20 | finished |
| `job4-probe-20261114d` (2 GPUs, then CPU) | Nov 14, 21:38 to 22:13 | finished |
| `t7-fb-nemotron-persistent` | Nov 14, 18:14 | finished: Nemotron weights on `hfcache` |
| `t7-launch` (job 5) | Nov 15, from 16:04 | running: `load` 7 s, `infer` 35 s on one GPU, `score` 33 s, then `board` and `nemotron` up |

One forecast for the 25-patient ward takes about 78 seconds, from load to score. In that run, `load`, `infer` and `nemotron` ran on node CIQ-CHI-SPARK14 and `score` and `board` on CIQ-CHI-SPARK13.

Volumes as Fuzzball lists them (provisioner `team7`): `mimic_clif` 200 GB, `twin-store` 20 GB, `hfcache` (no fixed size reported).

### Which node ran each step

Fuzzball places each step; these are the hosts it recorded (read only, 2026-11-15). Node A is CIQ-CHI-SPARK13 (192.168.99.22), node B is CIQ-CHI-SPARK14 (192.168.99.23); each is a Lenovo ThinkStation PGX with one NVIDIA GB10 (20 Arm cores, about 128 GB, one GPU).

| Workflow | Step | Node |
|---|---|---|
| Job 1 `job_1_data_move` | `copy-in` (alpine) | A |
| Job 2 `job-2-tokenize` | `tokenize` | B |
| Job 3 `job-3-train ep2-20261114c` | `setup` | A |
| | `train` (DDP, one rank and one GPU per node) | A and B |
| Job 3.1 `job-3-1-package ep2-20261114c` | `package`, `loadtest` | A |
| Job 4 `job4-probe-20261114d` | `winnow` | A |
| | `extract` (one GPU per node) | A and B |
| | `probe` (fit on CPU) | B |
| Job 5 `t7-launch` (Nov 15 run) | `load`, `infer` (GPU) | B |
| | `score` | A |
| | service `board` | A |
| | service `nemotron` (GPU) | B |

## How to run it

From the ICU-Twin checkout, with the Fuzzball MCP or CLI (`workflows/job_5_launch/README.md`):

1. Stage the code: `git archive -o icutwin_code.tar $(git stash create || echo HEAD)`, then put it in the object cache at `fb://group/staging/icutwin_code.tar`.
2. Stop the previous `t7-launch` (two would mean two Nemotrons).
3. Start `workflows/job_5_launch/workflow.fz` as `t7-launch` with a new `Tag`, for example `launch-20261115a`.
4. Open the `board` endpoint.

**Once per model, by hand:** job 5 reads the classifiers from `twin-store:/train/probe-final.joblib` and `probe-final.meta.json`. Job 4 writes them to `mimic_clif:/model_output/final/probe.joblib`. No workflow on the branch copies one to the other; the copy is a manual step.

## The privacy rules the workflows enforce

- `mimic_clif` is read only in job 5, by rule.
- Every job prints counts, never ids or rows; the launch summary holds the model's run, step and the forecast time.
- Names on the board are generated (`--names fake`). Real rooms only with `--real-ward`, on the cluster.
- The demo cohort is removed from every training split (job 2), and job 3 checks that again before it trains.

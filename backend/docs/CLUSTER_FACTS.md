# Cluster facts (checked 2026-11-13, evening)

Read this if you need the hardware, driver, image and storage facts of the two Lenovo PGX nodes; it is a dated record from the evening before the event, so use [`RUNBOOK.md`](RUNBOOK.md) to run the app and [`../../docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) for the overview.

**Status:** The team ran ICU Lookahead end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, and it worked. Statements below that nothing had run describe the time of writing.

Superseded since this check: the storage rows for `clif_work`, `tooling` and `twin-store`, and the `t7-build` and `t7-smoke` rows of the GPU table. Current state:

| Topic | Current state (code on `main`) |
|---|---|
| How to run | `scripts/launch.sh` first ([`RUNBOOK.md`](RUNBOOK.md)); the manual workflow steps are the fallback |
| Volumes | `twin-store` is the one volume ICU Lookahead writes (code, packages, stage ward, forecast files). `mimic_clif` is only read, at `/data`. `hfcache` holds the Nemotron weights. `clif_work` and `tooling` are not used |
| Probe | Fitted by job 4 in vaishvikc/ICU-Twin and staged at `/store/train/probe-final.joblib` with `probe-final.meta.json`. `t7-fit` is the fallback |
| Names | Generated per room number by `app/fake_names.py` (`--names fake`). `name.parquet` is no longer read |
| Code on the cluster | Published by `t7-code` from this repo's `backend/` at a pinned commit. Training (`job_2` to `job_4`) is in vaishvikc/ICU-Twin; there is no `t7-build` here |
| Schedule and cut | One run at 07:00; each patient is cut 24 h after ICU arrival; five predictions on the board |

## How the facts were checked

Read-only checks as the team7 account, plus one probe job on one GPU node. The probe printed system facts and file names only, never file contents.
Question IDs refer to [`QUESTIONS.md`](https://github.com/vaishvikc/ICU-Twin/blob/main/docs/QUESTIONS.md) (in vaishvikc/ICU-Twin). Facts marked "verify at kickoff" are not yet tested on our own two nodes.

## Hardware and scheduler

| Fact | Value | Answers |
|---|---|---|
| Fuzzball | 4.3.1 (CLI and agent) | F1, G1 |
| Our compute | **2 × Lenovo ThinkStation PGX** (NVIDIA GB10: 1 GPU, 20 cores, 128 GB unified memory each). `fuzzball node list` shows every team's nodes; size all work for our two | A1 |
| GPU rule | Each node lists `nvidia.com/gpu: 1`. A job or service that requests it holds the whole GPU until it ends, so two GPU jobs never share a node. `exclusive: true` is a different thing: it reserves the whole **node** (Fuzzball 4.3 workflow syntax), so only Nemotron sets it; the forecast, fit and smoke GPU jobs do not (`COMPUTE_PLAN.md`). No pinning to a named node: the scheduler places work | F3 |
| Driver / CUDA | 580 / **CUDA 13.0**. Images must be built for CUDA 13.0 (forward compatible to 13.1 only) | G7 |
| Images we pin | `nvcr.io/nvidia/pytorch:25.11-py3`, `nvcr.io/nvidia/vllm:25.12.post1-py3`, `lmsysorg/sglang:v0.5.21` (official SGLang release, arm64, CUDA 13.0.1; only for the sampling experiments and the optional smoke check; fallback `scitrera/dgx-spark-sglang:0.5.12`). NGC tags newer than 26.02 need a newer driver | G7, H3 |
| GPU memory | `nvidia-smi` reports `[N/A]` (unified memory); use `free -g` | G3 |
| `/dev/shm` | 60 GB | G8 |
| ulimits | nofile 1048576, memlock 4194304 KB | G8 |
| RDMA | **no `/dev/infiniband`** in a single-node job. The 2-node smoke test decides NCCL over RoCE or TCP sockets | G4, H1 |
| NICs in a job | `lan0`, two QSFP/ConnectX ports (`enp1s0f0np0`, `enp1s0f1np1` and their `enP2…` pairs), Wi-Fi | H1 → `NCCL_SOCKET_IFNAME` candidates |
| Multinode | Works: team7 already ran a 2-node `generic` exclusive job | F3 |

## GPU allocation (two GPUs, one per node)

| Phase | GPU on one node | GPU on the other node |
|---|---|---|
| Smoke (`t7-smoke.fz`, 9:30 check, seeds the stack) | tiny training run, `icutwin-extract` forward pass, vLLM check, optional SGLang scripts | free |
| Build (`t7-build.fz`) | training rank 0 | training rank 1 |
| Forecast (`t7-forecast.fz`, 07:00 daily and on request) | job `extract` (`icutwin-extract`, one forward pass per patient), a few minutes; `probe` and `aggregate` run on CPU | Nemotron 3 Nano (`t7-twin.fz`), always on |
| Demo app (`t7-twin.fz`) | free for the everyday forecast | Nemotron 3 Nano answering questions |

Why this layout: training is the heavy job and uses both nodes; a 25-bed forecast fits on one GPU for minutes, so the other node keeps the nurse's assistant always on and can take over if a node fails. The second node unlocks training on both GPUs (multinode); `t7-forecast-burst.fz` is retired (kept for reference).

The aggregate job and the bed board need no GPU.

## Storage

| Fact | Value | Answers |
|---|---|---|
| Provisioners | `team7` (NFS, team-only), `shared` (NFS, read-only datasets for everyone) | S1, A4 |
| Backing store | NFS shared by all nodes, so persistent and `use: team7` volumes are visible from both training ranks | G2, S1 |
| Team volume `mimic_clif` | 186 GiB quota, empty, writable, team7 only. Our data lands here | S3 |
| `clif_work` | Superseded: not used. Was planned for tokens and per-stay scores; they are on `twin-store` (`/store/stage`, `/store/train`) | |
| `tooling` | Superseded: not used. Packages are at `/store/py` on `twin-store` | |
| `hfcache` | team7 only: Nemotron weights cache, needed by `t7-twin.fz` (80 GB) | |
| `twin-store` | Superseded: it now holds everything ICU Lookahead writes, including the staged ward tokens and per-stay scores, so treat it as restricted ([`FUZZBALL_VALIDATION.md`](FUZZBALL_VALIDATION.md)) | |
| `shared/datasets` | organizers' open data (bio, city, finance, geo, gov, space). No clinical data | |
| Read-only mounts | not tested (`fuzzball run --volume` has no `:ro`) | S2 open |

## Data route (decided)

1. **Our S3 bucket → `mimic_clif`** by volume `ingress` with a team-scoped S3 secret.
2. Fallback: upload once from a team member's computer through a short-lived upload service, then a verify job.
3. Last resort: PhysioNet download by https ingress with a `physionet` secret; outbound HTTPS to physionet.org, GitHub, PyPI, nvcr.io and Hugging Face works from a job.

Laptops never hold or move the data. Jobs print counts and checksums only.

## Catalog (ready-made workflows)

vLLM, vLLM inference server, LiteLLM gateway, Jupyter, RStudio, Open WebUI, Filebrowser, Rclone, MPI Hello World, Dependent Jobs Example, and models including GPT-OSS 20B/120B and Nemotron 3 Nano/Super. Each catalog entry starts its own workflow and takes a GPU; to combine one with ours, `fuzzball workflow catalog render` it and copy the service into our fuzzfile.

## Still open at kickoff

- Data-use answers A2, A3 and S1 (deletion, admin access, log retention) in writing from CIQ.
- `t7-smoke.fz` (9:30): the pinned images pull and run on driver 580.
- 2-node smoke test: RoCE or TCP for NCCL.
- Still open from QUESTIONS.md: S2, A2, A3, D2–D4, F5, G4–G6, H2 (NGC key).
- VAST (event sponsor): whether our volumes sit on VAST, snapshots and their deletion, S3 and DataBase access: QUESTIONS.md V1–V8. Nothing in the plan depends on VAST.

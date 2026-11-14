# Compute plan: who gets which GPU and which cores

Written 2026-11-14 from the Fuzzball 4.3 documentation and this repo. **Nothing here was tested on the cluster**: training was running, so no CLI or MCP call was made. Every Fuzzball fact carries a source tag (list at the end). "Not documented" means the 4.3 docs do not say; it is not a guess.

Line numbers refer to the working tree on 2026-11-14. Other people were editing the `.fz` files that day, so find the job by name if a line has moved. All changes below are **recommendations**; this plan edits nothing.

## 0. The three findings that change the plan

| # | Finding | Why it matters | Source |
|---|---|---|---|
| 1 | `exclusive: true` means the whole **node**, not the whole GPU. "If true, job gets exclusive access to the node." | Nemotron (`t7-twin.fz:21`) and the forecast `extract` (`t7-forecast.fz:57`) both set it. Two nodes, two exclusive holders: the board and dispatcher have no node left. As written, the forecast `extract` should not start while `t7-twin` is up, and `t7-twin` cannot run on one node. Predicted from the docs; confirm live (section 6). | [WS], [DEBUG] |
| 2 | The GPU needs no `exclusive`. Each node has one `nvidia.com/gpu`. A job that requests 1 takes the only one, so two GPU jobs never share a node anyway. | Removing `exclusive` from single-node GPU jobs costs nothing and lets CPU services share the node. | [GPU], `CLUSTER_FACTS.md` |
| 3 | The dispatcher counts a **queued** workflow as busy. Any non-finished `t7-build`, `t7-forecast*`, `t7-smoke`, `t7-fit` or `t7-ward` blocks every update. | A retrain or a hand-started job that sits in the queue stops all forecast updates, even with a free GPU. | `app/dispatcher.py` (`GPU_WORKFLOW`, `TERMINAL`, `busy`) |

## 1. What competes for what

### The hardware

| Item | Value | Source |
|---|---|---|
| Nodes | 2 × Lenovo ThinkStation PGX (NVIDIA GB10) | `CLUSTER_FACTS.md` |
| Cores per node | 20 Arm cores (10 Cortex-X925 + 10 Cortex-A725) | [LENOVO], [SPARK] |
| Memory per node | 128 GB LPDDR5x, **unified**: CPU and GPU share it. Fuzzball lists 127.9 GB available on a GB10 node. | [LENOVO], [SPARK] |
| GPU per node | 1 (`nvidia.com/gpu: 1`), requested whole | [GPU], `CLUSTER_FACTS.md` |
| Cluster total | 40 cores, about 256 GB, 2 GPUs | sum |
| Storage | NFS, shared by both nodes. No volume ties a job to one node. | `CLUSTER_FACTS.md`, [DRIVERS] |

Unified memory is the trap. A model on the GPU uses the same 128 GB as every CPU job on that node. CIQ's own GB10 guide says "a large GPU-resident model competes with the rest of the stack" and asks for 4 to 8 GB of headroom [SPARK].

### The workloads

"Run time" is a measured number only where it says so. Nothing has been timed on the GB10s (`LIVE_DEMO.md` section 2). The timeout is the upper bound the scheduler enforces.

| Workflow · job | GPU | Request in the `.fz` today | File:line | Run time | When |
|---|---|---|---|---|---|
| `t7-build` · train | **both** (multinode, 2 nodes, generic) | not in this repo (ICU-Twin repo) | n/a | hours | once; running now |
| `t7-fit` · stage | no | 8 cores, 32 GB | `t7-fit.fz:36` | not measured; timeout 30 m | once per model |
| `t7-fit` · extract | **1** | 16 cores, 100 GB, exclusive | `t7-fit.fz:54` | not measured; timeout 2 h | once per model |
| `t7-fit` · fit | no | 16 cores, 64 GB | `t7-fit.fz:65` | not measured; timeout 1 h | after extract and stage |
| `t7-ward` · load | no | 2 cores, 8 GB | `t7-ward.fz:39` | seconds; timeout 10 m | when the ward changes |
| `t7-ward` · tokenize | no | 8 cores, 32 GB | `t7-ward.fz:55` | not measured; timeout 30 m | after load |
| `t7-twin` · nemotron | **1**, all day | 16 cores, 100 GB, exclusive; vLLM `--gpu-memory-utilization 0.85` | `t7-twin.fz:21`, `:34` | always on | before 07:00 on demo day |
| `t7-twin` · board | no | 2 cores, 4 GB | `t7-twin.fz:44` | always on | same |
| `t7-twin` · dispatcher | no | 1 core, 2 GB | `t7-twin.fz:73` | always on | same |
| `t7-forecast` · precheck | no | 1 core, 1 GB | `t7-forecast.fz:41` | seconds; timeout 5 m | 07:00 daily and on request |
| `t7-forecast` · extract | **1**, minutes | 16 cores, 100 GB, exclusive | `t7-forecast.fz:57` | not measured; timeout 30 m | after precheck |
| `t7-forecast` · score | no | 4 cores, 16 GB | `t7-forecast.fz:75` | not measured; timeout 20 m | after extract |

A room update costs the same GPU time as a unit update. The extractor has no stay filter, so it runs the whole ward (`t7-forecast.fz` header).

## 2. How the scheduler decides (documented facts)

| Question | Answer | Source |
|---|---|---|
| How is a job placed? | The scheduler works through a queue on a fixed interval (default 60 s) and puts each allocation on a node that has the requested cores, memory and devices free. | [CONF], [QUEUE] |
| Which node, when both fit? | **Not documented.** No spread or pack rule is described. Do not rely on either. | n/a |
| Can a job be pinned to a node? | Not by name. Annotations select node pools, not single nodes. | [WS] |
| What if nothing fits? | The job waits. Status `Pending`; `workflow why` reports `INSUFFICIENT_RESOURCES`. It does not fail. No limit on the wait is documented. | [QUEUE], [WS] |
| What if a node refuses the lease? | The job returns to the queue. After more than 10 minutes and 10 refusals in a row the workflow fails. One refusal text: "could not set exclusive mode, other resources in use". | [DEBUG] |
| Can a CPU job share a node with a GPU service? | Yes, if the service is **not** `exclusive` and the cores and memory fit. A shared node "can run multiple jobs simultaneously". | [CONF], [WS] |
| Can two jobs share one GPU? | **No way is documented.** Devices are whole counts. The docs mention no time-slicing, MPS, MIG or fractions. With one device per node, the second requester waits. | [GPU], [WS] |
| Does vLLM's memory setting allow sharing? | Only between processes inside the same job. Lowering it leaves memory for "other processes on the same GPU". Fuzzball still gives the device to one job. | [VLLM] |
| Priorities? | Yes. Effective priority = organization + group + user + workflow priority, plus 1 per hour waited. A submitter may set `--priority` to 0 or lower only. `workflow update --priority` changes it later. | [PRIO] |
| Preemption? | Off by default. It only evicts work marked `preemptible`. | [CONF], [PRIO] |
| Backfill? | On by default. A smaller job may run ahead of a blocked one if its time limit fits. A service has no time limit and cannot backfill. | [CONF], [QUEUE] |
| Named queues or partitions? | None for users. One scheduler queue with states pending, ready, running, finished. | [QUEUE] |
| `multinode` | All ranks start together or none does. One rank failing stops the job. Use it for training only. | [PAR] |
| `task-array` | Independent tasks, each its own single-node allocation, `concurrency` at most 200. | [WS], [TASK] |
| Services | `persist: true` keeps a service running until the workflow is stopped. A service becomes RUNNING only after its readiness probe passes. A service takes the same `resource` block as a job. Whether a request is also a hard limit is **not documented**. | [WS] |
| Node lost | Work on it fails at once, with the node named. Only jobs with `policy.restart: on-node-fault` run again elsewhere. | [HEALTH], [WS] |
| Volumes and locality | Shared NFS volumes place no constraint. Only a provisioner marked `local: true` ties work to one node. Container images are converted and cached on first use. | [DRIVERS], [WS], [VOLS] |

## 3. Phases

Node A and node B are labels. The scheduler picks which machine is which.

### (a) Now: training

| | Node A | Node B |
|---|---|---|
| GPU | `t7-build` rank 0 | `t7-build` rank 1 |
| CPU | training | training |

Start nothing. Training is a 2-node exclusive job, so no other job can be placed. Anything submitted now waits, and if its name matches the dispatcher's list it also blocks updates later.

### (b) After training: fit the probes

Run `t7-fit` **before** `t7-twin` starts. Both nodes are empty, so the exclusive flags do no harm.

| | Node A | Node B |
|---|---|---|
| GPU | `t7-fit` extract | free |
| CPU | extract: 16 cores, 100 GB | `t7-fit` stage: 8 cores, 32 GB; then `fit`: 16 cores, 64 GB |

- `stage` and `extract` have no dependency on each other. Together they ask for 24 cores, more than one node has. They need both nodes, or they run one after the other.
- Do not start Nemotron during `t7-fit` with today's files. Nemotron would take node B whole and `stage` would have to wait for `extract`.
- Then run `t7-ward` if the ward is not the open demo (CPU only, about 8 cores).

### (c) Steady state and demo

Target allocation, after the recommendations in section 4:

| | Node A | Node B |
|---|---|---|
| GPU | Nemotron, all day | free; forecast `extract` for minutes |
| Always on | Nemotron: 16 cores, 100 GB | board: 2 cores, 4 GB; dispatcher: 1 core, 2 GB |
| During a forecast | nothing more | precheck 1 core → extract 8 cores, 48 GB → score 4 cores, 16 GB |
| Peak use | 16 of 20 cores, 100 of 128 GB | 11 of 20 cores, 54 of 128 GB |
| Left free | 4 cores (unused while Nemotron stays exclusive) | 9 cores, about 74 GB |

The same picture with **today's** files:

| Step | What the docs predict |
|---|---|
| `t7-twin` starts | Nemotron needs an empty node. The board and dispatcher must both land on the other node. If the scheduler places them on different nodes first, Nemotron stays `Pending`. Placement order is not documented. |
| Forecast `precheck` | Runs on node B (1 core). |
| Forecast `extract` | Asks for exclusive use of a node. Node A is Nemotron's. Node B holds the board and dispatcher. It stays `Pending`, or the lease is refused and the workflow fails after about 10 minutes. |
| Dispatcher | Sees an unfinished forecast. Refuses every further update until someone stops it. |

### (d) A second request during the demo

| Request | What happens | Rule |
|---|---|---|
| Second forecast from the board or chat | The dispatcher refuses it in plain words. It never reaches the scheduler queue. | Nothing to do. |
| Second forecast started by hand | It queues. Its `extract` waits for the GPU (`INSUFFICIENT_RESOURCES`). Both runs write the same stage files in `clif_work/stage`. | Do not start forecasts by hand while `t7-twin` is up. |
| `t7-ward` during a forecast | CPU only, so it would run at once and replace the tokens the forecast is reading. | Start `t7-ward` only when no forecast is active. |
| Retrain (`t7-build`) | Needs both nodes at the same moment. Nemotron holds one with no time limit, so the start cannot be estimated and the job waits for good. Preemption is off. While it waits, the dispatcher refuses every update and the 07:00 run is missed after 10 minutes of retries. | No retrain while the demo is up. To retrain, stop `t7-twin` first. That takes the board down too. |
| `t7-fit` (new model) | Needs one GPU. Same exclusive problem as the forecast `extract`. The dispatcher refuses updates while it is unfinished. | Run it in a quiet window, after the fix in section 4. |

## 4. Balance rules

### Rules to check each `.fz` against

1. **`exclusive: true` only on `t7-build`.** A single-node GPU job is already alone on its GPU. Exception: Nemotron may keep it for the demo (rule 5).
2. **A node's requests must add up to 20 cores and 127.9 GB or less**, counting every job that can run at the same time. The scheduler will not place a job beyond that; it queues it.
3. **Keep 3 cores and 6 GB free for the board and dispatcher on the node without Nemotron.** No job that can run beside them may request more than 17 cores or 120 GB.
4. **Every job has a `policy.timeout.execute` close to its real run time.** The timeout is the only automatic release for a hung job, and backfill needs it.
5. **Count GPU memory as node memory.** Nemotron's memory request must cover what vLLM takes on the GPU. Today vLLM is told to take 0.85 of the device. If vLLM sees the full 128 GB, that is about 109 GB, more than the 100 GB requested. Keeping Nemotron exclusive hides this, because nobody else is on its node.
6. **Forecasts start only through the dispatcher.** It is the one place that knows a run is active.
7. **Background work starts below priority 0**, for example `fuzzball workflow start --priority -10` for `t7-ward` or a hand-started check. Dispatcher forecasts stay at 0 and are considered first [PRIO].
8. **Jobs that are safe to run twice get `policy.restart: on-node-fault`.** `precheck` and `extract` overwrite their own output, so they qualify. Check that `score` writes `rooms.json` and `forecast.json` whole before adding it there [WS].

### Requests to change (recommendations only)

Memory values for the two `extract` jobs are starting values. Read the real peak with `free -g` at the rehearsal (`nvidia-smi` shows no memory on GB10) and adjust.

| File:line | Job | Today | Recommended | Why |
|---|---|---|---|---|
| `t7-forecast.fz:57` | extract | 16 cores, 100 GB, GPU, `exclusive: true` | 8 cores, 48 GB, GPU, **no exclusive** | Finding 1. It must share node B with the board and dispatcher. 25 patients fit one batch of 64 (`icutwin/config/extraction.yaml:4`). |
| `t7-forecast.fz:58` | extract | timeout 30 m | 10 m | A hung extract blocks updates for the whole timeout. |
| `t7-forecast.fz:76` | score | timeout 20 m | 10 m | Same reason. |
| `t7-forecast.fz:41`, `:75` | precheck, score | 1 core, 1 GB; 4 cores, 16 GB | keep | Small and sequential. |
| `t7-fit.fz:54` | extract | 16 cores, 100 GB, GPU, `exclusive: true` | **no exclusive**; keep cores and memory | So a refit can run while the board is up. The MIMIC-sized pass needs the cores. |
| `t7-fit.fz:36`, `:65` | stage, fit | 8 cores, 32 GB; 16 cores, 64 GB | keep | Fit phase (b). Not measured. |
| `t7-twin.fz:21` | nemotron | 16 cores, 100 GB, GPU, `exclusive: true` | **Demo: keep.** Later: 8 cores, no exclusive, memory equal to vLLM's real footprint | Demo: fewest changes, and it hides the unified-memory overlap. Later: frees 12 cores on node A for CPU work. |
| `t7-twin.fz:34` | nemotron | `--gpu-memory-utilization 0.85` | Demo: keep. Later: about 0.60 with a 96 GB request | Lower it only together with dropping `exclusive`, and only after a chat test. Not measured. |
| `t7-twin.fz:44`, `:73` | board, dispatcher | 2 cores, 4 GB; 1 core, 2 GB | keep | Right size. |
| `t7-ward.fz:39`, `:55` | load, tokenize | 2 cores, 8 GB; 8 cores, 32 GB | keep | Fits node B beside the services (11 of 20 cores). |
| `t7-smoke.fz:111` | seed | no timeout | add 10 m | Rule 4. |

After these changes the heaviest moment on node B is: board 2 + dispatcher 1 + extract 8 = 11 cores and 54 GB. Even with today's 16 cores and 100 GB the sum is 19 cores and 106 GB, so it fits once `exclusive` is gone.

Spreading CPU work across **both** nodes needs the "later" Nemotron change. Until then all CPU work runs on node B, which has the room.

### Dispatcher guard and scheduler queue

| Dispatcher rule | Effect on the queue |
|---|---|
| One run at a time. Busy = any listed `t7-(build|forecast|smoke|fit|ward)` workflow whose status is not Finished, Errored or Canceled. | At most one dispatcher forecast is ever in the queue. Queued counts as busy. |
| 20 minutes between updates of one scope. A unit update counts for every room. | The clock starts when the run is **submitted**, not when it ends. Time spent waiting in the queue uses up the gap. |
| The gap is cleared if the run fails early. | A run that waits and never fails keeps both the gap and the busy flag. |
| 07:00 run: no gap, retries each minute for 10 minutes. | If the GPU is held for more than 10 minutes at 07:00, the run is missed and `/status` shows it. |
| Scheduler interval, default 60 s [CONF]. | Three chained jobs can each wait for the next pass: up to about 3 minutes of pure waiting per forecast on a default cluster. The real interval here is unknown. |

Gap to close: nothing stops a forecast that is stuck `Pending`. The docs give no limit on waiting [QUEUE]. Add a runbook step now (section 5) and, later, have the dispatcher stop a forecast that has not started its `extract` after a few minutes.

## 5. Throughput options

For a faster unit update or a larger ward.

| Option | Gain | Cost | For 25 patients |
|---|---|---|---|
| Larger batch in the one GPU pass | None below 64 patients: the batch size is already 64. Above 64, raise it until memory is the limit. | Unified memory: a bigger batch takes memory from the same node. | No change needed. |
| Fewer jobs per run: fold `precheck` into the first lines of `extract`; optionally fold `score` in too | Saves one or two scheduler passes and container starts per update. | The GPU is held a little longer; a failed check holds it for seconds. | **Recommended**, after the rehearsal shows how long the waits are. |
| `task-array` on CPU steps | Helps when a CPU step takes many minutes and splits cleanly, such as tokenizing hundreds of stays. | Each task is its own allocation with its own start. For seconds of work it is slower. | No. |
| Both GPUs for a forecast (Nemotron stopped) | About half the forward-pass time on a large ward. | Chat is off. The model loads twice. The extractor needs a stay filter, which it does not have. Restarting Nemotron takes minutes. | No. Model load dominates, not the passes. |
| Model kept loaded in a second always-on service | Removes model load and queue waits; an update takes seconds. | Holds GPU 2 all day. Blocks `t7-fit` and retrain. New code. | Not before the demo. Best option if updates must feel instant. |
| Nemotron scaled to zero when idle (autoscaler, `replicas.min: 0`) [AUTO] | Frees GPU 1 between questions. | First question after idle waits for a cold start of minutes. | No. |

Recommendation for a 25-patient unit: one GPU, one pass, batch 64, two jobs or one. Measure before changing anything else.

## 6. Failure cases

### A node is down

One node means 20 cores, 128 GB and **one GPU**. Chat and new forecasts cannot both have it.

| Mode | What runs | What is lost | Needs |
|---|---|---|---|
| **F: board + forecasts, no chat (recommended)** | board, dispatcher, forecast on the one GPU | Chat says "Chat is not available right now." | `fuzzball/t7-twin-nochat.fz` (rendered: `fuzzball/ready/t7-twin-nochat.fz`): `t7-twin` without the `nemotron` service, started under the name `t7-twin`. The board has no dependency on Nemotron by design. |
| C: chat, no new forecasts | Nemotron, board, dispatcher; board shows the last good forecast | "Update" buttons and the 07:00 run | Nemotron without `exclusive` (19 cores, 106 GB fit one node). Do not press Update: the `extract` would wait for good. |

Choose F. The forecast is the product; the board is built to work without the chat. The no-chat file is in the repo (`fuzzball/ready/t7-twin-nochat.fz`); a test keeps its board and dispatcher identical to `t7-twin.fz`.

Facts behind this:
- Work on a lost node fails at once and names the node [HEALTH]. Services have no restart policy here, so the affected `t7-twin` services are gone.
- Whether losing one service ends the whole `t7-twin` workflow is **not documented**. Plan to restart it.
- With today's files `t7-twin` cannot start on one node at all: Nemotron's `exclusive` leaves no room for the board (finding 1).
- A forecast `extract` on the lost node fails. The dispatcher clears the gap. Press Update again.

### A GPU is held by a stuck job

| Sign | Check (cluster owner) | Fix |
|---|---|---|
| Updates refused as busy for more than 10 minutes | `fuzzball workflow list --status started`; `fuzzball queue show --mine` | `fuzzball workflow stop <id>` on the stale workflow. |
| Forecast `Pending` | `fuzzball workflow why <workflow-id> <allocation-id>` gives the reason | If `INSUFFICIENT_RESOURCES`: find and stop what holds the GPU or the node. |
| Job running but silent | The platform does not detect a hung command [PAR]. | Only the timeout ends it. Hence 10 m, not 30 m, on `extract`. |

### A volume is unavailable

| Case | Effect | Source |
|---|---|---|
| A named volume does not exist | The workflow is rejected at submission. | [VOLS] |
| NFS is down while services run | **Not documented.** Expect the board to fail reading `forecast.json` and every job to fail on its mounts. No degraded mode on the cluster; use the laptop mockup. | n/a |
| `hfcache` missing | Nemotron cannot load. Run mode F. | `t7-twin.fz` |
| `clif_work` or `tooling` missing | No forecast. The board keeps the last good files from `twin-store`. | `t7-forecast.fz` |
| First use of an image on a node | Slow first start while the image is fetched and converted. Warm both nodes at the rehearsal. | [VOLS] |

## 7. Checklist for the demo

1. `t7-build` has finished. No `t7-*` workflow is queued or running except `t7-twin`.
2. `t7-fit` ran before `t7-twin` started. Probes are saved.
3. The forecast `extract` no longer sets `exclusive: true`, or a rehearsal proved it starts beside `t7-twin`.
4. `t7-twin` shows three services RUNNING, Nemotron on one node, board and dispatcher on the other.
5. One unit update ran end to end. Write down: seconds waiting, seconds in `extract`, total seconds.
6. One room update ran. Both nodes have now pulled every image.
7. The no-chat copy of `t7-twin.fz` is rendered and validated, ready for mode F.
8. One person owns `workflow stop`. Nobody starts a workflow by hand during the demo.

## 8. Open questions for the cluster owner

Only a live check can answer these. Nobody runs them now.

1. Does a forecast `extract` with `exclusive: true` start while the board and dispatcher sit on the same node? (`workflow why` on the pending allocation.)
2. In a running `t7-twin`, which node holds each service? Did the board and dispatcher land together? (`workflow describe`, `queue show --mine`.)
3. What does `fuzzball node list --available` show for our two nodes: 20 cores and 127.9 GB each?
4. Is the memory request enforced as a limit, and does GPU memory on GB10 count against it? (Peak `free -g` inside Nemotron and inside `extract`.)
5. How much memory does vLLM really take at `--gpu-memory-utilization 0.85` on GB10? Does chat still work at 0.60?
6. What is the scheduler interval on this cluster (default 60 s)? How long does each forecast job wait before it starts?
7. Is preemption enabled? Is backfill left on?
8. When two nodes both fit, which one does the scheduler pick?
9. If one `t7-twin` service dies with its node, does the workflow end or keep the other services?
10. Does a `Pending` job ever time out on its own?
11. Is the `team7` provisioner free of `local: true`? (`fuzzball volume provisioner info team7`.)
12. Peak memory and run time of `extract` for 25 patients, and of the three `t7-fit` jobs.

## Sources

Fuzzball 4.3 documentation, read 2026-11-14:

- [WS] Workflow syntax (resource, `exclusive`, services, `persist`, probes, `depends-on`, task-array, multinode, restart tolerance, status values, node-local volumes): https://docs.ciq.com/fuzzball/4.3/appendices/workflow-syntax
- [CONF] Configuration reference (scheduler interval, priority expression, preemption, backfill, shared and exclusive node pools): https://docs.ciq.com/fuzzball/4.3/central-config/configuration-reference
- [QUEUE] Queue and scheduling observability (`queue show`, `workflow why`, reasons): https://docs.ciq.com/fuzzball/4.3/scheduler-admin/queue-observability
- [PRIO] Workflow priority: https://docs.ciq.com/fuzzball/4.3/scheduler-admin/workflow-priority
- [GPU] Using GPUs: https://docs.ciq.com/fuzzball/4.3/advanced-hardware/gpus
- [SPARK] Fuzzball on an NVIDIA DGX Spark (GB10: 128 GB unified, 20 cores, headroom): https://docs.ciq.com/fuzzball/4.3/cluster-admin-guide/dgx-spark
- [PAR] Parallel and distributed jobs (rank failure, hung ranks): https://docs.ciq.com/fuzzball/4.3/parallel-and-distributed
- [TASK] Job arrays: https://docs.ciq.com/fuzzball/4.3/parallel-and-distributed/parallel
- [HEALTH] Node health (nodes that go offline): https://docs.ciq.com/fuzzball/4.3/scheduler-admin/node-management/node-health
- [DEBUG] Debugging (refused lease grant, node-local volume blocking): https://docs.ciq.com/fuzzball/4.3/debugging
- [AUTO] Service autoscaling (scale to zero, one replica per node): https://docs.ciq.com/fuzzball/4.3/advanced-features/service-autoscaling
- [DRIVERS] Provisioner driver types (NFS shared, hostpath `local: true`): https://docs.ciq.com/fuzzball/4.3/volume-admin/provisioners/provisioner-driver-types
- [VOLS] Volumes, closing notes (image caching, volume not found): https://docs.ciq.com/fuzzball/4.3/volumes/vols-notes

Other:

- [VLLM] vLLM, optimization and tuning (`gpu_memory_utilization`; current docs, not checked against the pinned 25.12 image): https://docs.vllm.ai/en/latest/configuration/optimization.html
- [LENOVO] Lenovo PSREF, ThinkStation PGX (GB10, 20 Arm cores, 128 GB LPDDR5x unified system memory): https://psref.lenovo.com/syspool/Sys/PDF/ThinkStation/ThinkStation_PGX/ThinkStation_PGX_Spec.html

Repo files read: `backend/fuzzball/t7-fit.fz`, `t7-forecast.fz`, `t7-twin.fz`, `t7-ward.fz`, `t7-smoke.fz`; `backend/app/dispatcher.py`; `backend/docs/LIVE_DEMO.md`, `CLUSTER_FACTS.md`; `docs/ARCHITECTURE.md`; `docs/diagrams/workflow.html`; `backend/icutwin/config/extraction.yaml`.

Not documented in Fuzzball 4.3: which node is chosen when several fit; GPU sharing of any kind; whether a resource request is a hard limit; how unified GPU memory is accounted; a time limit on pending jobs; what a workflow does when one of its services dies; behaviour when shared storage goes away under running work.

# Fuzzball 4.3 review of the ICU Lookahead workflows and dispatcher

Read this if you want to see each workflow construct checked against the Fuzzball 4.3 documentation; it is a dated record of the files as read on 2026-11-14 at 14:24 CST, so use [`RUNBOOK.md`](../../backend/docs/RUNBOOK.md) to run the app and [`../../docs/ARCHITECTURE.md`](../ARCHITECTURE.md) for the overview.

**Archived 2026-11-15** from `backend/docs/`. File names in the text are relative to `backend/` as it was then.

**Status:** The team ran ICU Lookahead end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, and it worked. Statements below that nothing had run describe the time of writing.

Superseded since this review: line numbers, and findings about constructs that later changed. In the files on `main` the dispatcher fetches the Fuzzball CLI with Python (no `apt`, no `wget`), the board endpoint is `protocol: http` (the proxy ends TLS), and the probe comes from job 4, with `t7-fit` as the fallback. Current state:

| Topic | Current state (code on `main`) |
|---|---|
| How to run | `scripts/launch.sh` first ([`RUNBOOK.md`](../../backend/docs/RUNBOOK.md)); the manual workflow steps are the fallback |
| Volumes | `twin-store` is the one volume ICU Lookahead writes (code, packages, stage ward, forecast files). `mimic_clif` is only read, at `/data`. `hfcache` holds the Nemotron weights. `clif_work` and `tooling` are not used |
| Probe | Fitted by job 4 in vaishvikc/ICU-Twin and staged at `/store/train/probe-final.joblib` with `probe-final.meta.json`. `t7-fit` is the fallback |
| Names | Generated per room number by `app/fake_names.py` (`--names fake`). `name.parquet` is no longer read |
| Code on the cluster | Published by `t7-code` from this repo's `backend/` at a pinned commit. Training (`job_2` to `job_4`) is in vaishvikc/ICU-Twin; there is no `t7-build` here |
| Schedule and cut | One run at 07:00; each patient is cut 24 h after ICU arrival; five predictions on the board |

## Scope of this review

Read-only review against the official docs at `https://docs.ciq.com/fuzzball/4.3` (all 229 pages of the 4.3 tree were downloaded on 2026-11-14 and searched; the pages in section 5 were read). Nothing was run on the cluster: no `fuzzball` CLI, no MCP call, no `workflow validate`. No repo file was edited.

Working tree first read at 14:14 CST and read again at **2026-11-14 14:24:29 CST**; every line number below is from the 14:24 read (see "Late changes" at the bottom). Other people were editing the `.fz` files and `dispatcher.py` during the review, so find a construct by name if a line has moved.

Doc keys used below (prefix every path with `https://docs.ciq.com/fuzzball/4.3/`):

| Key | Page |
|---|---|
| [WS] | `appendices/workflow-syntax` |
| [API] | `advanced-features/in-workflow-api-access` |
| [EP] | `advanced-features/workflow-endpoints` |
| [CON] | `advanced-features/workflow-connect` |
| [HOST] | `advanced-features/job-hostnames` |
| [GPU] | `advanced-hardware/gpus` |
| [SPARK] | `cluster-admin-guide/dgx-spark` |
| [URL] | `creating-fuzzfiles/container-urls` |
| [START] | `quick-start/uqs-starting-and-stopping-workflows` |
| [STATUS] | `quick-start/uqs-interacting-with-workflows/uqs-workflow-status` |
| [LOGS] | `quick-start/uqs-interacting-with-workflows/uqs-retrieve-logs` |
| [RN431] | `release-notes/v4.3.1` |
| [RN430] | `release-notes/v4.3.0` |
| [DBG] | `debugging` |
| [MCP] | `mcp-server` |
| [CLI] | `appendices/cli-installation` |
| [VOLC] | `volumes/vols-operations/vols-ops-creation` |
| [VOLN] | `volumes/vols-notes` |
| [CAT] | `workflow-catalog/existing-templates` |
| [SDK] | `sdk/sdk-coding-examples/sdk-code-listwfs` |
| [BILL] | `cloud-admin-guide/billing/per-workflow-charges` |
| [CONF] | `central-config/configuration-reference` |

## 1. Verdict per file

| File | Verdict | Why |
|---|---|---|
| `fuzzball/t7-forecast.fz` | **OK, one minor fix** | Syntax matches the 4.3 reference. The `exclusive: true` on `extract` was removed during this review (now line 63; F1). Hand-start line 13 has no `--name` (F9). |
| `fuzzball/t7-fit.fz` | **OK** | Syntax matches. The `exclusive: true` on `extract` was removed during this review (now line 56; F1). |
| `fuzzball/t7-smoke.fz` | **needs fixes (minor)** | Syntax matches. `exclusive: true` on lines 79 and 96 (F1); header line 8 starts the unrendered file (F10). |
| `fuzzball/t7-twin.fz` | **needs fixes** | Syntax matches; all three services have readiness probes. The dispatcher bootstrap can exit nonzero, which on 4.3.1 fails the whole workflow (F3). CLI location and open node ports: F5, F6. |
| `fuzzball/t7-ward.fz` | **OK** | Syntax matches; CPU only; all three tokens (`@CLIF_DIR@`, `@WARD_IDS@`, `@NAMES@`) are rendered by `--render-only`. Only the shared image-pin note (F7). |
| `app/dispatcher.py` | **needs fixes (minor)** | `workflow list -o json`, the status handling and the token refresh match the docs. The start output is parsed as a bare id although the docs show two formats (F4); the new 5-minute pending limit compares against the word `PENDING`, which the JSON output may not use (F14); `DOWN` is treated as terminal (F8); `--name` on `workflow start` is not in the docs (section 4). |
| `docs/LIVE_DEMO.md` §9 | **needs fixes** | The hand-start `sed` (line 437) leaves `@CLIF_DIR@` and `@NAMES@` in the file (F2). Other commands match. |
| `docs/LIVE_DEMO.md` §2, §6 | mostly OK | Commands match the docs. §2.5 says the board survives a lost service; the docs say a failed service fails the workflow (F3). |
| `docs/CLUSTER_FACTS.md` | OK with one gap | Claims agree with the docs. The GPU rule (line 12) does not say that `exclusive` takes the whole node (F1). |
| `docs/FUZZBALL_TEST_PLAN.md` | not present | Referenced by `t7-ward.fz:3`; the file did not exist at review time. `docs/FUZZBALL_CLI.md` and `docs/FUZZBALL_PLAN.md` (LIVE_DEMO lines 195, 361) are also missing. |

Nothing found in any `.fz` file is expected to fail `fuzzball workflow validate` on documented grounds: every key, nesting level, enum value and unit was checked against [WS] (section 3), and an offline structural lint built from [WS] passed all five files. That is not a substitute for the live validate (section 4).

## 2. Findings, by severity

| # | Severity | Where | Finding | Doc | Fix (exact text) |
|---|---|---|---|---|---|
| F1 | **High**, fixed during the review in `t7-forecast.fz:63` and `t7-fit.fz:56`; still open in `t7-smoke.fz:79`, `:96` | interacts with `t7-twin.fz:21` | `exclusive: true` means the whole **node**: "If true, job gets exclusive access to the node." 4.3.0 fixed "whole-node-exclusive jobs were placed onto nodes that already had other work", so such a job now waits for an empty node. With `t7-twin` up, node A is held exclusively by `nemotron`, so `board` and `dispatcher` must sit on node B, and the forecast `extract` never finds an empty node. It stays Pending, or the lease is refused ("could not set exclusive mode, other resources in use") and the workflow fails after about 10 minutes. The GPU needs no `exclusive`: each node has one `nvidia.com/gpu`, so a request for 1 already takes it. `docs/COMPUTE_PLAN.md` reaches the same conclusion independently. | [WS] jobs fields; [RN430] scheduler fixes; [DBG] "Blocking on a Refused Lease Grant"; [SPARK] node shape 20 cores, 127.9 GB, `nvidia.com/gpu:1` | Already applied by the other editor: `t7-forecast.fz:63` is now `{cpu: {cores: 8}, memory: {size: 48GB}, devices: {nvidia.com/gpu: 1}}` and `t7-fit.fz:56` has no `exclusive`; both match the docs. Still to do, `t7-smoke.fz:79` and `:96`: `resource: {cpu: {cores: 16}, memory: {size: 64GB}, devices: {nvidia.com/gpu: 1}}`. Node B with a refit: board 2 + dispatcher 1 + extract 16 = 19 of 20 cores and 106 of 127.9 GB. `nemotron` may keep `exclusive: true`. Add to `CLUSTER_FACTS.md:12`: "`exclusive: true` takes the whole node, not the GPU; only `t7-build` and Nemotron use it." |
| F2 | **High** (fallback path only) | `docs/LIVE_DEMO.md:437`, `:422` | The hand-start `sed` replaces four tokens; `t7-forecast.fz` now has six. `@CLIF_DIR@` and `@NAMES@` survive. `validate` passes (the tokens are inside scripts), then `precheck` exits 1 with "no ward CLIF folder at @CLIF_DIR@"; with only `@NAMES@` left, `rooms.py` would get the literal `@NAMES@` as an argument. The header of `t7-forecast.fz` (line 13) already has the right command. | [WS]: no parameters section exists, so nothing else fills a token | Line 437: `sed 's/@SCOPE@/unit/;s/@ROOM@/0/;s/@HOURS@/0/;s/@WARD_FLAG@//;s/@NAMES@//;s#@CLIF_DIR@#/store/code/clif_demo#' fuzzball/t7-forecast.fz > /tmp/t7-forecast-manual.fz`. Line 422: list all six tokens (`@CLIF_DIR@`, `@NAMES@` added). |
| F3 | **High** | `t7-twin.fz:80-91` (dispatcher bootstrap), `:54`, `:33`; `docs/LIVE_DEMO.md:228`, `:230` | On 4.3.1, "a service that exits on its own with a nonzero code now ends FAILED" and "any other exit code ends it FAILED and fails the workflow". The dispatcher script runs under `set -euo pipefail`: a failed `apt-get`, a failed `wget`, or the sha256 mismatch (`exit 1`, line 91) fails **all of `t7-twin`**, so Nemotron and the board go down with it, the endpoint URL is removed and every workflow token dies. The same holds if `board.py` or `vllm serve` crashes. This contradicts gap G7 ("the board works while the others are down") and LIVE_DEMO §2.5 rows "Node with Nemotron fails" and "The board or dispatcher is on the failed node": with no restart policy "a node fault or an offline node fails it", and a failed service fails the workflow. | [RN431] upgrade notes; [WS] services intro; [WS] Restart Tolerance; [EP] "An endpoint is alive only while the workflow ... is still running"; [API] token "stops working as soon as its workflow finishes, fails, or is canceled" | Replace `t7-twin.fz:80-81` with: `set -uo pipefail` and `until apt-get -qq update >/dev/null && apt-get -qq install -y wget ca-certificates tzdata >/dev/null; do echo "apt failed; retry in 20 s"; sleep 20; done`. Wrap the `wget` (lines 87-88) the same way: `until wget -q ... ; do echo "CLI download failed; retry in 20 s"; sleep 20; done`. Line 91: replace `rm -f "$CLI"; exit 1;` with `rm -f "$CLI"; CLI=/nonexistent/fuzzball;` and line 95 with `[ -f "$CLI" ] && chmod 500 "$CLI"` (the dispatcher then starts and answers "cannot list workflows", and the board shows the reason). Untested. LIVE_DEMO:228 and :230: "the service fails, so `t7-twin` fails as a whole: restart `t7-twin` (new URL, new token)". |
| F4 | Medium | `app/dispatcher.py:562` | `wid = self._cli("workflow", "start", ...).strip()` assumes stdout is the bare id. The docs show two formats: `Workflow "3cc718d1-..." started.` in [START] and a bare UUID in [API] and [CAT]. With the first format the "workflow id" in `runs.jsonl`, in `/run` replies and in `inflight` is a sentence. Reaping still works by name. | [START]; [API] "Using the token"; [CAT] | `out = self._cli("workflow", "start", str(path), "--name", name)` then `m = re.search(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", out); wid = m.group(0) if m else out.strip()` |
| F5 | Medium | `t7-twin.fz:85` | The docs say the CLI binary "is larger than a job container's writable layer so it must be downloaded into a mounted volume". `/dev/shm` is not a mounted volume; whether tmpfs in a service is large enough and how it counts against the 2 GB memory request (line 73) is not documented. | [API] "Installing the Fuzzball CLI in a job container" | Keep `/dev/shm` if the rehearsal log shows the download and a working `workflow list`. Documented fallback that still avoids the shared `/store`: add `cli: {use: team7, size: 1GB}` under `volumes`, set the dispatcher's `mounts: {/store: store, /cli: cli}` and `CLI_DIR=/cli` (an ephemeral volume, mounted by this service only). |
| F6 | Medium | `t7-twin.fz:24`, `:47`, `:76` | "Each declared port is published on the node at the declared port" and "a service also listens on its node's port, where requests arrive without passing through the endpoint proxy at all". So `dispatcher:9000` (`POST /run` starts GPU workflows), `nemotron:8000` and `board:8080` answer on the node address without the endpoint's `scope: group` check. Who can reach the node network is a cluster fact, not in the docs. | [WS] services `network`; [EP] caller identity warnings | No Fuzzfile change is documented that hides a declared port. Keep the dispatcher's own checks (role, guards) as the only gate, and ask CIQ whether other teams' jobs can reach our nodes' ports. |
| F7 | Medium | every `image:` line (`t7-fit.fz:35,53,66`; `t7-forecast.fz:42,58,80`; `t7-smoke.fz:40,61,76,93,109`; `t7-twin.fz:18,39,67`; `t7-ward.fz:41,57`) | Images are pinned by tag, none by digest. `python:3.12-slim` moves with every patch release. The docs: "Pulling containers by hash is considered the best strategy for reproducibility." | [URL] | Form: `image: {uri: "docker://docker.io/library/python@sha256:<digest>"}` and likewise `docker://nvcr.io/nvidia/pytorch@sha256:<digest>`. The arm64 digests were not looked up in this review. |
| F8 | Low | `app/dispatcher.py:83-86`, comment at `:78-80`, docstring at `:177-178` | `DOWN` is in `FAILED_STATES`, so it counts as ended and failed. The docs: "`down` is an autoscaled service scaled to zero — not terminal". No `t7-*` GPU workflow has an autoscaled service, so today this cannot trigger. | [MCP] "Workflow status words"; [WS] "Workflow Status Values" | `FAILED_STATES = frozenset({"ERRORED", "FAILED", "CANCELED", "CANCELLED", "STOPPED"})` and drop `Down` from the two comments. `FAILED` must stay: the enum for "ended with errors" is `STAGE_STATUS_FAILED`. |
| F9 | Low | `t7-forecast.fz:13` | The hand-start in the header has no `--name`. An unnamed workflow is named after its file ("The workflow is named `printer.fz`, after the Fuzzfile used at submission"), here `f.fz`, which the dispatcher's guard `^t7-(\w+-)?(build|forecast|smoke|fit|ward)` does not match. A second update could start beside it. | [STATUS] | End of line 13: `... > /tmp/f.fz && fuzzball workflow start /tmp/f.fz --name t7-forecast-manual` |
| F10 | Low | `t7-smoke.fz:8` | The header starts `fuzzball/t7-smoke.fz` unrendered, against lines 26-27. The run would fail at ingress (URL ends in `@CODE_REF@`). | [WS] volumes `ingress` | `#   sed "s/@CODE_REF@/<sha>/g;s/@CODE_SHA256@/<sha256>/g" fuzzball/t7-smoke.fz > /tmp/t7-smoke.fz && fuzzball workflow validate /tmp/t7-smoke.fz && fuzzball workflow start /tmp/t7-smoke.fz --name t7-smoke` |
| F11 | Low | `app/dispatcher.py:783-785` | `last_refresh` is set before the call, so a failed refresh is retried 24 hours later although the log says "will retry". Still inside the 7-day window the docs require ("daily, for example"). | [API] "Refreshing the token" | `if time.time() - self.last_refresh > 86400 and refresh_token(): self.last_refresh = time.time()` plus a floor so a failing call is tried at most hourly. |
| F12 | Low | `docs/LIVE_DEMO.md:305`, `:319`; `:377`; `app/dispatcher.py:8-9` | Wording. The CLI prints `Started`, not RUNNING (`RUNNING` exists only in `depends-on`). G7 and the dispatcher docstring still say the CLI is on `/store/bin`; `t7-twin.fz` uses `/dev/shm`. | [WS] "Workflow Status Values" | 305: `# nemotron, board and dispatcher Started`. 319: `# extract Started on the free node`. 377 and the docstring: `--cli "$CLI"` on `/dev/shm`. |
| F14 | Medium | `app/dispatcher.py:430` (added during the review) | The 5-minute limit fires on `st == "PENDING"`. The docs give the pending state as `Pending` in the CLI table but `STAGE_STATUS_UNSPECIFIED` in the enum that `-o json` and the SDK return. `_status_of` turns that into `UNSPECIFIED`, so a forecast that cannot be placed would be stopped only by the 45-minute limit. The `workflow stop <id>` call itself (line 437) matches the docs, and the workflow token may stop the owner's workflows. Stop is asynchronous: the status reads `started` for a moment, then `canceled`. | [WS] "Workflow Status Values"; [SDK]; [START]; [API]; [MCP] | Line 430: `if st in ("PENDING", "UNSPECIFIED", "") and age > self.pending_limit_s:` |
| F13 | Info | `t7-fit.fz:4`, `t7-forecast.fz:2-4`, `t7-ward.fz:6`, `t7-twin.fz:63`, `LIVE_DEMO.md:422`, `:458` | "Fuzzball 4.3 has no parameters" is right for Fuzzfiles: [WS] lists no parameters or variables section, and no `--set` appears anywhere in the docs. Two qualifications: catalog templates do take values (`fuzzball workflow catalog start/render --values K=V`), and [START] says submission "substitutes workflow variables" without defining them. No cron or schedule feature is documented. | [WS]; [CAT]; [START] | Optional wording: "plain Fuzzfiles have no parameters (only catalog templates take `--values`)". |

Checks asked for explicitly:

- **Would fail `workflow validate`**: nothing found on documented grounds.
- **Services without readiness probes**: none. `nemotron` (`http-get /v1/models:8000`), `board` and `dispatcher` (`tcp-socket`) all have one.
- **GPU requests**: `devices: {nvidia.com/gpu: 1}` on `t7-fit` extract (56), `t7-forecast` extract (63), `t7-smoke` train-demo (79) and sglang (96), `t7-twin` nemotron (21). The form matches [WS] and [GPU]. `exclusive` remains beside it only in `t7-smoke` and on Nemotron (F1).
- **Images not pinned**: all pinned by tag, none by digest (F7).
- **Token placeholders that survive rendering**: the dispatcher's `render()` covers all six tokens of `t7-forecast.fz` (`@NAMES@` at `dispatcher.py:219`); `--render-only` covers the tokens of `t7-fit.fz` and `t7-ward.fz`; `t7-smoke.fz` refuses to run with `@CODE_REF@` or `@CODE_SHA256@` left. The one leak is the manual `sed` in LIVE_DEMO §9.5 (F2). Neither render path asserts that no `@NAME@` is left; a one-line check after `render()` would catch the next new token (`@NAMES@` was added during this review and the runbook `sed` already missed it).
- **Flags that do not exist in 4.3**: none found to be wrong. `--name` on `workflow start` is the one flag the docs do not show (section 4).

## 3. Confirmed correct (file:line → construct → doc → verdict)

All verdicts in this section are "matches docs".

### Shared by all five Fuzzfiles

| Construct | Where | Doc |
|---|---|---|
| `version: v4` | line 1 of each | [WS] version: "new workflows must use `v4`" |
| Top-level keys `volumes`, `defaults`, `jobs`, `services` only | all | [WS] top-level sections |
| Persistent volume `{name: <existing>, use: team7}` | `t7-fit:18-26`, `t7-forecast:24-32`, `t7-smoke:10-21`, `t7-twin:9-14`, `t7-ward:23-31` | [WS] volumes: `name` marks a persistent volume, `use` names the provisioner; a missing volume is rejected at submission |
| `defaults.job.mounts` as `{<absolute path>: <volume>}` and `defaults.job.env` as a `KEY=VALUE` list | `t7-fit:28-31`, `t7-forecast:34-37`, `t7-smoke:32-35`, `t7-ward:33-36` | [WS] defaults. Job `env` is merged with the default; job `mounts` replaces it |
| `image: {uri: "docker://..."}` | every job and service | [WS] image: `docker://` and `oras://` |
| `script: \|` with `#!/bin/bash` | every job and service | [WS]: `script` and `command` are mutually exclusive; no shebang means `/bin/sh` |
| `resource: {cpu: {cores: N}, memory: {size: <N>GB}}` | every job and service | [WS]: `cpu` and `memory` are required once `resource` is set; sizes such as `4GB`, `512MB`, `2GiB` |
| `devices: {nvidia.com/gpu: 1}` | `t7-fit:56`, `t7-forecast:63`, `t7-smoke:79,96`, `t7-twin:21` | [WS] devices; [GPU] |
| `exclusive: true` (valid key; see F1 for its effect) | `t7-smoke:79,96`, `t7-twin:21` | [WS] |
| `policy: {timeout: {execute: 5m\|10m\|20m\|30m\|45m\|1h\|2h}}` | jobs | [WS] policy: durations such as `2h`, `30m`, `1h30m` |
| `depends-on: [{name: <job>, status: FINISHED}]` | `t7-fit:65`, `t7-forecast:57,79`, `t7-smoke:77,94,110`, `t7-ward:56` | [WS]: only `RUNNING` and `FINISHED` are accepted |
| Job and service names are DNS-safe and unique in each file | all | [WS] naming constraint; [HOST] |
| Not used, so nothing to check: `files`, `annotations`, `preemptible`, `multinode`, `task-array`, job `network`, `egress`, secrets, `autoscaler`, `dynamic-config`, `policy.restart` | all | [WS] |

### `t7-smoke.fz`

| Line | Construct | Doc |
|---|---|---|
| 22-30 | Ephemeral volume `work: {use: team7, size: 20GB, ingress: [...]}` (no `name`, so ephemeral) | [WS] volumes: `size` is only valid without `name` |
| 29-30 | Ingress `source.uri: https://...`, `destination.uri: file://code.tar.gz` | [WS] ingress: `https://` is an allowed scheme; the destination is `file://<path>`, relative to the mount |
| 41-42, 78, 95 | Per-job `mounts` and `env` overrides | [WS] defaults: mounts replace, env merges |
| 111 | `seed` has no `policy.timeout` | [WS]: optional. `docs/COMPUTE_PLAN.md` already suggests adding 10 m |

### `t7-twin.fz`

| Line | Construct | Doc |
|---|---|---|
| 16 | `services:` with no `jobs:` | [WS]: at least one job or service |
| 22, 45, 74 | `persist: true` on all three | [WS]: a service with nothing depending on it and `persist` unset "is stopped as soon as it reports ready" |
| 24, 47, 76 | `network: {ports: [{name, port}]}` as a list; ports 8000, 8080, 9000 are distinct | [WS]: `ports` is a list; two services with the same port cannot share a node |
| 48 | `endpoints: [{name: web, port-name: web, protocol: https, type: subdomain, scope: group}]` | [WS] endpoints: all five values are allowed enum values; `port-name` refers to a declared port. Same shape as the docs' `api-server` example |
| 25 | `readiness-probe: {http-get: {path, port}, initial-delay-seconds, period-seconds, failure-threshold}` | [WS] readiness-probe: key names and nesting match |
| 49, 77 | `readiness-probe: {tcp-socket: {port}, ...}` | [WS] |
| 54-55 | `http://nemotron:8000`, `http://dispatcher:9000` from the board | [WS]: "the service name alone also resolves, via the workflow's DNS search path", at the declared port |
| 40-41 | No `depends-on` from board to nemotron | [WS]: optional |
| 87-88 | `wget --ca-certificate /run/fuzzball-substrate/trusted-certs/root-ca.crt --header "Cookie: fwi.access-token=${FB_TOKEN}" ... "${FB_UI_URL}/api/download/cli/linux/arm64"` | [API] "Installing the Fuzzball CLI": same header, same path, `linux/arm64`, same CA file |
| 98-99 | The downloaded CLI runs with no login | [API]: the CLI picks up `FB_TOKEN` and `FB_API_HOST` when no context is configured. The service mounts no home directory, so no context can take precedence |
| 62 | Comment: token may start, list and stop as the team7 user | [API] token scope |

### `t7-fit.fz`, `t7-forecast.fz`, `t7-ward.fz`

Only shared constructs (table above). `t7-ward.fz` has two CPU jobs, no GPU and no `exclusive`; its three tokens sit inside scripts and comments.

### `app/dispatcher.py`

| Line | Construct | Doc |
|---|---|---|
| 282 | `fuzzball workflow list -o json` | [CLI]: `-o, --output` is a global flag, `json` or `yaml`; [RN430] and release notes 4.0.0 |
| 284 | Rows read from a bare list or from `data["workflows"]` | [SDK]: `ListWorkflowsResponse.workflows`, each with `id`, `status` |
| 156-160, 83-86 | Status upper-cased, `STAGE_STATUS_` prefix stripped; `FINISHED`, `ERRORED`, `FAILED`, `CANCELED` end a run; anything else (including `UNSPECIFIED` = pending and `STARTED`) counts as running | [WS] "Workflow Status Values": CLI words Pending, Started, Finished, Errored, Canceled, Down; enum `STAGE_STATUS_UNSPECIFIED/STARTED/FINISHED/FAILED/CANCELED/DOWN` |
| 437 | `fuzzball workflow stop <id>` for a stuck forecast | [START]: `fuzzball workflow stop <uuid>`; [API]: the token covers stopping the owner's workflows |
| 562 | `fuzzball workflow start <file>` (the file is read by the CLI inside the service) | [API] "Using the token": `fuzzball workflow start pipeline-step.fz` |
| 5-6, `t7-twin.fz:62` | Token covers start, list, stop of the owner's other workflows | [API]: "it can also list and stop that user's other workflows" |
| 690-707 | `POST $FB_OPENAPI_URL/v4/workflows:refreshToken` with `Authorization: Bearer $FB_TOKEN`; reads `.token`; swaps `os.environ["FB_TOKEN"]` only on success; CA file passed explicitly | [API] "Refreshing the token": same URL, same header, response `{"token": ..., "expiresAt": ...}`, "only overwrite `FB_TOKEN` once you have a token in hand"; the CLI reads `FB_TOKEN` on every invocation |
| 783 | Refresh once a day | [API]: service tokens last 7 days; "refresh on a schedule comfortably inside the seven-day window (daily, for example)" |
| 267-274 | The CLI inherits the process environment | [API] |
| no call | The dispatcher never calls `workflow describe`, `status`, `log` or `validate` | nothing to check |

### `docs/LIVE_DEMO.md`

| Line | Command or claim | Doc |
|---|---|---|
| 195 | `fuzzball volume create team7 twin-store --size 5GB` | [VOLC]: `fuzzball volume create <provisioner> <name> --size 10GB` |
| 213 | Injected `FB_TOKEN`, `FB_API_HOST`, `FB_OPENAPI_URL`; scope; 7 days in a service; dies with the workflow | [API] |
| 215, 318 | `fuzzball workflow list --parent <twin-id>` | [API] "Workflow lineage" (default window: created in the last 7 days) |
| 227 | `policy.restart: on-node-fault` is the only retry option | [WS] Restart Tolerance |
| 229 | `INSUFFICIENT_RESOURCES`, `fuzzball workflow why <id> <alloc>` | [RN430]; [DBG] |
| 245, 307 | `fuzzball workflow endpoints <twin-id> board web` | [EP]: `fuzzball workflow endpoints WORKFLOW_ID [SERVICE_NAME] [ENDPOINT_NAME]` |
| 245, 308 | `fuzzball workflow connect --name board --endpoint web <twin-id>` | [CON] flags `--name`, `--endpoint` |
| 245 | `fuzzball workflow endpoints generate-token <endpoint-id> --expiration 24h`; `Authorization` or `FB-Authorization` header; the token dies with the workflow | [EP] |
| 293-295 | `fuzzball context list`, `fuzzball node list`, `fuzzball volume list` | [CLI]; [GPU]; [VOLN] |
| 297, 438, 455 | `fuzzball workflow validate <file>` | [WS] version section |
| 298, 346 | `fuzzball workflow list --status started` | [WS] "Workflow Status Values": `--status` filter value `started` |
| 305, 319 | `fuzzball workflow describe <id>` | [STATUS] |
| 306, 320 | `fuzzball workflow log <id> <job> -n 50` | [LOGS]: `-n` limits to the last N lines |
| 321 | `fuzzball report charges workflow <id> -o json` | [BILL] |
| 346 | `fuzzball mcp serve --allow-exec` | [MCP] |
| 454 | `sed` of `@CODE_REF@` and `@CODE_SHA256@` before validate and start | matches the guard in `t7-smoke.fz:48-49, 67-68` |

One addition for gap G16 ("how a browser reaches a `group` endpoint"): the Web UI has a documented **Connect** button on the workflow page that "opens the workflow's primary endpoint in a new browser tab"; with one endpoint in `t7-twin`, the board is the primary one ([EP], [CON]). So a team7 member signed in to the Web UI can open the board without the CLI.

### `docs/CLUSTER_FACTS.md`

| Line | Claim | Doc |
|---|---|---|
| 11 | GB10 node: 1 GPU, 20 cores, 128 GB unified | [SPARK]: `cpu/arm64`, 20 cores, 127.9 GB, `nvidia.com/gpu:1`; the 128 GB is shared by CPU and GPU |
| 12 | A request for the GPU holds the whole GPU; two GPU jobs never share a node | [GPU]; follows from one device per node. Missing: `exclusive` (F1) |
| 12 | No pinning to a named node | [WS] annotations select node provisioners, not nodes |
| 20 | 2-node `generic` exclusive job | [WS] multinode: `implementation: generic` |
| 40 | `use: team7` volumes on shared NFS are visible from both nodes | [WS] "Volumes on node-local storage": only `local: true` provisioners are single-node. Whether `team7` is local is a cluster fact (section 4) |
| 47 | `fuzzball run --volume` has no `:ro` | [VOLC] and other pages show only `--volume user/persistent:/data`; no read-only form is documented |
| 51 | Volume `ingress` from S3 with a team secret | [WS] ingress: `s3://` plus `secret: secret://<scope>/<name>` |
| 53 | Https ingress with a secret | [WS] ingress |
| 59 | `fuzzball workflow catalog render` | [CAT] |

## 4. Not documented: needs a live `fuzzball workflow validate` (or `--help`) after training

| # | Item | How to check |
|---|---|---|
| U1 | `fuzzball workflow validate` on each **rendered** file. The docs give the syntax but no list of validator rules; whether it also checks that the volumes exist is not stated | `python app/dispatcher.py --render-only ...` (or the `sed`), then `fuzzball workflow validate /tmp/<file>.fz` for all five |
| U2 | `--name` on `fuzzball workflow start` (`dispatcher.py:562`, LIVE_DEMO 304, 438, the `.fz` headers). Named workflows exist in the docs (Web UI prompt, `MyDescriptiveWorkflowName` in a list), but the CLI flag is not shown | `fuzzball workflow start --help` |
| U3 | What `fuzzball workflow start` prints: bare id or `Workflow "<id>" started.` (F4) | one start in the rehearsal; read `runs.jsonl` |
| U4 | Keys of `workflow list -o json` (`id`, `name`, `status`, wrapper key) and the status spelling in JSON, above all for a pending workflow (F14) | `fuzzball workflow list -o json` once; the dispatcher already accepts several spellings |
| U5 | Default page size or limit of `workflow list` (`--limit` exists). Default order is by priority, default window 7 days. A cut-off list could hide a running GPU workflow from the guard | `fuzzball workflow list --help` |
| U6 | What happens when a readiness probe passes `failure-threshold` (Nemotron's budget is 60 s + 80 × 15 s, about 21 min; the others about 5 min). The docs say only "consecutive failures before marking unhealthy" | watch `workflow describe` and `workflow events` during a cold Nemotron start |
| U7 | Whether an `exclusive` job really pends beside `t7-twin` (F1). The docs imply it; only the scheduler can confirm | after the fix is decided: `fuzzball workflow why <id> <alloc>` on a test forecast |
| U8 | Whether team7 may create an ephemeral volume on its provisioner (`t7-smoke.fz:22-24`): "the user's group must have `ephemeral` access" | `fuzzball volume provisioner info team7` or the smoke run |
| U9 | `type: subdomain` needs wildcard DNS for `*.endpoints.<domain>`. The URL form also differs between pages (`endpoint-<id>.endpoints.<domain>` in [EP], `<name>.<workflow-id>.<account>.fuzzball` in [WS]) | `fuzzball workflow endpoints <twin-id> board web`, then open it. If it does not resolve, use `type: path` (the board already runs with `--behind-proxy`) |
| U10 | `FB_UI_URL` (`t7-twin.fz:71`) and the CLI sha256 (`:72`) | first dispatcher log |
| U11 | `/dev/shm` size and memory accounting in a service (F5) | first dispatcher log |
| U12 | Whether `nvcr.io` pulls need an image secret on this cluster (CLUSTER_FACTS H2) | the smoke run; if needed: `image: {uri: ..., secret: secret://group/<name>}` per [WS] |
| U13 | Whether other teams' jobs can reach our nodes' published ports (F6) | ask CIQ |
| U14 | Whether a node loss fails the whole `t7-twin` (F3) or only the service on that node | ask CIQ; do not test on demo day |

## 5. Doc pages read

Read in full:

- https://docs.ciq.com/fuzzball/4.3 (index)
- https://docs.ciq.com/fuzzball/4.3/appendices/workflow-syntax
- https://docs.ciq.com/fuzzball/4.3/advanced-features/in-workflow-api-access
- https://docs.ciq.com/fuzzball/4.3/advanced-features/job-hostnames
- https://docs.ciq.com/fuzzball/4.3/quick-start/uqs-starting-and-stopping-workflows
- https://docs.ciq.com/fuzzball/4.3/quick-start/uqs-interacting-with-workflows/uqs-workflow-status
- https://docs.ciq.com/fuzzball/4.3/quick-start/uqs-interacting-with-workflows/uqs-retrieve-logs
- https://docs.ciq.com/fuzzball/4.3/advanced-hardware/gpus
- https://docs.ciq.com/fuzzball/4.3/release-notes/v4.3.1
- https://docs.ciq.com/fuzzball/4.3/appendices/known-issues

Read in the sections that apply (commands, flags, scope, status, scheduling):

- https://docs.ciq.com/fuzzball/4.3/advanced-features/workflow-endpoints
- https://docs.ciq.com/fuzzball/4.3/advanced-features/workflow-connect
- https://docs.ciq.com/fuzzball/4.3/advanced-features/serving-a-model
- https://docs.ciq.com/fuzzball/4.3/cluster-admin-guide/dgx-spark
- https://docs.ciq.com/fuzzball/4.3/creating-fuzzfiles/container-urls
- https://docs.ciq.com/fuzzball/4.3/release-notes/v4.3.0
- https://docs.ciq.com/fuzzball/4.3/release-notes/v4.1.0 and `/v4.0.0` (CLI flags)
- https://docs.ciq.com/fuzzball/4.3/debugging
- https://docs.ciq.com/fuzzball/4.3/mcp-server
- https://docs.ciq.com/fuzzball/4.3/appendices/cli-installation
- https://docs.ciq.com/fuzzball/4.3/volumes/vols-operations/vols-ops-creation
- https://docs.ciq.com/fuzzball/4.3/volumes/vols-notes
- https://docs.ciq.com/fuzzball/4.3/workflow-catalog/existing-templates
- https://docs.ciq.com/fuzzball/4.3/workflow-catalog/creating
- https://docs.ciq.com/fuzzball/4.3/sdk/sdk-coding-examples/sdk-code-listwfs
- https://docs.ciq.com/fuzzball/4.3/cloud-admin-guide/billing/per-workflow-charges
- https://docs.ciq.com/fuzzball/4.3/central-config/configuration-reference (node `exclusive` levels)

The other pages of the 4.3 tree were searched by keyword only (`exclusive`, `--name`, `--set`, `--values`, `variable`, `cron`, `readiness`, `workflow list`, `workflow start`, `-o json`). The 4.3 docs have no single CLI reference page: flags come from examples and release notes, which is why section 4 lists `--help` checks.

## Late changes

The files were edited by someone else while this review ran. Reads: 14:14, 14:20:55 and 14:24:29 CST. All line numbers are from the last read.

- 14:15: `t7-ward.fz` appeared; cohort paths moved to `/rows/stage/unit25`; `ward` joined the dispatcher's busy pattern (`dispatcher.py:76`).
- Between 14:21 and 14:24: `exclusive: true` was removed from `t7-forecast.fz` (now line 63, with 8 cores, 48 GB and a 10 m timeout) and from `t7-fit.fz` (line 56), which settles most of F1. A sixth token `@NAMES@` was added to `t7-forecast.fz` (line 91) and `t7-ward.fz` (line 51) and to both render paths. The dispatcher gained a bounded wait that calls `workflow stop` (lines 417-459; F14). `docs/LIVE_DEMO.md`, `docs/CLUSTER_FACTS.md` and `t7-smoke.fz` did not change.
- The offline structural lint was run again on the 14:24 files: all five still pass.

Anything edited after 14:24:29 CST is not covered.

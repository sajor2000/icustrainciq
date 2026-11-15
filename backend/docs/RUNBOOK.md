# Runbook: setting up and relaunching ICU Horizon on the cluster

Read this if you need to start ICU Horizon on the cluster, publish new code to it, or bring it back after a break.

How to get the dashboard running from nothing, and how to bring it back after a
break. Companion to [`LIVE_DEMO.md`](LIVE_DEMO.md) (what to say) and
[`FUZZBALL_TEST_PLAN.md`](../../docs/archive/FUZZBALL_TEST_PLAN.md) (what to check).

The team ran ICU Horizon end to end on the two Lenovo machines under Fuzzball with `scripts/launch.sh` on 2026-11-14, and it worked. This is the procedure that was used.

Everything runs from `backend/` in this repo (`cd backend` first) on a laptop with the `fuzzball` CLI logged in.

This runbook is Kaveri's, written in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin) where the app sits at the repo root; here the same files sit under `backend/`, and the code the cluster runs is published from this repo.

---

## 0. What lives where

The cluster keeps state between workflows, so most days you do **not** repeat
the setup: you only relaunch (§3).

| On the cluster | Holds | Set up by | Survives |
|---|---|---|---|
| `mimic_clif` (volume) | raw CLIF, tokens, the model, `/dashboard_data` (the 25-patient ward) | loaded once | yes |
| `hfcache` (volume) | Nemotron weights | lane 2, once | yes |
| `twin-store` (volume) | `/store/code`, `/store/py`, `/store/stage`, forecasts | `t7-code` | yes |

The laptop holds no patient data and runs nothing but a browser and the CLI.

---

## 1. One-time setup

Only needed on a fresh cluster, or if a volume was deleted.

```bash
fuzzball context create <name> <api-host> <auth-url> fuzzball-cli
fuzzball context use <name>
fuzzball context login
```

```bash
fuzzball volume create team7 twin-store --size 20GB --description "code, packages, model, stage ward, forecast outputs"
```

> **Size note.** Earlier notes say 5 GB, written when `tooling` and
> `clif_work` were separate volumes. `twin-store` now absorbs both
> (`/store/py`, `/store/stage`, `/store/train`), so 20 GB is the safer number.

Check `fuzzball volume list` shows `mimic_clif`, `hfcache` and `twin-store`.

---

## 2. After any code change

The cluster runs a **pinned commit**, not your working tree. Publishing is two
steps and takes a few minutes.

```bash
git push origin <branch>
```

Render the workflow files against the commit you just pushed (writes
`fuzzball/ready/`, downloads the tarball once to hash it, starts nothing):

```bash
PATH="$PWD/.venv/bin:$PATH" bash scripts/make_ready.sh $(git rev-parse HEAD)
```

> The render script needs Python 3.10+; the `PATH` prefix points it at the
> project venv. Without it you get `TypeError: unsupported operand type(s) for |`.

**Check the ingress before starting anything**: this one line is the guard
against publishing the wrong repo:

```bash
grep -h "uri:.*http" fuzzball/ready/*.fz | sort -u
```

Expect exactly one URL, `codeload.github.com/sajor2000/icustrainciq/tar.gz/<sha>`.

Then publish it to `/store/code`:

```bash
fuzzball workflow start fuzzball/ready/t7-code.fz --name t7-fc-code
```

`t7-code` is CPU-only and safe beside training, but **not** beside a forecast,
`t7-fit` or `t7-ward`: it swaps the code they import.

---

## 3. Launching the dashboard

Once the code is published and the ward is staged, this is the whole thing:

```bash
bash scripts/launch.sh
```

It runs whatever is missing, waits for the board's readiness probe (up to 20 min while
Nemotron loads from `hfcache`), prints the HTTPS link and opens it.

**After publishing new code (§2), restart the app.** A `t7-twin` that is already
running is left alone by the plain command, and its board and dispatcher keep the
code they loaded when they started. To make them load the new `/store/code`:

```bash
bash scripts/launch.sh --restart
```

This stops the running `t7-twin`, waits for the node to free its ports and starts it
again (Nemotron reloads, so allow the same wait). Forecast jobs need no restart: each
one is a new workflow and reads `/store/code` when it starts.

Variants:

```bash
bash scripts/launch.sh --link
```

Prints the link of the already-running board. Use this if you close the tab
mid-demo. It starts nothing.

```bash
bash scripts/launch.sh --forecast
```

Runs a fresh forecast first, then opens the board.

```bash
bash scripts/launch.sh --no-open
```

Prints the URL without opening a browser.

---

## 4. Full sequence from cold

Only after a new model, a new ward, or a wiped `twin-store`.

```bash
bash scripts/launch.sh --all
```

That is publish code, stage the ward, forecast, then open the board. The steps
it runs, and what each leaves on the cluster:

| # | Workflow | GPU | Leaves behind |
|---|---|---|---|
| 1 | `t7-code` | no | `/store/code`, `/store/py` |
| 2 | `t7-ward` | no | `/store/stage` (25 rooms, vocab checked against the model) |
| 3 | `t7-forecast-unit` | **1** | `/store/rooms.json`, `/store/forecast.json` |
| 4 | `t7-twin` | **1** | board + dispatcher + Nemotron, and the link |

**The probe is not in this list.** It comes from `workflows/job_4_probe` (job 4, in vaishvikc/ICU-Twin), fit
beside the model it belongs to. The forecast reads it from
`/store/train/probe-final.joblib`; `fuzzball/t7-fit.fz` is a fallback for when
job 4 has not run. If `twin-store` is ever recreated, stage it again.

**Where to run this: on the cluster, not on the laptop.** The two commands below
need both volumes, `mimic_clif` at `/data` and `twin-store` at `/store`, and the
published code (`PYTHONPATH=/store/py:/store/code`). The laptop has neither. Run
them inside a job that mounts both: a one-line CPU job, or a shell in a running job
that already mounts them (`fuzzball workflow exec`), as
[`FUZZBALL_TEST_PLAN.md`](../../docs/archive/FUZZBALL_TEST_PLAN.md) section 5 does for clean-up. No
workflow file in this repo does this step yet; job 4 in vaishvikc/ICU-Twin is the
owner of the probe.

```bash
mkdir -p /store/train
cp /data/model_output/final/probe.joblib /store/train/probe-final.joblib
```

then, in the same job, write its provenance sidecar (`apply_probes` refuses a probe
without one):

```python
from pathlib import Path
from icutwin.scoring.rep_based import write_scores_meta
write_scores_meta(Path("/store/train/probe-final.joblib"), Path("/data/model_output/final"))
```

**Two GPUs total.** Nemotron holds one for the whole demo, the forecast uses the
other, so a forecast and the board coexist, but nothing else GPU-bound does.

---

## 5. Checking it is alive

```bash
fuzzball workflow list | head
```

```bash
fuzzball workflow describe <id>
```

```bash
fuzzball workflow log <id> <job> -n 50
```

```bash
fuzzball queue show --mine
```

`ready` means waiting for room, `running` means placed. If allocations sit
`ready` while `fuzzball node list` shows idle nodes, ask the scheduler directly:

```bash
fuzzball workflow why <workflow-id> <allocation-id>
```

Board-level checks: the page loads at the endpoint, `/api/forecast` returns a
recent `made_at`, and `/api/runs` lists the dispatcher's runs.

---

## 6. Stopping

```bash
fuzzball workflow stop <id>
```

Stop `t7-twin` when you are done with the GPUs. `/store/code` and the ward
survive, so the next launch is §3 alone.

---

## 7. Things that went wrong once, and the fix

| Symptom | Cause | Fix |
|---|---|---|
| `volume "twin-store" not found` on every validate | the volume was never created at onboarding | §1 |
| `unknown option(s) ['horizon_after_threshold_s']` | the key was commented out in `winnowing.yaml`, so `-c` rejected it | fixed: it is now listed as `null` |
| `ModuleNotFoundError: transformers` in a CPU job | `icutwin.common` imported it at module level | fixed: `exclude_demo` uses `tokenizer.helpers.Logger` |
| `object "…" already exists with different content` | the object cache refuses silent overwrites | `fuzzball object delete -f <uri>` then `put` |
| A workflow published the wrong repo | the ready files were rendered from another repo | re-render (§2) and check the ingress line |
| `TypeError: unsupported operand type(s) for \|` | system `python3` is older than 3.10 | prefix `PATH` with `.venv/bin` (§2) |
| Board shows "No forecast yet" | correct empty state: no forecast has run | `scripts/launch.sh --forecast` |
| `probe.joblib has no probe.meta.json` | job 4's code predates the provenance sidecar | stage it as in §4 |
| Chat says "Nemotron is not answering yet" | the service is still loading, or not running | wait, or run `t7-twin` without it (`COMPUTE_PLAN.md` mode F) |

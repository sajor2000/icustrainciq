# Proposed changes for the ICU-Twin repo

Read this before the team decides what to change in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin). Nothing here has been applied there. Everything was written by reading branch `t7/fb-job5-launch` at commit `875358a` (2026-11-15) without changing it.

| File | What it is | How to apply |
|---|---|---|
| [`icu-twin/README.md`](icu-twin/README.md) | A proposed README: the five predictions with their held-out AUROC, how it works, exactly how the CIQ, NVIDIA and Lenovo stack was used, how to run job 5, and the team | Copy it over ICU-Twin's `README.md` |
| [`icu-twin/README.patch`](icu-twin/README.patch) | The same change as a diff against the branch's README | In an ICU-Twin checkout on that branch: `git apply README.patch` (checked: it applies cleanly) |
| [`../HOW_WE_USED_CIQ.md`](../HOW_WE_USED_CIQ.md) | The full account: hardware, software, each Fuzzball feature, each workflow's jobs, images and resources | Lives in this repo; the proposed README links to it |

## What the proposed README fixes

1. **The predictions.** The README on the branch lists "hypotension" among the forecasts. The code has no hypotension task: `examples/probe_tasks.yaml` has six classifiers (ward, step-down, ventilator, vasopressor start, CRRT start, death) and `app/aggregate.py` shows five predictions. The proposal names the five and explains why there are six classifiers.
2. **How the stack was used.** The branch README lists the jobs by name. The proposal adds what each job runs on (CPU, one GPU, two GPUs), the three volumes and the object cache, and the NVIDIA images and models.
3. **The team.** The branch README has no team list; the proposal adds names and affiliations, with no roles.
4. **The results.** The held-out AUROC table from the slides, so the README carries the numbers the pitch shows.

## Things found while reading the code (not fixed: they are code or workflow changes)

| # | Where | What | Suggestion |
|---|---|---|---|
| 1 | `workflows/job_4_probe` and `job_5_launch` | Job 4 installs the classifiers at `mimic_clif:/model_output/final/probe.joblib`. Job 5 reads `twin-store:/train/probe-final.joblib` and its `.meta.json`. No workflow copies one to the other | Document the manual copy in job 5's README, or point job 5 at `final/` |
| 2 | `app/static/index.html`, `app/board.py` | The page still offers "Update the unit"; with no dispatcher in job 5 it answers "no dispatcher configured" | Hide the button when the board starts without `--dispatcher`, or say on the page that a new forecast means restarting job 5 |
| 3 | `workflows/job_4_probe/README.md` | Says the probe is saved "in `final/`, so inference loads the model and the probes from one folder"; job 5 does not read it from there (see 1) | Align the README with whichever path the team keeps |
| 4 | `README.md` | Names the product ICU-Twin; the slides call the engine "CLIFATRON" | Pick one name per thing: ICU-Twin (the code), ICU Horizon (the board), and say so once |

Decide each row as a team: change now, change after judging, or leave.

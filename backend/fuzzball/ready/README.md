# Ready-to-run workflow files (final 25-patient cohort)

Rendered from the templates in `fuzzball/` by `scripts/make_ready.sh`. No `@TOKEN@` is left; the volume names are the real ones. Do not edit these by hand: change the template, then regenerate.

```
cd backend && scripts/make_ready.sh            # code = origin/main; or: scripts/make_ready.sh <40-hex commit>
```

| File | Start it as | When |
|---|---|---|
| `t7-code.fz` | `--name t7-code` | first, and after every code change |
| `t7-fit.fz` | `--name t7-fit` | fallback only: when job 4 has not produced a probe (one GPU) |
| `t7-ward.fz` | `--name t7-ward` | after the probe is staged; again when the ward changes |
| `t7-twin.fz` | `--name t7-twin` | the board, the dispatcher and Nemotron |
| `t7-forecast-unit.fz` | `--name t7-forecast-manual` | the first unit forecast, by hand, only while no dispatcher update runs |
| `t7-forecast-room12.fz` | example only | room updates are started by the dispatcher from the board |

Each: `fuzzball workflow validate fuzzball/ready/<file> && fuzzball workflow start fuzzball/ready/<file> --name <name>`.

**Which code `t7-code` publishes.** `CODE_REF` holds the commit and `CODE_SHA256` the sha256 of its GitHub tarball (`https://codeload.github.com/sajor2000/icustrainciq/tar.gz/<commit>`). These files were rendered for commit `617edc0b74d356de7f0cd32757692ffae28d4280` (origin/main on 2026-11-14, before the ICU-Twin sync was merged).

**That commit is older than these files.** The templates here carry the team's ICU-Twin changes (job 4's probe at `/store/train/probe-final.joblib`, generated names, the python CLI fetch, `protocol: http`), but `t7-code` would publish the commit's older `backend/`, and the dispatcher in `t7-twin` renders every forecast from the published `/store/code/fuzzball/t7-forecast.fz`. So, **before the first run on the cluster: merge the sync to `main`, run `scripts/make_ready.sh` again, commit `fuzzball/ready/`, and start that `t7-code.fz`.** The probe is no longer made by `t7-fit` on the usual path: job 4 (in vaishvikc/ICU-Twin) fits it, and `t7-fit` is the fallback (`docs/RUNBOOK.md`, section 4). `scripts/launch.sh` runs the whole chain.

`t7-smoke` is not here: it is no longer on the run path (see its header). Validation record: `docs/FUZZBALL_VALIDATION.md`.

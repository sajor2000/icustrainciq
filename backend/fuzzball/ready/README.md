# Ready-to-run workflow files (final 25-patient cohort)

Rendered from the templates in `fuzzball/` by `scripts/make_ready.sh`. No `@TOKEN@` is left; the volume names are the real ones. Do not edit these by hand: change the template, then regenerate.

```
cd backend && scripts/make_ready.sh            # code = origin/main; or: scripts/make_ready.sh <40-hex commit>
```

| File | Start it as | When |
|---|---|---|
| `t7-code.fz` | `--name t7-code` | first, and after every code change |
| `t7-fit.fz` | `--name t7-fit` | once per model (one GPU) |
| `t7-ward.fz` | `--name t7-ward` | after `t7-fit`; again when the ward changes |
| `t7-twin.fz` | `--name t7-twin` | the board, the dispatcher and Nemotron |
| `t7-twin-nochat.fz` | `--name t7-twin` | **instead of** `t7-twin.fz` when only one node (one GPU) is up: the board and the dispatcher, no Nemotron. Stop `t7-twin` first; never run both |
| `t7-forecast-unit.fz` | `--name t7-forecast-manual` | the first unit forecast, by hand, only while no dispatcher update runs |
| `t7-forecast-room12.fz` | example only | room updates are started by the dispatcher from the board |

Each: `fuzzball workflow validate fuzzball/ready/<file> && fuzzball workflow start fuzzball/ready/<file> --name <name>`.

**Which code `t7-code` publishes.** `CODE_REF` holds the commit and `CODE_SHA256` the sha256 of its GitHub tarball (`https://codeload.github.com/sajor2000/icustrainciq/tar.gz/<commit>`). These files were rendered for commit `6a46ea4f25fbe4903bbdd0804691da3154e78e1d` (origin/main on 2026-11-14; its `backend/` is identical to `134d642`).

**That commit is older than these files.** It does not contain `fuzzball/ready/`, and, more important, its `fuzzball/t7-forecast.fz` and `app/dispatcher.py` are the versions from before the storage change (they name the volumes `clif_work` and `tooling`, which do not exist). `t7-code` publishes the commit's `backend/`, and the dispatcher in `t7-twin` renders every forecast from the published `/store/code/fuzzball/t7-forecast.fz`. So, **before the first run on the cluster: merge this branch to `main`, run `scripts/make_ready.sh` again, commit `fuzzball/ready/`, and start that `t7-code.fz`.** With the files as they are here, `t7-code`, `t7-fit`, `t7-ward`, `t7-twin` and the hand-started unit forecast would work, but every update the dispatcher starts (07:00, the board's buttons) would stop at a missing volume.

`t7-smoke` is not here: it is no longer on the run path (see its header). Validation record: `docs/FUZZBALL_VALIDATION.md`.

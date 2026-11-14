# Fuzzball validation record

Date: 2026-11-14 (afternoon). Cluster context `hack` (cluster `fb-hack`, account `team7@fb-hack.local`, group `team7`). CLI `~/.local/bin/fuzzball`.

Only read-only calls were made: `fuzzball workflow validate`, `workflow list`, `workflow describe`, `workflow log`, `volume list`. **Nothing was started, stopped, created or deleted. No workflow in this repo has run on the cluster.** `validate` checks syntax, images and that the named volumes exist; it runs no script.

## Result per file

Files: `fuzzball/ready/` (rendered for the final cohort by `scripts/make_ready.sh`, code commit `6a46ea4f25fbe4903bbdd0804691da3154e78e1d`, tarball sha256 `cd609e4cb66b255d1c02cf1f41a1b0fc601c8d7fc94aaf9ffdce474a33682abb`).

| File | As it is | Scratch copy with `twin-store` replaced by the existing `hfcache` |
|---|---|---|
| `t7-code.fz` | fails: volume "twin-store" not found | validated |
| `t7-fit.fz` | fails: volume "twin-store" not found | validated |
| `t7-ward.fz` | fails: volume "twin-store" not found | validated |
| `t7-twin.fz` | fails: volume "twin-store" not found | validated |
| `t7-forecast-unit.fz` | fails: volume "twin-store" not found | validated |
| `t7-forecast-room12.fz` | fails: volume "twin-store" not found | validated |
| `t7-smoke.fz` (template, not in `ready/`) and `t7-fit.fz` for the open demo | not checked as is | validated |

The missing volume is the only error in every file. The scratch copies were made with `sed 's/name: twin-store /name: hfcache /'` outside the repo and are not kept.

## The one volume to create

Not run by this session; for the team to run once:

```
fuzzball volume create team7 twin-store --size 50GiB --description "Lookahead: code, packages, probes, stage ward, forecast files"
fuzzball volume list          # twin-store: PERSISTENT Yes, STATUS Enabled
fuzzball workflow validate fuzzball/ready/t7-code.fz
```

50 GiB is a starting value (code and packages: a few GiB; features of the training stays, the stage ward and the JSON files: a few GiB more). `fuzzball volume create --help` has a `--node` flag: "on a local provisioner this becomes the volume's holding node, and stages using the volume are placed there". Whether the `team7` provisioner is local is not known here. If it is, `twin-store` must be on a node that can also reach `mimic_clif` (every forecast job mounts both), so ask before choosing a node; without `--node` Fuzzball chooses.

## Storage map

`mimic_clif` belongs to training. Lookahead only reads it (Fuzzball 4.3 has no read-only mount, so this is a rule the scripts keep: a test checks that no script writes under `/data`). Everything Lookahead writes is on `twin-store`.

| Mount | Volume | Kind | Read | Written |
|---|---|---|---|---|
| `/data` | `mimic_clif` (exists, 186 GiB) | persistent | `dashboard_data/` (cohort: 19 CLIF tables, `dashboard_patients_unit25.parquet`, `name.parquet`), `model_output/final/` (the model), `tokenized_output/` (training tokens) | nothing. Never `clif/` or `dashboard_data/` |
| `/store` | `twin-store` (**to create**) | persistent | all of it | `code/`, `py/` (t7-code); `train/` (links to the training token files, winnowed stays, features, baseline scores), `probes/` (t7-fit); `stage/` (t7-fit, t7-ward, t7-forecast); `rooms.json`, `forecast.json` (t7-forecast); `capacity.json` (board); `runs.jsonl`, `rendered/` (dispatcher) |
| `/cache` | `hfcache` (exists) | persistent | `nemotron-3-nano-fp8/<revision>/` (t7-twin) | only if that folder is missing: the download, under `hf/` |
| `/work` | unnamed, 20 GB, in `t7-code` only | ephemeral (removed when the workflow ends) | the code tarball (ingress lands here) | tarball, unpacked copy, pip cache, temp files |
| `/tmp`, `/dev/shm` | container | ephemeral | | `HOME`, `TMPDIR`; the Fuzzball CLI of the dispatcher |

Which workflow mounts what: `t7-code`: `twin-store`, `work`. `t7-fit`, `t7-ward`, `t7-forecast`: `mimic_clif`, `twin-store`. `t7-twin`: `twin-store` (board, dispatcher), `hfcache` (Nemotron); it does not mount `mimic_clif`.

Files another process reads while they are replaced are swapped by rename: `/store/code` and `/store/py` (built as `.new`, renamed), `/store/stage/tokenized_output` and `stage_ward.csv` in t7-ward (built in `ward-new`), `rooms.json`, `forecast.json` and `capacity.json` (`.tmp`, then `os.replace`). `runs.jsonl` is appended one line at a time.

**Why one volume, and what it costs.** The earlier plan had three (`twin-store`, `clif_work`, `tooling`) so that the board's volume held nothing row-level. One volume is one thing to create and one place to look, and nothing in the Fuzzball 4.3 documentation or the files prevents it. The cost: `twin-store` now also holds `stage/` and `train/` (tokens, features and per-stay scores of real MIMIC-IV stays), and the board and dispatcher containers mount it. The board serves only `rooms.json`, `forecast.json`, `capacity.json` and the static page, and the links in `train/` point into `/data`, which those containers do not mount. Treat `twin-store` as restricted, like `mimic_clif`, and delete `stage/`, `train/`, `rooms.json` and `forecast.json` after judging.

## Where the trained model is

Read from `workflow describe` and `workflow log` of two finished workflows (paths and file names only):

- `job-3-ckpt-check ep2-20261114c` (8fe7026d-84a4-4d03-b391-e5892b7be622): the checkpoint `model_output/ep2-20261114c/checkpoint-2616` exists on the volume it mounts at `/data` (step 2616 of 4351; the training runs themselves are Canceled).
- `job-3-1-package ep2-20261114c` (1382fbd2-0b92-46ad-97c2-52441ac4b94c): job `package` wrote that checkpoint to **`model_output/final/`**: `config.json`, `generation_config.json`, `model.safetensors` (about 145 MB, 256 tensors), `vocab.yaml`, `MANIFEST.json`, and a folder `src/`. Job `loadtest` loaded it on the pytorch image and printed `LOADTEST OK`. `MANIFEST.json` was also sent to `fuzzball://group/package/final-ep2c-2616/`.

The workflows therefore read the model at `/data/model_output/final` and no copy step is needed (`t7-model.fz` was dropped). The Nemotron weights are on `hfcache` at `nemotron-3-nano-fp8/9bee19446c0dfd01f356e10979d225b2a6621944` (log of `t7-fb-nemotron-persistent`).

The cohort: the log of `t7-fc-dashboard-patients.fz` and of two one-core `fuzzball run` jobs show `dashboard_data/` with 21 files, `dashboard_patients_unit25.parquet` in it, and `name.parquet` written (3414 bytes, checksum compared in the job).

## Not verified until something runs

1. That the volume those training workflows call `data` is `mimic_clif`. `describe` does not print the volume's name; the folder names match what is on `mimic_clif`.
2. That `icutwin`'s extractor loads `model_output/final` with the packages in `requirements/t7-model.txt` (`AutoModelForCausalLM`, transformers 5.23.0). The load test used the image's own packages and the model's `src/`.
3. That `tokenized_output/` holds `tokens_train.parquet`, `tokens_tuning.parquet`, `tokens_held_out.parquet` and a `vocab.yaml` identical to the model's. `t7-fit` job `tokens` checks both and stops with a plain message if not.
4. The 19 table names in `dashboard_data/`: only the file count (21) and two file names are in the logs. `t7-ward` job `load` checks the tables, the 25 ids and the names file.
5. Time and memory of `t7-fit` (winnowing and extracting every training stay): the values in the file are starting values.
6. That vLLM serves the local Nemotron folder (`t7-twin` falls back to the Hugging Face name at the same revision if the folder has no `config.json`).
7. Everything in `FUZZBALL_TEST_PLAN.md` "Questions only the cluster can answer" (queueing beside Nemotron, the service endpoint, the CLI download in the dispatcher).
8. The code that `t7-code` publishes from the commit above predates the storage change: regenerate `fuzzball/ready/` after the merge (see `fuzzball/ready/README.md`).

# Fill-in list for the submission

Nothing below has been measured yet. Each slot is an empty tag in `one-sheet.html`
(`<span class="fill" data-fill="NAME" ...></span>`) or a `[FILL]` mark in `DEMO_SCRIPT.md`.
The sheet prints a blue "— on site" style placeholder while a slot is empty, so it is finished either way.

To fill a slot: type the value between the tags, then run

```bash
uv run --with playwright python docs/submission/make_shots.py export
```

Keep values short (about 14 characters fit in a slot on the sheet).

## One-sheet slots

| `data-fill` | What goes in | Who supplies it | Where it comes from |
|---|---|---|---|
| `model-size` | Patient model size, for example "35 M parameters" | Vaishvik | the size trained (`backend/icutwin/config/decoder.yaml` lists s 12.3 M, m 35 M, l 70 M) |
| `model-status` | One or two words: "trained", "training", "checkpoint ready" | Vaishvik / cluster owner | `fuzzball workflow list`; confirm the checkpoint loads |
| `train-scaling` | Training time on 1 GPU against 2, for example "9 h → 5 h" | Vaishvik | `t7-build` run times; only if both were run |
| `forecast-time` | Seconds from pressing "Update the unit" to the board redrawing | Fuzzball lane | rehearsal, `COMPUTE_PLAN.md` checklist step 5 |
| `chat-tokens-per-sec` | Nemotron 3 Nano tokens per second on one GB10 | Services lane | vLLM log during a chat question |
| `heldout-accuracy` | **Filled:** held-out AUROC 0.77–0.93 (see `docs/RESULTS.md`) | Vaishvik | done 2026-11-14 |
| `workflow-count` (has a value: 6) | Number of Fuzzball workflow files | Fuzzball lane | `ls backend/fuzzball/*.fz` |

## Counts printed on the sheet (recheck before printing)

| Count | Value on Nov 14 | Recheck with |
|---|---|---|
| Backend tests passing | 282 | `cd backend && uv run --extra dev --extra model pytest -q` |

## Statements to confirm on site

These came from the team on Nov 14 and were not checked from this repo:

- "On the cluster: 25 demo patients loaded, workflows validated." (cluster owner)
- "trained from scratch", "Both GPUs for training" (Vaishvik: confirm the training run finished on both GPUs)

## Demo script slots

Every `[FILL]` in `DEMO_SCRIPT.md`: who speaks, the live board URL, the forecast time, the training numbers, the held-out accuracy line, the model status.

## Not on the sheet on purpose

No accuracy, speed or scaling number appears anywhere until someone measures it. The screenshots show demo data (made-up patients and names), and the sheet says so.

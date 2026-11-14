# Lookahead JSON contract

What `app/aggregate.py` writes to `forecast.json` (unit scope) and `app/rooms.py` writes to `rooms.json` (one ward: the open demo by default, or a real MIMIC-IV ward with `--real-ward`, see "ward block"). The frontend and the services build to this. Flags: `docs/LIVE_DEMO.md` section 1.5. Decisions: `docs/DECISIONS.md` D8.

All times are ISO 8601 with a UTC offset (the default site zone is `America/Chicago`, so the offset in November is `-06:00`; the services pass `--tz` explicitly). All probabilities are for the same window, the next 24 h from the cut (morning cut 07:00). Five predictions: `icu_departure` (to a ward or step-down unit), `ventilator` (IMV), `vasopressor` (continuous infusion), `crrt`, `death`. Life support = IMV, vasopressor, CRRT.

## forecast.json

```json
{
  "made_at": "2026-11-14T11:30:00+00:00",
  "cut_time": "2026-11-14T07:00:00-06:00",
  "window": {"start": "2026-11-14T07:00:00-06:00", "end": "2026-11-15T07:00:00-06:00"},
  "scope": "unit",
  "unit_name": "Medical ICU",
  "ward": {"source": "open-demo", "label": "Open MIMIC-IV Demo"},
  "forecast_state": "ready",
  "on_now_source": "tokens",
  "demo_clock_hours": 0,
  "beds": 25,
  "range": "80% (p10-p90)",
  "resources": {
    "ventilator": {"team": "respiratory therapy", "available": true, "p10": 1, "p50": 2, "p90": 4, "expected": 2.1},
    "vasopressor": {}, "crrt": {}, "death": {}, "icu_departure": {}
  },
  "life_support": {
    "now_patients": 9,
    "now_by": {"imv": 5, "vasopressor": 6, "crrt": 1, "ecmo": null},
    "expected_new_patients": {"p10": 1, "p50": 2, "p90": 4, "expected": 2.3},
    "expected_by": {"imv": {"p10": 0, "p50": 1, "p90": 2, "expected": 1.0}, "vasopressor": {}, "crrt": {}}
  },
  "yardstick": {
    "kind": "capacity",
    "words": "TIGHT",
    "level": "amber",
    "capacity": {"life_support_patients": 11, "vents_free": 2, "vents_total": 7, "crrt_total": 2,
                 "set_at": "...", "set_by_role": "charge nurse", "load": {"p10": 10, "p50": 11, "p90": 13}},
    "typical": null
  },
  "machines": {
    "imv":  {"total": 7, "in_use": 5, "free": 2, "flag_at": 0.25, "flagged": 3, "short_by": 1, "words": "SHORT", "level": "red"},
    "crrt": {"total": 2, "in_use": 1, "free": 1, "flag_at": 0.25, "flagged": 1, "short_by": 0, "words": "AT LIMIT", "level": "amber"}
  },
  "check_first": [{"room": 7, "any_life_support": 0.62, "level": "high"}],
  "levels": {"medium": 0.2, "high": 0.4},
  "out_tag": 0.6
}
```

(Numbers are illustrative, not a result.)

- `ward`: where the data comes from, `{"source": "open-demo", "label": "Open MIMIC-IV Demo"}` (default) or `{"source": "mimic-iv", "label": "Real MIMIC-IV · local only"}` (a run with `--real-ward`). The same block is in `rooms.json`. A real ward never leaves the cluster volumes; stdout and logs hold counts only in both modes. See "ward block" below.
- `unit_name`: the unit's name for the page header (`--unit-name` on `aggregate.py`, `rooms.py --recount` and `scripts/run_cohort.py`; default "Medical ICU"; at most 60 characters).
- `forecast_state`: `"ready"` or `"pending-model"`, in both files. See "forecast_state" below. A key missing from an older file means `"ready"`.
- `cut_time` / `window`: the scheduled cut (`demo_clock_hours` 0) is the 07:00 nearest to the run in `--tz`. With a demo clock H the ward is replayed H hours after the morning cut, so `cut_time` is the last 07:00 at or before the run plus H hours (as the dispatcher counts `demo_clock_hours`) and `window` is the 24 h from it. An explicit `--cut-time` is taken as given (it must carry a UTC offset; a naive time is refused) and is not moved again by the demo clock.
- `resources.<name>`: `{team, available, p10, p50, p90, expected}`, exact Poisson-binomial over the unit's patients; a patient with that support running at the cut is not a new start (one that stopped before the cut is forecastable again). `p10/p50/p90` = the smallest count whose cumulative probability reaches 10 / 50 / 90%. `icu_departure` adds the ward and step-down probabilities (they exclude each other), clipped to 1; the other resources take the largest token probability. **`available: false` means the probe for that task was skipped in training (one class): `p10`, `p50`, `p90` and `expected` are then `null`, never 0** (a consumer must show "no data"). Stays already past the event do not make a resource unavailable. `life_support.expected_by.<support>` has the same shape for a skipped probe; the any-life-support figures treat a skipped support as 0, so they are a lower bound in that case.
- `life_support.now_patients`: patients with IMV, vasopressor or CRRT on at the cut (running at the cut: from the last record before it, see `docs/LIVE_DEMO.md` section 1.5; with `on_now_source` `tokens` CRRT uses a documented fallback, a CRRT row in the last 24 h, because the tokens have no stop signal; with `clif` see "on_now_source"). `now_by.ecmo` is always `null` = not available: no ECMO or mechanical circulatory support token reaches the model (`icutwin/config/tokens/` has none), so it is never invented.
- `expected_new_patients`: patients on none of the three at the cut who start at least one in the window. Per patient `any_life_support = 1 - prod(1 - p_k)` over IMV, vasopressor, CRRT not already on. `expected_by.<support>`: new starts of that one support.
- `yardstick`: load = `now_patients + expected_new_patients` (80% range in `load`). `kind: "capacity"` when a capacity file was given and readable (`life_support_patients` must be a JSON number from 0 to 50, not a bool or a string; anything else prints "capacity file unreadable" and the typical yardstick applies): ON TRACK (p90 <= capacity), TIGHT (p90 > capacity >= p50), SHORT (p50 > capacity); level ok / amber / red. Otherwise `kind: "typical"`: `typical.life_support_patients` = beds x the training share of stays on, or starting, life support in a 24 h window (`typical.load` as above); load p50 / typical <= 1.0 USUAL (ok), <= 1.3 BUSY (amber), above VERY BUSY (red). `yardstick` is `null` when there is no capacity and no training baseline.
- `machines`: ventilators (`imv`) and CRRT machines (`crrt`) against the unit's totals; see "capacity.json and /api/capacity" below. `null` when no total is set; a key missing from an older file means the same.
- `check_first`: up to 3 rooms whose new-start chance is High, largest first; stage ward only, `[]` otherwise (never stay ids). It ranks the same quantity `expected_new_patients` counts: a patient already on a support is 0 here and is not listed, even though that patient's room tile still shows `any_life_support` over the supports not on.
- `levels`, `out_tag`: the thresholds in use (a patient is `high` at `any_life_support >= 0.40`, `medium` at `>= 0.20`, else `low`; tagged "out" when `icu_departure >= 0.60`).
- `strain.per_task` / the typical baseline use the same definition as the forecast: a life support "running at the cut" is not a new start, one that stopped before the cut still is. A task with no data (`available: false`) is left out of the typical day.
- Also written for the current board and chat, to be dropped once they read the new keys: `method`, `model`, `horizon`, `default_horizon`, `horizons`, `per_day`, `already_started`, and `strain` (when a baseline exists).

## rooms.json

```json
{
  "made_at": "2026-11-14T11:30:00+00:00",
  "ward": {"source": "open-demo", "label": "Open MIMIC-IV Demo"},
  "forecast_state": "ready",
  "on_now_source": "tokens",
  "names": "fictional",    // only when at least one room has a name
  "dropped": 0,
  "rooms": [
    {
      "room": 7,
      "name": {"display": "Rivera, J.", "first": "Jo", "last": "Rivera", "fictional": true},  // only with --names
      "age": "67",          // "90+" for 90 and over; null if unknown (open demo CLIF)
      "sex": "F",           // "F" | "M" | null
      "updated_at": "2026-11-14T11:30:00+00:00",
      "cut_time": "2026-11-14T07:00:00-06:00",
      "window": {"start": "...", "end": "..."},
      "scope": "room",
      "on_now": {"imv": true, "vasopressor": false, "crrt": false, "ecmo": null},
      "p": {"imv": null, "vasopressor": 0.31, "crrt": 0.02, "icu_departure": 0.1, "death": 0.04},
      "skipped": {"imv": false, "vasopressor": false, "crrt": false, "icu_departure": false, "death": false},
      "on_life_support": false,
      "stopped_before_cut": {"imv": false, "vasopressor": true, "crrt": false},
      "any_life_support": 0.32,
      "level": "medium",
      "out": false,
      "past_12h": [{"h": 1, "text": "Norepinephrine infusion running"}]
    }
  ]
}
```

- `on_now.<support>` is true when that support is running at the cut. `on_life_support` is true when two or more are running (the board shows "On life support" with a dark-ink border instead of the level word); `level` is still computed. `stopped_before_cut.<support>` is true when it started before the cut but is not running at it (the room page's faint "V off" note).
- `dropped`: ward rooms with no entry (their record ends before a moved demo-clock cut); rooms for them are omitted. Computed as the ward's room numbers minus the rooms in the file: never negative.
- `p.<support>` is `null` where that support is running at the cut (not a new event) or its probe was skipped. `skipped.<name>` is `true` only for the second case: no score although the stay could have a new event (the probe was skipped in training, one class). A consumer shows "no data" for it, not 0 and not "on". `icu_departure` is the ward plus step-down probability, clipped to 1; the "out" tag reads that value. `any_life_support` is the new-start chance over the supports not already on, so a room with every support running reads 0.
- `past_12h`: at most 8 readable events from the 12 h before the cut, most recent first; `h` is hours before the cut, rounded up and at least 1 (an event 3601 s before the cut is in hour 2; 12 h exactly is hour 12; older events are not listed). Plain text mapped from the tokens (labs and vitals read "low", "normal" or "high" against the reference range, and the bin is left out when the token has no reference range); event kinds only, with no values, dates or ids.
- Room scope (`--room N`) replaces that room only, keeps every other room and the file's `made_at`; a room whose stay ended before a moved cut is removed. It edits an existing whole-ward file and refuses when there is none (run the whole ward first) or when the file's `ward` is not the ward of this run. A full run rewrites the file.
- Rooms hold room numbers only: no stay ids, patient ids or dates of the source data. A `name`, when present, is invented ("names" below).

### capacity.json and /api/capacity

`capacity.json` sits beside `forecast.json`. `POST /api/capacity` replaces it; `aggregate.py --capacity` reads it on the next run.

| Field | Meaning |
|---|---|
| `life_support_patients` | life-support patients tonight's staffing covers (the ON TRACK / TIGHT / SHORT yardstick). Optional |
| `vents_total` | ventilators on the unit. Optional |
| `crrt_total` | CRRT machines on the unit. Optional |
| `vents_free` | ventilators free, as entered (the older field). Optional; when it is given it wins over `vents_total` |
| `updated_at`, `set_at`, `set_by_role` | written by the server: the time (twice, the second for `aggregate.py`) and the role, never a name |

- **POST** body: `role` plus any of the four numbers, each a whole number 0 to 50 (a JSON integer, not a string). At least one of `life_support_patients`, `vents_total`, `crrt_total` must be there; otherwise 400 `{"ok": false, "reason": "enter whole numbers from 0 to 50"}`. A field left out is stored as `null` (the file is replaced, not merged). The answer is `{"ok": true, "capacity": {...}}` with the stored fields plus `vents_free` and `crrt_free` as GET gives them. A body with only `life_support_patients` and `vents_free` works as before.
- **GET** gives `{"life_support_patients", "vents_total", "vents_free", "crrt_total", "crrt_free", "updated_at", "set_by_role"}`; `null` = not set.
- **Free machines are never stored.** free = total − patients on that support at the cut (`life_support.now_by.imv` / `.crrt` of the current `forecast.json`), never below 0, worked out on every read; so it follows a new forecast. `vents_free` is the entered number when one was entered. With a total but no forecast file yet, free is `null`.
- An older file (`life_support_patients`, `vents_free` only) still loads: the totals read as `null`. A file that is not JSON reads as not set.
- **`machines` in `forecast.json`**, per `imv` and `crrt` (`null` for a machine with no total; for `imv` an entered `vents_free` alone is enough, `total` is then `null`): `total`, `in_use` (on at the cut), `free`, `flag_at` (0.25, the page's default line), `flagged` = rooms not on that support whose chance of starting it is `flag_at` or more, `short_by` = max(0, flagged − free), and the word, the same rule as the page's cards: **SHORT** (red) when flagged > free; **AT LIMIT** (amber) when flagged = free and at least one bed is flagged; otherwise **ON TRACK** (ok). With no forecast for that support (`pending-model`, or its probe was skipped) `flagged`, `short_by`, `words` and `level` are `null`; `total`, `in_use` and `free` stay real. The page may still apply its own line (the Thresholds button); the block is the answer at the default line, for the chat and for a page with no stored line.
- `yardstick.capacity` (only with a staffing number) also carries `vents_total`, `crrt_total` and the derived `vents_free`.
- The chat's `get_capacity` tool returns the GET fields plus `machines`.

### forecast_state

`"ready"`: the model and the probes scored the ward. `"pending-model"`: there are no model weights or probes yet (`scripts/run_cohort.py` without `--model` / `--probes`, or with folders that lack weights or a probe manifest). The files are still valid and the Now side is real:

| Field | `pending-model` |
|---|---|
| `rooms[].on_now`, `on_life_support`, `stopped_before_cut`, `age`, `sex`, `past_12h` | real, as in `ready` |
| `rooms[].p.<name>` | `null` for all five |
| `rooms[].skipped.<name>` | `true` where the support is not running at the cut (and for `icu_departure`, `death`): "no data", as for a skipped probe |
| `rooms[].any_life_support`, `rooms[].level` | `null` (not 0, not "low") |
| `rooms[].out` | `false` |
| `life_support.now_patients`, `now_by` | real |
| `resources.<name>`, `life_support.expected_new_patients`, `life_support.expected_by.<support>` | `{"available": false, "p10": null, "p50": null, "p90": null, "expected": null}` (`resources` keeps `team`) |
| `yardstick` | `null` |
| `machines` | `total`, `in_use`, `free` real; `flagged`, `short_by`, `words`, `level` `null` |
| `check_first` | `[]` |
| `model` | `"pending"` |

A consumer shows "pending run" or "no forecast yet" for the Next 24 h side and the real counts for Now. `board.py` sends both files whole, so the key reaches the page unchanged. A room-scope run (`rooms.py --room`) refuses a `pending-model` file: run the whole ward first.

### Shared demo day

MIMIC-IV shifts every patient's dates by a different amount (years 2100 and later), so the stays of a ward never overlap in calendar time. The board shows them as one unit on one day. The rule:

- **Each stay keeps its own clock.** Its cut is its first ICU arrival + 24 h (`--cut-after-arrival-hours`, D3) + the demo clock, in its own dates (`icutwin-winnow`, `clif_now.stay_cuts`). Everything "at the cut" (on now, last 12 h, the tokens the model reads, the 24 h outcome window) is measured from that cut. Raw timestamps of two stays are never compared.
- **The files carry one shared cut.** `cut_time` is the same in `forecast.json` and in every room: the scheduled 07:00 in the ward time zone plus the demo clock (`scripts/run_cohort.py`: the last 07:00 at or before the run). A stay's display offset is that shared cut minus its own cut. The only times of a stay that reach the files are already relative: `past_12h[].h` is hours before the cut. `made_at` and `updated_at` are the run's wall clock. So no date of the source data is in either file, and `scripts/run_cohort.py` refuses to write a file whose strings hold a year of 2100 or later, or a stay id.
- **The demo clock moves every stay by the same hours**, each on its own clock. A stay whose ICU stay ended before the new cut has no room entry and counts in `dropped`. `scripts/run_cohort.py` also checks presence against `clif_adt` (the cut lies inside an ICU stay) and `discharge_dttm` (still in hospital): a patient who left the ICU or died before the cut is dropped, never shown as present.
- **Age** is `age_at_admission` from the stay's own CLIF row: the age at that admission, never worked out against today's date. 90 and over shows as "90+".
- **Checks**, per stay, printed as counts (`checks` in the script's last line): no past token at or after the cut (`future_tokens` 0), the past is in time order (`unordered` 0), the tokenizer's cut equals the CLIF cut (`cut_clock_differs`; it can be 1 h off only when a daylight-saving change falls inside the first day), rooms present, rooms ended before the cut. A non-zero `future_tokens` or `unordered` stops the run.

`forecast.json` also records `cut_after_arrival_hours` (24 unless set) when `scripts/run_cohort.py` wrote it.

### names

A room may carry `"name": {"display", "first", "last", "fictional": true}` and the file then has `"names": "fictional"`. **The names are invented for the demo.** MIMIC-IV has no names. They come from a names file made for one ward (`--names <file>`: `hospitalization_id`, `first_name`, `last_name`, `display_name`, `name_source` = `"fictional"`) or from the seeded generator (`--names fake`, `app/fake_names.py`, keyed by room number). Without `--names` there is no `name` key and the page shows the room number, sex and age only.

- A stay with no row in the names file has no `name`. The run prints how many rooms were named and how many were not, never which.
- Each string is at most 40 characters: letters, spaces and `. , ' -`. A file with any other string, or with a `name_source` other than `"fictional"`, stops the run (the message has counts only).
- A names file holds real stay ids, so it stays beside the ward's data (git-ignored folder or a team volume). It is never committed.
- Names are never written to stdout, to `runs.jsonl` or to any log. The chat may say "Room 12 (Rivera, J.)"; its log keeps the role and tool names only.
- A real deployment would take names from the hospital's ADT feed, with the hospital's access rules. Nothing here is built for real names.

### on_now_source

`"on_now_source"` (in `forecast.json` and `rooms.json`) says where "on now" comes from: `"tokens"` (default: the winnower's `LABEL//imv_at_cut`, `pressor_at_cut`, `crrt_at_cut` flags) or `"clif"` (`--clif-now <CLIF folder>` on `rooms.py` and `aggregate.py`, `app/clif_now.py`). With `"clif"`, raw CLIF decides what runs at each stay's cut (first ICU arrival + 24 h + the demo clock, in the data's timeline): IMV = the last non-null `device_category` within 24 h is IMV (no device row: the token flag is kept); vasopressor = per pressor the last `medication_admin_continuous` row within 24 h is start / dose_change / going with dose > 0 (null dose carries the last non-null since the last stop; `stop` ends it); CRRT = a `crrt_therapy` row within 6 h with `blood_flow_rate` > 0 (or no rate but a mode). That replaces the token flags for the room `on_now` tags and `stopped_before_cut`, `life_support.now_patients` / `now_by`, and the supports excluded from `any_life_support` and from the new-start counts. A key missing from an older file means `"tokens"`. A room-scope run refuses a `rooms.json` made with the other source. The `--real-ward` guard applies to the CLIF folder's stays too.

### ward block (decided by J.C., 2026-11-14)

Real MIMIC-IV per-patient room views are approved, with all patient data kept local (cluster volumes only; never git, screenshots, logs beyond counts, or public hosting). It is an explicit mode:

- Default: `rooms.py` and `aggregate.py --stage-csv` work on the open demo ward and write `"ward": {"source": "open-demo", "label": "Open MIMIC-IV Demo"}`. If any stay id in the room map is not in the git-tracked `clif_demo/clif_hospitalization.parquet`, they refuse (the message gives counts, never ids).
- `--real-ward` (on `rooms.py` and on `aggregate.py`) allows a non-demo ward and writes `"ward": {"source": "mimic-iv", "label": "Real MIMIC-IV · local only"}` in `rooms.json` and `forecast.json`. `rooms.py --demographics` may then point at the real CLIF folder. The page should show the label wherever the ward is shown.
- stdout and logs hold counts only in both modes; rooms still carry room numbers only.

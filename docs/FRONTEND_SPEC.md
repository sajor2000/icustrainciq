# Frontend spec: the ICU command-center board

The frontend is the ICU team's board for 07:00 morning rounds. The backend (forecaster, workflows, dispatcher) lives in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin); this repo holds the frontend design, the mockup, and the contract it must meet. Journeys: [`USER_JOURNEY.md`](USER_JOURNEY.md). Decisions: [`DECISIONS.md`](DECISIONS.md). Visual system: [`../DESIGN.md`](../DESIGN.md).

## How it runs

- Static HTML, CSS and vanilla JavaScript; no build step, no Node in the image, works offline.
- Served by the stdlib Python server `app/board.py` in the backend repo, as the `board` service in `fuzzball/t7-twin.fz` (port 8080, team-scoped HTTPS endpoint) on the team's two NVIDIA GB10 nodes.
- The finished frontend replaces the page template in `app/board.py` (or is served as a static file by it). Keep the API below unchanged.

## Data the board reads

| Source | What | Who writes it |
|---|---|---|
| `GET /api/forecast` | `forecast.json` (counts only); example: [`../examples/forecast.json`](../examples/forecast.json) | `app/aggregate.py` after each `t7-forecast` run |
| `GET /api/runs` (via the board) | dispatcher status: next scheduled run, recent runs (time, role, workflow id) | `app/dispatcher.py` |
| `GET /api/rooms`: `rooms.json` (to build; contract in `FRONTEND_PLAN.md`) | stage-ward rooms only: risk per horizon per event, a sample of futures as event lists, preceding-event counts, last 12 h of events | lane 3, open MIMIC-IV Demo patients only (D6) |

`forecast.json` keys: `made_at`, `beds`, `range` ("80% (p10-p90)"), `default_horizon` ("24h"), `horizon` (label), `model`, `shards`, `resources` (default horizon), `horizons` (`24h`, `48h`, `72h`, `stay`, each with `label` and `resources`), `per_day` (`Day 1` to `Day 3`), `already_started` (`vasopressor`, `ventilator` counts). Each resource: `team`, `p10`, `p50`, `p90`, `expected`. Resource names: `vasopressor`, `ventilator`, `nippv`, `high_flow_nc`, `icu_admission`, `death`, `icu_departure`, `icu_beds_net`.

## Actions the board sends

| Action | Request | Response |
|---|---|---|
| Ask the chat | `POST /api/ask {"question": "...", "role": "ICU nurse", "room": 7}` (`room` optional, stage ward only) | `{"answer": "..."}` (Nemotron 3 Nano, counts and stage-ward room only) |
| Rerun the forecast (button) | `POST /api/rerun {"role": "ICU nurse"}` | `{"started": true, "name": "t7-forecast-1114-1302", "workflow": "..."}` or `{"started": false, "reason": "..."}` |
| Rerun from the chat | a question matching "rerun / run / start / refresh / update ... forecast" | same as above, as an answer sentence |

Roles accepted: `ICU nurse`, `ICU physician`, `pharmacy`, `respiratory therapy`, `bed manager`. The board never sends or stores names.

## Screens and what each must do

1. **Top strip**: unit name, "For 07:00 morning rounds · patients in the ICU at least 24 h", when it ran; horizon tabs (Next 24 h default, Day 2, Day 3, Rest of stay); Day/Night board switch; role picker and **Rerun forecast** with the last-run line.
2. **Room board**: 25 room magnets, number large, highest-risk event and percent, shaded by risk; VENT/PRESS tags for already on a ventilator or vasopressor. Click opens the room drawer.
3. **Margin (unit strain)**: rows by team with median, 80% range bar, red capacity line and status word where a capacity exists (ON TRACK / TIGHT / SHORT, always as a word).
4. **Room drawer** (stage ward only): risks per horizon, the 100-futures chart for a chosen event, "what most often came before it, in those futures", what the model read in the last 12 h, and the "evidence, not a cause; not a treatment recommendation" note.
5. **Shift brief**: AI-drafted from the counts, labelled.
6. **Ask the board**: chat for unit and room questions and for "rerun the forecast".
7. **Run strip**: model, workflows, GPU timings or "pending run".

## States the frontend must handle

| State | Show |
|---|---|
| No forecast yet | "No forecast yet: the 06:30 run has not finished" and the rerun control |
| Forecast older than 24 h | the age, struck through numbers, and a rerun prompt |
| Run in progress | "Running t7-forecast-... for ICU nurse" and keep the last forecast visible |
| Rerun refused | the dispatcher's reason, verbatim |
| Nemotron not up | "Nemotron is not answering yet"; the rest of the board works |
| Horizon missing from the file | hide that tab |
| Room with an event already started | "on now" instead of a percent |

## Rules

- **Counts only for real MIMIC-IV.** Room-level views and room chat only for the stage ward (open MIMIC-IV Demo patients, excluded from training). Never log questions.
- **Every number has its range.** Never a bare median.
- **Status never by colour alone**; tile text at 4.5:1 or better in day and night.
- **Honest labels**: SYNTHETIC on demo data, "(mock)" on drafted text, "pending run" where no run has produced a number, "not forecast" for arrivals.
- **Decision support, never a treatment recommendation.**
- **Design**: follow [`../DESIGN.md`](../DESIGN.md) (the unit whiteboard world: enamel board, marker-navy ink, magnet blue, system UI stack with tabular numerals). Use the Impeccable skill (`/impeccable`) for any UI work; the mockup's direction contract is in `.impeccable/surfaces/`.

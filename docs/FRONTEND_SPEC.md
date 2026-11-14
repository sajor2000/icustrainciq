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
| `GET /api/rooms`: `rooms.json` (to build; contract in `FRONTEND_PLAN.md`) | stage-ward rooms only: the six probabilities for the next 24 h, events already on, last 12 h of events | lane 3, open MIMIC-IV Demo patients only (D6) |

`forecast.json` keys: `made_at`, `beds`, `range` ("80% (p10-p90)"), `method` (probe scoring, one forward pass per patient), `default_horizon` ("24h"), `horizon` ("Next 24 h (to 07:00 tomorrow)"), `model`, `resources`, `horizons` (only `24h`), `per_day` (empty), `already_started` (counts of patients already on a task before the cut), `other_tasks` (the rest of Vaishvik's probe heads: ICU transfer-in, potassium high and low, anemia, sodium low and high, tachycardia, hypertension; same shape as `resources`, team `research`; the board does not show them). Each resource: `team`, `p10`, `p50`, `p90`, `expected`. The six resources (`docs/DECISIONS.md` D8): `ventilator` (respiratory therapy), `vasopressor` (pharmacy), `crrt`, `hypotension`, `death` (ICU team), `icu_departure` (bed manager). There is one horizon: the next 24 h, 07:00 to 07:00.

## Actions the board sends

| Action | Request | Response |
|---|---|---|
| Ask the chat | `POST /api/ask {"question": "...", "role": "ICU nurse", "room": 7}` (`room` optional, stage ward only) | `{"answer": "..."}` (Nemotron 3 Nano, counts and stage-ward room only) |
| Rerun the forecast (button) | `POST /api/rerun {"role": "ICU nurse"}` | `{"started": true, "name": "t7-forecast-1114-1302", "workflow": "..."}` or `{"started": false, "reason": "..."}` |
| Rerun from the chat | a question matching "rerun / run / start / refresh / update ... forecast" | same as above, as an answer sentence |

Roles accepted: `ICU nurse`, `ICU physician`, `pharmacy`, `respiratory therapy`, `bed manager`. The board never sends or stores names.

## Screens and what each must do

1. **Top strip**: unit name, "For 07:00 morning rounds · next 24 h, 07:00 to 07:00 · patients in the ICU at least 24 h" (one horizon, no tabs); Day/Night board switch; role picker ("I am") and **Rerun forecast**; the run line (when it ran, or "Running ..." while a run is in progress).
2. **Shift brief** (top of the right column; first on a phone): at most three lines, labelled (mock) until Nemotron drafts it. A shared caption says "Median (80% range)". Line 1 is the verdict: every SHORT or TIGHT row ("Ventilators TIGHT 3 (1–5); 3 free"), or "Nothing short where a capacity is set". Line 2: the two busiest rows without a capacity ("Departures 7 (5–10); hypotension 5 (3–7)"). Line 3: "Review rooms 20, 12, 7", each number a link that opens the room. Short labels; no percentages that the magnets already show; full detail stays in the rows and the drawer.
3. **Room board**: 25 room magnets, number large, the room's highest risk (task name and percent; leaving the ICU is not counted as a risk), shaded by that risk; VENT / PRESS / CRRT tags for tasks already on before 07:00. Click opens the room drawer.
4. **Unit rows**: one row per D8 task: name and team (or "your row"), median as the big number, 80% range bar with the range in words, an ink line at the free count, and the status word (ON TRACK / TIGHT / SHORT) where a capacity is set, "no capacity set" where none is. Order and folding follow the role (see Cognitive load).
5. **Room drawer** (stage ward only), opens under the unit rows so the verdict stays in view: the room's live tasks as bars sorted by risk, with percent; "On now, not forecast as new" tags for tasks already started; one line on how far to trust them (held-out calibration and AUROC, "pending run" until a run supplies them); what the model read in the last 12 h, five items and "Show more"; the "model evidence, not a cause; not a treatment recommendation" note.
6. **Ask the board**: suggested-question chips (at most three by role, plus "Rerun the forecast"; with a room open, the first chip is "Room N: what is most likely in the next 24 h?"), then the answers, then a text box ("Or type a question"). The chat starts empty: no seeded exchange.
7. **How this forecast was made** (foot of the page): one plain-language line (when and where it ran, that patient records stay in the hospital), then a folded "All 14 forecasts, and what each one means" table: the six board tasks (for staffing) and the eight `other_tasks` (research only, never staffing rows), each with its definition, median and 80% range, and who uses it; then the model, method, held-out accuracy and run time, each "pending run" until a run supplies it.

## Cognitive load

The board is read at 07:00 by a tired team standing at a workstation or a projector, often mid-conversation. Every screen decision below lowers what they must hold in their heads. Target: the shift question ("what will we be short of tonight, and how sure are we?") is answered within 10 seconds, without scrolling on a 1440 px screen. On a phone the order is brief, unit rows (your row first), room drawer, room board, chat, so no one scrolls past 25 rooms to reach their row.

| What we surface | Rule | Why it lowers load |
|---|---|---|
| The verdict first | The shift brief's first line names every SHORT or TIGHT row, or says nothing is short. It sits at the top of the right column and is the first block on a phone. | The answer comes before the evidence; no one scans eight rows to find one word. |
| Exceptions only | Unit rows sort SHORT, then TIGHT, then the rest. Rows that are ON TRACK or have no capacity fold under "N more rows · 1 on track, 3 capacity not assessed". | Attention goes to the rows that need a decision. |
| Each role sees its own row first | The role picker ("I am") puts that team's rows on top, marked "your row" (pharmacy: vasopressor starts; respiratory therapy: ventilator starts; bed manager: leaving the ICU; ICU physician: CRRT, hypotension, deaths). The charge nurse (ICU nurse) sees all six rows open. | Each team reads one row, not the whole unit. The role also picks the chat chips. |
| One number per row | The big number is the median; the 80% range is a bar and "range a to b" in small text; the status is a word. No probability tables by default. | One glance per row; uncertainty is shown, not computed. |
| Top three rooms | The three highest-risk rooms lead the board as magnets; "Review rooms 20, 12, 7" in the brief links to their drawers; the full board is under "Show all 25 rooms". | No scanning 25 magnets to find where to start rounds. |
| The room drawer | Live tasks as bars sorted by risk; tasks already on as tags, not percentages; one trust line in words; last 12 h capped at five events with "Show more". It opens under the unit rows; focus moves to its heading and returns to the room's magnet on close (Escape closes it). | The attending sees this room's top risk first and still sees the unit verdict. |
| Suggested questions | At most three chips by role plus "Rerun the forecast" (44 px targets); a room chip when a room is open; the chat starts empty and clears when the role or the room changes. | Tapping beats composing a question at rounds; an empty chat never looks like an answer. |
| Shift brief | Three lines at most; never repeats a full row. | It is something to read aloud at rounds, not a report. |
| One horizon | Next 24 h, 07:00 to 07:00. No tabs, no time slider. | Nothing to choose before reading. |
| Everything else folded | The other eight forecasts and the model details sit in one closed section at the foot ("All 14 forecasts"), in plain words, never in the staffing rows. | Judges and the curious can see everything the model makes; the 07:00 reader never has to. |
| Consistent colour | Blue means risk (magnet shading, range bars). Red means SHORT only, amber TIGHT only, green ON TRACK only, always with the word. The capacity line and the SYNTHETIC badge are ink. | A colour never needs decoding twice. |
| Day and night boards | Same layout and words; the user picks the board, not the OS. | Nothing moves when the lights go down. |

## States the frontend must handle

| State | Show |
|---|---|
| No forecast yet | "No forecast yet: the 06:30 run has not finished" and the rerun control |
| Forecast older than 24 h | the age, struck through numbers, and a rerun prompt |
| Run in progress | "Running t7-forecast-... for ICU nurse" and keep the last forecast visible |
| Rerun refused | the dispatcher's reason, verbatim |
| Nemotron not up | "Nemotron is not answering yet"; the rest of the board works |
| A task missing from the file | hide that row; say "not in this run" |
| Room with an event already started | "on now" instead of a percent |

## Rules

- **Counts only for real MIMIC-IV.** Room-level views and room chat only for the stage ward (open MIMIC-IV Demo patients, excluded from training). Never log questions.
- **Every number has its range.** Never a bare median.
- **Status never by colour alone**; tile text at 4.5:1 or better in day and night. Red is reserved for SHORT.
- **Honest labels**: SYNTHETIC on demo data, "(mock)" on drafted text, "pending run" where no run has produced a number, "not forecast" for arrivals.
- **Decision support, never a treatment recommendation.**
- **Design**: follow [`../DESIGN.md`](../DESIGN.md) (the unit whiteboard world: enamel board, marker-navy ink, magnet blue, system UI stack with tabular numerals). Use the Impeccable skill (`/impeccable`) for any UI work; the mockup's direction contract is in `.impeccable/surfaces/`.

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
| `GET /api/rooms`: `rooms.json` (to build; contract in `FRONTEND_PLAN.md`) | stage-ward rooms only: the five predictions for the next 24 h, events already on, last 12 h of events | lane 3, open MIMIC-IV Demo patients only (D6) |

`forecast.json` keys: `made_at`, `beds`, `range` ("80% (p10-p90)"), `method` (probe scoring, one forward pass per patient), `default_horizon` ("24h"), `horizon` ("Next 24 h (to 07:00 tomorrow)"), `model`, `resources`, `horizons` (only `24h`), `per_day` (empty), `already_started` (counts of patients already on a task before the cut). The board reads only the five predictions in `resources` (D8); any other key is ignored. Each resource: `team`, `p10`, `p50`, `p90`, `expected`. The five resources (`docs/DECISIONS.md` D8), all for the next 24 h (07:00 to 07:00): `icu_departure` (ICU discharge; bed manager; ward or step-down), `ventilator` (IMV; respiratory therapy), `vasopressor` (pharmacy), `crrt` (ICU team), `death` (ICU team). There is one horizon: the next 24 h, 07:00 to 07:00.

## Actions the board sends

| Action | Request | Response |
|---|---|---|
| Ask the chat | `POST /api/ask {"question": "...", "role": "ICU nurse", "room": 7}` (`room` optional, stage ward only) | `{"answer": "..."}` (Nemotron 3 Nano, counts and stage-ward room only) |
| Rerun the forecast (button) | `POST /api/rerun {"role": "ICU nurse"}` | `{"started": true, "name": "t7-forecast-1114-1302", "workflow": "..."}` or `{"started": false, "reason": "..."}` |
| Rerun from the chat | a question matching "rerun / run / start / refresh / update ... forecast" | same as above, as an answer sentence |

Roles accepted: `ICU nurse`, `ICU physician`, `pharmacy`, `respiratory therapy`, `bed manager`. The board never sends or stores names.

## Screens and what each must do

1. **Top strip**: unit name, "For 07:00 morning rounds · next 24 h, 07:00 to 07:00 · patients in the ICU at least 24 h" (one horizon, no tabs); Day/Night board switch; role picker ("I am") and **Rerun forecast**; the run line (when it ran, or "Running ..." while a run is in progress).
2. **Shift brief** (top of the right column; first on a phone): at most three lines, labelled (mock) until Nemotron drafts it. A shared caption says "Median (80% range)". Line 1 is the verdict: every SHORT or TIGHT row ("Ventilators TIGHT 3 (1–5); 3 free"), or "Nothing short where a capacity is set". Line 2: the two busiest rows without a capacity ("Discharges 7 (5–10); vasopressors 2 (0–3)"). Line 3: "Review rooms 20, 12, 7", each number a link that opens the room. Short labels; no percentages that the magnets already show; full detail stays in the rows and the room page.
3. **Unit strain** (top of the right column; first on a phone): a four-bar signal glyph with the band word, then the busy-day ratio, new events forecast for the next 24 h across the five predictions divided by this ICU's typical day (from training data; synthetic or "pending run" until a run supplies it), e.g. "1.3× a typical day", with its 80% range, a band word (QUIET / USUAL / BUSY / VERY BUSY), a scale with the typical day marked, and one line naming the tasks above their usual. It measures the unit against its own norm, as ICU strain studies do (Wilcox 2020, PMID 32141924; indicators reviewed in Rewa 2018, PMID 29587816); it is a forecast summary, not a validated outcome score.
4. **Room board** (left two-thirds; all 25 rooms on one screen): each tile shows only the room number, its **predicted acuity** (Low / Medium / High) and on-now tags (V, P, C). Acuity is coded three ways that agree: a signal-strength glyph (1, 2 or 3 rising bars), the tile shade (white, light blue, full blue) and the word. Rule: the room's highest chance of a new IMV, vasopressor or CRRT start, or death, in the next 24 h (High 4 in 10 or more, Medium 2 in 10 or more). Forecast only: support already running is shown by the tags, never folded into the level. Redundant shape-and-count coding follows the Visual Patient human-factors studies (Tscholl 2020, PMID 32283625; Bergauer 2023, PMID 37041316: better information transfer, lower workload, readable at a distance). A tile opens the room page.
5. **Unit rows**: one row per D8 task: name and team (or "your row"), median as the big number, 80% range bar with the range in words, an ink line at the free count, and the status word (ON TRACK / TIGHT / SHORT) where a capacity is set, "no capacity set" where none is. Order and folding follow the role (see Cognitive load).
6. **Room page** (`#room=N`, stage ward only; the browser's back button returns to the board): "← All 25 rooms" and previous / next room for walking rounds; one line of unit context (strain and the brief's verdict); the room number with its acuity glyph; each event as a level word (LOW / MEDIUM / HIGH), a 10-dot icon array and a natural frequency ("about 4 in 10 patients like this"), never a bare percentage (icon arrays and absolute frequencies improve understanding: Zipkin 2014, PMID 25133362; chart choice shifts clinicians' risk judgement: Alptekin 2025, PMID 39579585); "On now, not forecast as new" tags; the trust line ("pending run" until held-out checks exist); what the model read in the last 12 h (five, then "Show more"); "Ask about this room"; the evidence-not-cause note. Focus moves to the room heading on open and back to the room's tile on return.
6a. **Ask the board** (floating widget, closed by default): a launcher button at the bottom right opens a panel with suggested-question chips (at most three by role, plus "Rerun the forecast"; on a room page the first chip is "Room N: what is most likely in the next 24 h?"), the answers, and a text box. Close and Escape close it and return focus to the launcher; the chat clears when the role or the room changes. It never opens by itself and never flashes.
7. **How this forecast was made** (foot of the page): one plain-language line (when and where it ran, that patient records stay in the hospital), then a folded "The five forecasts, and what each one means" table (definition, median and 80% range, who uses it), then the model, method, held-out accuracy and run time, each "pending run" until a run supplies it.

## Cognitive load

The board is read at 07:00 by a tired team standing at a workstation or a projector, often mid-conversation. Every screen decision below lowers what they must hold in their heads. Target (one screen, Few's rule for dashboards): the shift question ("what will we be short of tonight, and how sure are we?") is answered within 10 seconds, without scrolling on a 1440 px screen. On a phone the order is brief, unit rows (your row first), room room page, room board, chat, so no one scrolls past 25 rooms to reach their row.

| What we surface | Rule | Why it lowers load |
|---|---|---|
| The verdict first | The shift brief's first line names every SHORT or TIGHT row, or says nothing is short. It sits at the top of the right column and is the first block on a phone. | The answer comes before the evidence; no one scans eight rows to find one word. |
| Exceptions only | Unit rows sort SHORT, then TIGHT, then the rest. Rows that are ON TRACK or have no capacity fold under "N more rows · 1 on track, 3 capacity not assessed". | Attention goes to the rows that need a decision. |
| Each role sees its own row first | The role picker ("I am") puts that team's rows on top, marked "your row" (pharmacy: vasopressor starts; respiratory therapy: ventilator starts; bed manager: leaving the ICU; ICU physician: CRRT, deaths). The charge nurse (ICU nurse) sees only the rows with a verdict (TIGHT or SHORT); the rest fold. | Each team reads one row, not the whole unit. The role also picks the chat chips. |
| One number per row | The big number is the median; the 80% range is a bar and "range a to b" in small text; the status is a word. No probability tables by default. | One glance per row; uncertainty is shown, not computed. |
| All beds, exceptions marked | All 25 rooms on one screen; each tile's three highest risks as bars; only the three watch-first rooms tinted and numbered; "Watch first" and the brief link to them. | The whole unit at a glance, with the eye drawn only to the exceptions (colour for the exception, length for the size). |
| The room page | Its own page per room (back button works, previous and next room for rounds); live tasks as large bars sorted by risk; tasks already on as tags; one trust line; last 12 h capped at five with "Show more"; a line of unit context on top. | The attending reads one room without losing the unit; nothing about other rooms competes on the page. |
| Strain first | One number for the unit (× a typical day) with its range, band word and the tasks driving it, at the top of the right column. | Answers "how busy are we" before anyone reads a row. |
| Chat out of the way | A closed floating widget; opens on demand, never on its own; clears on room or role change. | The board stays a board; questions are one tap away. |
| Suggested questions | At most three chips by role plus "Rerun the forecast" (44 px targets); a room chip when a room is open; the chat starts empty and clears when the role or the room changes. | Tapping beats composing a question at rounds; an empty chat never looks like an answer. |
| Shift brief | Three lines at most; never repeats a full row. | It is something to read aloud at rounds, not a report. |
| One horizon | Next 24 h, 07:00 to 07:00. No tabs, no time slider. | Nothing to choose before reading. |
| Model details folded | The five forecasts with their definitions and the model details sit in one closed section at the foot, in plain words. | Judges and the curious can see how it works; the 07:00 reader never has to. |
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

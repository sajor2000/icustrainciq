# Frontend spec: ICU Horizon, the ICU board

> **What the page draws (D25, 2026-11-15).** The board page is the team's final board design (ICU-Twin `55df710`), with bug fixes and the refinements the team approved on 2026-11-15 (each one, with before and after pictures and how to undo it, in [`UI_REVIEW.md`](UI_REVIEW.md)). It has **no bed status**: no Worsening / Watch / Still on support / Leaving, no status colour on a tile, no "Worry first" rail, no Staffing card, no 1:1 tag and no role picker. What it draws:
>
> - **Bed tile:** a person icon, the bed number, the generated (fictional) name with sex and age, the life support running at 07:00, and under NEXT 24 H each event at or above its threshold in Settings, in a circle with its chance (a new ventilator, vasopressor or CRRT, discharge). When a new life support is at its threshold the person icon turns red and pulses; discharge alone does not. Death is never shown on a tile. A "See first" row above the grid names the three highest-risk beds. In Now a bed on two or more supports is marked Critical.
> - **Settings panel** (the gear): light or dark board, "Flag beds at 40% · 20% · 10%" (default 20%) with a visible "Reset to standard" and a threshold per event (kept on the device). The standard lines are 20% watch, 40% worsening, 60% leaving (D26, applied: PR #24 merged), and Capacity (ventilators and CRRT machines on the unit, and optionally the life-support patients tonight's staffing covers).
> - **Bed pop-up** (`#room=N`): the five predictions, the last 12 hours of vital signs (`vitals_12h`, hourly medians) and the last events the model read; "Update this bed" and "Ask about this forecast".
> - **Unit strain:** a line with what is short, "Deaths expected" as one unit count, the three highest-risk beds (they pulse; death never ranks a bed) and "N on life support now · +N new expected in 24 h"; then one event card each for Deaths, Ventilator, Vasopressor, CRRT and Leave the ICU: on now, free machines, "Predicted new*" (beds at the threshold), the unit forecast with its range, the usage bar and the beds to watch. Deaths is a unit count only and lists no bed. An event the forecast skipped (`available: false`) reads "no data" / "not available", never 0, and does not blank the board.
> - **Now | Next 24 h:** a switch, or a sideways swipe.
>
> Staffing (D23) and the yardstick stay in the backend, the API and the chat; capacity is entered in the Settings form. The screen-by-screen section below describes this page.

ICU Horizon ("From bench to bedside") is the ICU team's board for 07:00 morning rounds. The unit name stays the big title. The backend (forecaster, workflows, dispatcher, `app/board.py`) lives in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin); this repo holds the frontend design, the mockup, and the contract it must meet. Journeys: [`USER_JOURNEY.md`](USER_JOURNEY.md). Decisions: [`DECISIONS.md`](DECISIONS.md). Words: [`NAMING_AND_WORDING.md`](archive/NAMING_AND_WORDING.md). Visual system: [`../DESIGN.md`](../DESIGN.md).

## How it runs

- Static HTML, CSS and vanilla JavaScript in one file; no build step, no Node in the image, works offline.
- Served by `app/board.py` (as `app/static/index.html`) on the team's two NVIDIA GB10 nodes. Served over http(s), the page reads the same-origin API below. Only when opened from `file://`, or with `#synthetic`, does it use its built-in synthetic generator, labelled "Demo data". A transient load failure over http(s) never switches a live board to synthetic data: the page retries (3 tries with backoff, then every few seconds), shows "Can't reach the board server — retrying" and keeps the last good data. The data-source label (a small outlined tag in the top strip, not a warning) reads "MIMIC-IV Demo" (`ward.source` `open-demo`, the default), "MIMIC-IV · local" (`mimic-iv`, real MIMIC-IV room views approved for local use) or "Demo data" (synthetic). `forecast.json` and `rooms.json` carry `"ward": {"source": "open-demo"|"mimic-iv"|"synthetic", "label": "..."}`; `synthetic` (the example files) reads "Demo data".
- Every server-supplied string reaches the page through one `esc()` helper or `textContent`; numbers are checked with `Number.isFinite`; `level`, `sex`, `age` and yardstick words are checked against fixed sets. The page loads no third-party scripts (CSP: self and Google Fonts only).
- Every POST (`/api/rerun`, `/api/capacity`, `/api/ask`) is same origin with `Content-Type: application/json` and `X-Lookahead: 1`; a refusal such as `403 {"ok":false,"reason":"request refused"}` shows its reason.
- Review flags in the URL hash: `#view=beds`, `#view=strain`, `#when=now`, `#when=next`, `#pending`, `#night`, `#room=7`, `#role=pharmacy`, `#fast` (short polls and runs), `#morning` (the scheduled run in progress, fallback only), `#synthetic`.

## What the board predicts

Five predictions only, all for the next 24 h, 07:00 to 07:00: ICU discharge, IMV, vasopressor, CRRT, death. No hypotension, no readmission, nothing else.

**Life support** means IMV (breathing tube or tracheostomy), a vasopressor infusion (inotropes alone do not count) or CRRT. **Now** means running at the 07:00 cut (decided 2026-11-14, Q29/Q30). ECMO and other mechanical support are not in the data and are not shown anywhere on the board.

## How this forecast was made

A native model, trained from scratch on our own token vocabulary; one forward pass per patient, then small classifiers on its last-layer summary; how Fuzzball ran it and what is only written so far. Full account, with sources: [`README.md`](../README.md#how-this-forecast-was-made). One page for judges: [`ONE_PAGER.md`](ONE_PAGER.md). Accuracy and its limits: [`RESULTS.md`](RESULTS.md).

## Data the board reads

| Source | What | Who writes it |
|---|---|---|
| `GET /api/forecast` | `forecast.json`; example [`../examples/forecast.json`](../examples/forecast.json). Before the first run: `{"resources":{},"note":"no forecast yet: the 07:00 run has not finished"}` | `app/aggregate.py` after each `t7-forecast` run |
| `GET /api/rooms` | `rooms.json`, stage ward only; example [`../examples/rooms.json`](../examples/rooms.json). Before the first run: `{"rooms":[],"note":"pending run"}` (not shown; the board says "No rooms yet") | lane 3, open MIMIC-IV Demo patients by default (D6); a real ward only when the board runs with `--real-ward` (D19), otherwise `{"rooms":[],"counts_only":true}` |
| `GET /api/runs` | `{next_scheduled, window, running: null / {name} / {unknown:true}, updating, last:{unit,room}, recent, demo_clock_hours, demo_clock_label, min_gap_minutes}`, or `{available:false, reason}` | `app/dispatcher.py` |
| `GET /api/capacity` | `{life_support_patients, vents_free, updated_at}` | board server |

### Coherent chat and board context

With `board.py --context PATH`, `GET /api/context` returns one validated envelope
containing `forecast` and `rooms`, with shared `snapshot_id` and `cohort_id`.
The page reads that envelope atomically; the two existing routes still expose
compatible projections. Without `--context` the route answers `200 {"available": false, "context_mode": false}`
(so the page's probe on every load leaves no failed request in the console) and the page
uses the two old reads; an older server's 404 means the same. An invalid configured context is a 503 and never falls back to stale
independent files. Chat replies include the publication identity they used.

`forecast_state: "pending-model"` preserves observed Now while every prediction
has `No estimate`. `on_now` is true, false or null; null is unknown. When a unit
count is incomplete, `now_known_patients` / `now_known_by` provide an explicit
lower bound and `now_unknown_patients` / `now_unknown_by` report missingness.
Unknown observations must not become off, zero, Steady or free machines.
`present: false` keeps a stable room slot for an ended stay, with no current
patient or forecast. The detailed envelope contract is in
[`backend/docs/CONTRACT.md`](../backend/docs/CONTRACT.md).

### forecast.json

```json
{ "made_at": "ISO", "cut_time": "ISO", "window": {"start": "ISO", "end": "ISO"}, "scope": "unit", "unit_name": "Medical ICU",
  "demo_clock_hours": 0, "beds": 25, "range": "80% (p10-p90)",
  "resources": { "icu_departure|ventilator|vasopressor|crrt|death": {"team", "p10", "p50", "p90", "expected"} },
  "life_support": { "now_patients": 10,
    "now_by": {"imv": 5, "vasopressor": 4, "crrt": 0, "ecmo": null},
    "expected_new_patients": {"p10", "p50", "p90"},
    "expected_by": {"imv": {"p10","p50","p90"}, "vasopressor": {}, "crrt": {}} },
  "yardstick": { "kind": "capacity|typical", "words": "ON TRACK|TIGHT|SHORT or USUAL|BUSY|VERY BUSY", "level": "ok|amber|red",
    "capacity": {"life_support_patients": null, "vents_free": null, "set_at": null, "set_by_role": null},
    "typical": {"life_support_patients": 15} },
  "check_first": [{"room": 20, "any_life_support": 0.71, "level": "high"}, {"room": 12, "any_life_support": 0.5, "level": "high"}],
  "levels": {"medium": 0.2, "high": 0.4}, "out_tag": 0.6 }
```

`now_patients` counts patients with IMV, a vasopressor infusion or CRRT running at the 07:00 cut. `check_first` is the High rooms by combined chance (`any_life_support`), at most three; the Bed board does not read it; it builds its priority rail from `rooms.json`. The board reads only the keys above; anything else is ignored.

### rooms.json (stage ward; a real ward only in real-ward mode, D19)

```json
{ "made_at": "ISO", "rooms": [ { "room": 1, "updated_at": "ISO", "cut_time": "ISO", "window": {"start": "ISO", "end": "ISO"},
    "scope": "unit|room",
    "name": {"display": "Rivera, J.", "first": "James", "last": "Rivera", "fictional": true},
    "on_now": {"imv": false, "vasopressor": false, "crrt": false, "ecmo": null},
    "on_life_support": false,
    "stopped_before_cut": {"imv": false, "vasopressor": false, "crrt": false},
    "p": {"imv": 0.06, "vasopressor": 0.15, "crrt": null, "icu_departure": 0.32, "death": 0.06},
    "any_life_support": 0.26, "level": "low|medium|high", "out": false,
    "past_12h": [{"h": -1, "text": "Lactate 3.1 (up from 2.2)"}] } ] }
```

`name` is optional: `{"display": "Rivera, J.", "first": "James", "last": "Rivera", "fictional": true}`. The board shows `display` beside sex and age and the full name on the room page; without the key everything renders as before. Each part must be 40 characters or fewer and only letters, spaces and `. , ' -`, or the name is dropped. Names in the demo data and in `examples/rooms.json` are made up; a real deployment would get them from the hospital. `null` in `p` means the support is already running (shown as "on now", never forecast as new). `on_life_support` is true when two or more supports are running. `stopped_before_cut` marks supports switched off before 07:00 (room page note only). `any_life_support` is the chance of any new IMV, vasopressor or CRRT, skipping supports already on. `level` is High at 0.4 or more, Medium at 0.2 or more, else Low. `out` is true when `icu_departure` is 0.6 or more. Death never sets the level.

## Actions the board sends

| Action | Request | Response |
|---|---|---|
| Update the unit or one room | `POST /api/rerun {"role": "ICU nurse", "scope": "unit"}` or `{"scope": "room", "room": 12}` | `{"started": true, "workflow", "name", "scope", "room", "demo_clock_hours", "demo_clock_label"}` or `{"started": false, "reason": "..."}` (HTTP 200; the reason is shown verbatim, for example "Updated 12 minutes ago. You can update again at 13:17.") |
| Set tonight's capacity | `POST /api/capacity {"life_support_patients": 0..50, "vents_total": 0..50, "role": "ICU nurse"}` (every number optional; a `vents_free` in the request is ignored, not refused: the save succeeds and the value is not stored, because free ventilators are worked out from `vents_total` when read) | `200 {"ok": true, "capacity": {...}}` or `400 {"ok": false, "reason": "..."}` (shown) |
| Ask the chat | `POST /api/ask {"question", "role", "room"?, "seen_made_at"?}` | `{"answer", "made_at", "trace"?}`; the board sends back the last `made_at` it received, and the server adds "Forecast updated at HH:MM. Answers below use it." when it changed |

Roles accepted: `ICU nurse`, `ICU physician`, `pharmacy`, `respiratory therapy`, `bed manager`. The board never sends or stores names. The chat can start "update room 12" or "update the unit" only when the user asks in those words; chips never start an update.

Polling: `/api/runs` every 10 s while a run is going or updating (the dispatcher caches its job list for 10 s), every 5 min otherwise. When `made_at` (or the last room run) changes, reload `/api/forecast` and `/api/rooms` and refresh the numbers in place; keyboard focus does not move. The demo-clock line uses `demo_clock_label` from `/api/runs` verbatim (for example "Ward clock 11:30 (07:00 + 4.5 h)"); the offline fallback writes "Demo clock: recorded patients, time advanced N h".

## Screens and what each must do

This section describes the final page: the team's design (D25) with the refinements the team approved on 2026-11-15 ([`UI_REVIEW.md`](UI_REVIEW.md)). The earlier design (bed statuses, the "Worry first" rail, the role picker, the Staffing card) is retired and is not described here; its record is D12, D13, D22 and D25 in [`DECISIONS.md`](DECISIONS.md).

The page is titled **ICU Horizon** with the descriptor "next 24 hours". The unit ("Medical ICU · 25 beds") is a chip beside the data-source tag and comes from the forecast (`unit_name`, optional; "ICU" when absent, and `beds`). Two controls sit under the header and stay at the top while scrolling:

- **Tabs** (what you look at): **Bed board** (default) and **Unit strain**. `#view=beds|strain`, remembered in `localStorage` (`lookahead-view`).
- **Time switch** (when): **Now** and **Next 24 h** (default), by button, left and right arrow keys, or a sideways swipe. `#when=now|next`, remembered (`lookahead-when`). Now is ink and shows only what is running at 07:00; Next 24 h is blue and shows the forecast. Switching re-renders in place: same grid, same room order, same scroll position.

Chances are **whole percentages** ("23%"; "<5%" when very small; "No estimate" for null).

**Thresholds.** There is no bed status. An event is shown on a bed when its chance is at or above that event's threshold. Thresholds live in the Settings panel: "Flag beds at **40% · 20% · 10%**" (default 20%) sets the three life supports together, a visible **Reset to standard** returns every line to the standard (20% watch, 40% worsening, 60% leaving; D13, D14, D26), and a stepper per event (Ventilator, Vasopressor, CRRT, Leaving; leaving defaults to 60%) sets one, showing how many beds it catches. It is a view setting kept on the device (`localStorage` `lookahead-lines`); nothing is sent to the server. Changing a threshold never moves a tile. Death has no threshold, because death never marks a bed. The standard lines were applied when PR #24 merged (D26); before that the defaults were 25% with presets 50 / 25 / 10.

1. **Header.** "ICU Horizon · next 24 hours"; "07:00 to 07:00"; the unit chip; the data-source tag ("MIMIC-IV Demo", "MIMIC-IV · local" or "Demo data"); **Update the unit**; the gear (Settings).
2. **Update progress** (under the header, only during and just after an update; item 8).
3. **Alert line** (both tabs, Next 24 h). What is short against the machines the unit has ("Ventilators short by 1", "CRRT at the limit, none spare"); **"Deaths expected 1 (0 to 3)"**, the one place death appears outside an opened bed; on Unit strain the three highest-risk beds as 44px chips; "10 on life support now · +5 new expected in 24 h" with the yardstick word (USUAL, BUSY, VERY BUSY, or ON TRACK, TIGHT, SHORT when tonight's staffing is set), which links to Unit strain; "Last run 07:00".
4. **Bed board, Next 24 h.**
   - **See first**: one compact row above the grid with the three beds that have the highest chance of a new life support (the top-beds rule; a tie with the third is included). Each is a button with the red person figure, the bed number, the name, and the bed's top event as a circle icon with its chance. It opens the bed. On a phone the three sit side by side without the figure and the name.
   - A sub-heading says what is forecast ("Forecast, per patient · chance in the next 24 h of starting a ventilator, vasopressor or CRRT, or leaving the ICU"), with a one-line key: ventilator, vasopressor, CRRT (solid = running, circled = may start) and discharge.
   - **Bed tile**: a person figure, the bed number (the identifier), the generated name with sex and age ("Rivera, J. · M 68"; cut with an ellipsis, full name in its legend). Then the life support running at 07:00 as solid icons, or "No life support". Under a hairline, **NEXT 24 H**: a circle icon and its percentage for each new support at its threshold, and for discharge at its threshold; "nothing new" otherwise; "No estimate" when a support's state or a score is missing. When a new life support is at its threshold the person figure turns red and pulses; discharge alone does not. **Death is never shown on a tile**: no death circle, no red figure for death, no death in the tile's label.
   - **All N beds**: every bed in room order, five across on a desktop, two on a phone. A tile opens the bed.
5. **Bed board, Now.** Sub-heading "Now, per patient · life support running at 07:00". A tile shows the bed, name, sex and age, and large solid icons. Weight is the number of supports running: none is white and reads "No life support", one sits on the tinted ground, two or more has a red border, reads "2 supports" and is counted as **Critical** in the key. No percentages, no See first row.
6. **Unit strain, Next 24 h.** Titled "Predicted events · next 24 h". One card per event, in this order: Deaths, Ventilator, Vasopressor, CRRT, Leave the ICU.
   - **Deaths** shows only the unit forecast and its likely range, and the words "Counted for the whole unit. No bed is listed or ranked by death." No bed, no threshold, no "Predicted new".
   - **Ventilator, Vasopressor, CRRT**: "On now"; "Free" (of the unit's total; "not set" opens Settings); "Predicted new*" (beds at or above the threshold: a flag per bed, not a certainty); "Unit forecast N (a to b)"; for ventilators and CRRT the total-length bar (solid = in use now, lighter = with the flagged beds, red when that passes the total); then "Beds to watch": the beds at the threshold as person figures that fill with the chance, highest first. A card reads **SHORT** (red) when the flagged beds outnumber what is free and **AT LIMIT** (amber) when they equal it. The three highest-risk beds pulse red.
   - **Leave the ICU**: the beds at the leaving threshold in grey; a leaver on life support carries a small device badge, and the ventilator and CRRT cards say how many machines likely leavers would free.
   - **Other beds**: every bed under every threshold, with its highest chance.
   - An event the forecast skipped (`available: false`) reads "no data" / "not available", never 0.
7. **Unit strain, Now.** "Unit now · life support running at 07:00": patients on life support now, tonight's staffing and ventilators free when set, and a card per support with the solid figures of those beds. Nothing forecast.
8. **Update flows.** "Update the unit" and "Update this bed" send `POST /api/rerun`. The button reads "Updating…" and a progress strip shows four steps: **Queued → Running on the GPU → Scoring → Done**, with "The last forecast stays on screen." Served live the step comes from `GET /api/runs`, polled every 10 s while a run is going: `running.state` `PENDING` is Queued, any other running state is Running on the GPU, and once the job has left the list the board reads the new scores (Scoring). When the new forecast lands the cards take one short blue ring and the strip reads **"Updated HH:MM · The board shows the new forecast."** for 8 seconds. Failures, in plain words, stay until dismissed:
   - refused: "Not started." and the server's reason ("Updated 12 minutes ago. You can update again at 13:17.");
   - stopped by the dispatcher (`stuck` in `/api/runs`): "The update was stopped. It waited for a free GPU for 5 minutes and was stopped. The forecast from 07:00 is still shown. Update again; if it happens twice, ask the team what is holding the GPU.";
   - ended with no new file after 60 s: "No new forecast arrived. …";
   - the server or the job list cannot be read: the strip keeps its step and says it is still trying.
   `/api/runs` has no separate scoring state, so Scoring is the time between the job leaving the list and the files landing. Inside an opened bed the same strip shows for that bed's update.
9. **Bed pop-up** (`#room=N`; Escape, "Close bed", a press outside or the browser's back button closes it; Escape closes one panel at a time). The heading "Bed 12 · James Rivera · M 68", the NOW → NEXT 24 H strip with names, one line with the window and "updated 07:00", the time switch and previous / next bed.
   - **Next 24 h**: "Five predictions for this patient · chance in the next 24 h": "Starts a ventilator (IMV)", "Starts a vasopressor", "Starts CRRT", "Leaves the ICU (ward or step-down)", **"Dies in hospital"**. Each row is an icon, a level word (High, Medium, Low, from the flag line), a 10-dot array and the percentage. A support running now reads "On now"; a missing score reads "No estimate".
   - **Vitals · last 12 h** when the data carries `vitals_12h`: heart rate, mean arterial pressure, SpO2, respiratory rate, hourly medians.
   - **What the model read · last 12 h** (five, then "Show more"), and the buttons **Update this bed** and **Ask about this forecast**.
   - **Now**: the three supports, each "On now", "Not running" or "Unknown".
10. **Ask ICU Horizon** (chat). A launcher at the bottom right; the panel is a non-modal dialog (a bottom sheet on a phone) and sits above an opened bed. Header: the name, a context chip ("Unit" or "Bed 12"; on a bed it switches between that bed and the unit), minimise and close. Minimise and Escape keep the conversation; close clears it.
    - Suggested questions follow the context, under a small label. **About the unit**: "Which beds should we see first?", "Will we be short of ventilators or CRRT?", "Who is likely to leave the ICU today?", "Summarise the next 24 hours". **About bed 12**: "Why is bed 12 flagged?" (or "What is forecast for bed 12?"), "What did the model read for bed 12 in the last 12 hours?", "How likely is bed 12 to leave the ICU?".
    - Answers: numbers are bold; every bed number is a link that opens that bed's pop-up, with the panel still open on a desktop (on a phone the sheet steps aside). "Thinking…" with Stop; "Can't reach the chat right now. Try again."; treatment questions are declined. `POST /api/ask` is unchanged.
11. **Settings** (the gear; a side panel): light or dark board, the thresholds, and Capacity (ventilators and CRRT machines on the unit, and optionally the life-support patients tonight's staffing covers).
12. **Figure legends (tooltips).** One floating element explains any icon, figure, bar, chip or number on hover, keyboard focus, tap or long-press. Its words come from one map (`DEF`) that also builds the key and "How this forecast was made".
13. **How this forecast was made** (foot): one folded disclosure: the five predictions, each bed, the thresholds, the icons, Unit strain, the status words, the table of the five forecasts, model, method, where and when, and what is not included.

### Icons

One family drawn for this board, inline as an SVG sprite (24 grid, `currentColor`, 1.75 stroke). Solid means running now, outline in a circle means it may start. Ventilator: lungs with an airway tube and circuit. Vasopressor: a syringe with a drop. CRRT: a capped filter with blood lines and arrows. Leaving: a bed with an outward arrow. Death: a pulse line, used only in the alert line, the Deaths card and the bed pop-up. The team's person figure (head and shoulders) marks a bed. Sheet: [`screenshots/icons.png`](screenshots/icons.png).

## Cognitive load

The board is read at 07:00 by a tired team at a workstation or a wall screen, often mid-conversation and from a few metres. Target: "who do we see first?" is answered in two seconds from the See first row, and "are we covered?" from the alert line; neither needs scrolling at 1440 px. Phone order: header, tabs and the time switch (sticky), the alert line, See first, all beds (two across), footer.

| What we surface | Rule | Why it lowers load |
|---|---|---|
| Who to see first | See first leads the Bed board: the three highest-risk beds, each with its top event. | Attention goes to three beds before anything else. |
| Now, then next | Every bed reads top to bottom: what is running, a hairline, what may start. | A change is seen as a change, not worked out from two numbers. |
| Pictures before words | One icon per support, solid for running, circled for expected. | Read from across the room and by people who do not share a first language. |
| No bed status | A bed shows events at their thresholds; only a new life support turns its figure red. | No tile needs decoding. |
| Death is a unit number | One count in the alert line and on the Deaths card; a row in an opened bed; never on a tile. | No bed is marked by death (D13). |
| The team sets the thresholds | Settings changes which events show, never where a bed is. | Sensitivity is a choice the team makes, visibly, in one place. |
| Ink is now, blue is forecast | On every screen. Amber and red appear only on TIGHT / BUSY / AT LIMIT, SHORT / VERY BUSY and the highest-risk figures. | Colour means one thing. |
| Strain on its own tab | The alert line keeps one line and one word; the event cards live on Unit strain. | The bed board stays a bed board. |
| An update is visible | Four named steps, then "Updated HH:MM"; a failure says what happened and what to do. | Nobody wonders whether the button worked. |
| Percentages, one way | "23%" everywhere, "<5%" when very small; the bed pop-up keeps a 10-dot array as the picture. | One number format on every screen. |
| Named, not implied | A NEXT 24 H caption on every tile, a sub-heading that says what is forecast, and a legend on hover, focus or long-press. | A newcomer can tell what each figure is. |
| Chat out of the way | A launcher at the bottom right; the panel is non-modal and keeps its conversation. | The board stays a board. |
| One horizon | Next 24 h, 07:00 to 07:00. No time slider; the switch only hides or shows the forecast. | Nothing to choose before reading. |
| Definitions folded | Every rule and the model details sit in one closed section at the foot. | The curious can look; the 07:00 reader never has to. |
| Day and night boards | Same layout and words; the user picks the board. | Nothing moves when the lights go down. |

## Capacity fields (`/api/capacity`)

> **Status (D25):** the page (`backend/app/static/index.html`, the team's final board design) has only the Settings capacity form: ventilators, CRRT machines and, optionally, the life-support patients tonight's staffing covers. It has no nurses or respiratory-therapist fields. The form sends `vents_total` and `crrt_total` (and `life_support_patients` when given), never `vents_free`; a total the user blanks is sent as `null`, a box that was never set is left out. A failed save reads "Not saved" with the reason and leaves the device copy alone; a response that arrives after a newer save is ignored. Served live, `GET /api/capacity` is read on load and on every refresh and its totals win (even `null`); Reset clears the totals on the server too.


"Set tonight's capacity" sends `POST /api/capacity` with `role` and **only the fields the user set or cleared**. A box that was never set is left out, and the server keeps what it has for that key. A saved total the user blanks is sent as `null`, and the server clears it:

| Field | Meaning |
|---|---|
| `vents_total` | ventilators on the unit (0 to 50) |
| `crrt_total` | CRRT machines on the unit (0 to 50) |
| `nurses_on_shift` | nurses on shift (0 to 50) |
| `rt_on_shift` | respiratory therapists on shift (0 to 50) |
| `life_support_patients` | life-support patients tonight's staffing covers (optional; drives the unit yardstick) |
| `vents_free` | not sent: free ventilators are total minus in use now, worked out when read, never stored |

The response is `{"ok": true, "capacity": {...}}` (or `{"ok": false, "reason"}`, shown). On load and on every refresh the page reads `GET /api/capacity` (either the object itself or `{"capacity": {...}}`) and the forecast's `yardstick.capacity` block. For `vents_total` and `crrt_total` (the page has no boxes for `nurses_on_shift` and `rt_on_shift`; the API and the chat carry them): **when the server returns the key, its value wins** (even `null`); when the key is absent (an older backend) or in `#synthetic` mode the copy kept on the device (`lookahead-machines`) is used. A saved `life_support_patients` from `GET /api/capacity` recomputes the yardstick on load when the forecast does not carry it yet, so a saved shortage survives a reload. The line "Capacity set 07:12 by ICU nurse (charge)" comes from the server's `set_at` (or `updated_at`) and `set_by_role`. An older server that refuses a save without `life_support_patients` leaves the numbers on the device and says so.

## Staffing (D23)

> **Status (D25):** the page (`backend/app/static/index.html`, the team's final board design) does not draw this: no Staffing card, no 1:1 tags, no Check first row. Staffing stays in the backend: the API and the chat described here are shipped and tested.


Rules: a nurse is **1:1** for a patient on CRRT or on **two or more vasoactive infusions**, **1:2** for everyone else; one **respiratory therapist per six ventilated patients**, rounded up.

The data and the served chat below are current. The page bullets (Unit strain card, bed-tile tags, room page line) are **historical: the design before D25, not drawn by the page**.

- Data, all optional: per room `on_now_detail: {"vasoactives": int|null}`; in `forecast.json` `staffing_now: {nurses, one_to_one, one_to_two, rt, vented}` and `staffing_next_24h: {nurses: {p10,p50,p90}, rt: {p10,p50,p90}}`. Historical (before D25): when they were absent the page worked them out, 1:1 from `on_now.crrt` and the vasoactive count (a vasopressor flag alone counts as one agent); next 24 h adds expected CRRT starts (new 1:1 beds) and ventilator starts from `life_support.expected_by`, and assumes a bed that empties is refilled.
- *Historical, not on the page (D25).* **Unit strain**: a Staffing card led the row. Nurses: needed now, next 24 h with its range, "1:1 × 3 · 1:2 × 22". Respiratory therapists: needed now, next 24 h with its range, "5 ventilated". With "Nurses on shift" or "RTs on shift" entered, the block shows the number on shift and SHORT (need above it) or AT LIMIT (equal); the header strain line adds "Nurses short by 2" or "RT short by 1".
- *Historical, not on the page (D25).* **Bed tiles**: Now showed a quiet "1:1" tag on a 1:1 bed (legend: "1:1 nurse: on CRRT" or "1:1 nurse: on 2 vasoactive infusions"); nothing for 1:2. Next 24 h shows "1:1 likely" only when the chance of starting CRRT is at the flag line or more.
- *Historical, not on the page (D25).* **Room page**: the sub-line started "Nursing 1:1 (on CRRT)" or "Nursing 1:2"; the offline chat answered "How many nurses do we need?".
- **Chat** (served): `get_staffing` gives the nurses and respiratory therapists the ratio rule asks for, now and in the next 24 h; a count the forecast cannot give reads "unknown" or "No estimate".

## Robustness (review of PR #3)

- **One task without counts** (a skipped probe returns null counts): only that task reads "No estimate"; every other count, bar and figure still shows. The board needs only the Now counts and the unit total to draw.
- **Stale forecast**: when `made_at` is a day old or more the run line reads "Forecast from yesterday 07:00 · update the unit" on an amber ground and the header strain line carries "From yesterday" (or "From 2 days ago").
- **Flags survive navigation**: `#synthetic`, `#pending`, `#fast` and `#night` are kept in every link and hash the page writes, so a served demo stays a demo after a reload.
- **Chat**: closing the chat drops any reply still on its way; `seen_made_at` is the forecast the last answer used, not the page's latest.
- **Refresh keeps keyboard focus** on the same bed or figure.
- **Synthetic examples**: `examples/forecast.json` and `examples/rooms.json` carry `"ward": {"source": "synthetic", "label": "Demo data"}`; the page shows "Demo data" for that source.

## Forecast not ready (`forecast_state: "pending-model"`)

Both files may carry `"forecast_state": "pending-model"` (see the backend's `docs/CONTRACT.md`): there are no model weights or probes yet. Every room's `p` is null, the unit's expected counts are null with `available: false`, there is no yardstick, and the Now side (`on_now`, names, age and sex, `life_support.now_patients` and `now_by`) is real. A missing key or `"ready"` behaves as before.

- The page never prints "null", "NaN" or "undefined": every forecast number is checked before it is drawn, and in this state none is drawn.
- The time switch opens on **Now** (not saved). Choosing Next 24 h shows one calm line, "Forecast not ready yet: the model is still being prepared.", above the same Now content.
- Nothing forecast is computed or drawn: no See first row, no circles; the "Flag beds at" control is disabled.
- The header strain line reads "N on life support now" only; the run line reads "Now as of 07:00 · forecast not ready yet".
- Unit strain shows the on-now counts, the figures of those beds and the capacity form; no expected numbers, bars or deaths line.
- The room page shows what is running and the last 12 hours, with "Forecast not ready yet" in place of the five predictions.
- The chat answers Now questions ("Who is critical now?", "How many are on a ventilator now?"); forecast questions get the same line and the Now counts.
- Review flag `#pending` puts the built-in synthetic data in this state.

## States the frontend must handle

| State | Show |
|---|---|
| No forecast yet | "No forecast yet" on the Unit strain tab, no header strain line, a dash in the footer table, "No rooms yet" on the Bed board, and the update control |
| Forecast older than 24 h | the age and an update prompt |
| Run in progress (button, chat or scheduled) | "Updating…", the progress strip (Queued, Running on the GPU, Scoring, Done), the last forecast kept; then "Updated HH:MM" |
| Update refused | "Not started." and the server's reason, verbatim ("Updated 12 minutes ago. You can update again at 13:17.") |
| Update stopped, or ended with no new forecast | what happened and what to do, in plain words, until dismissed |
| Capacity refused | the server's reason in the form |
| Chat not answering | "Can't reach the chat right now. Try again." |
| API unreachable (at load or later) | "Can't reach the board server — retrying", retry with backoff, last good data kept; synthetic only for `file://` or `#synthetic` |
| A room missing from `rooms.json` | no tile and no room page; deep link goes to the board |
| A room missing from `rooms.json` (link or hash) | "Room N is not in this forecast." on the board |
| Support already running | its solid icon left of the arrow; "On now" on the room page (never a number) |

## Rules

- **Counts only for real MIMIC-IV, unless the server runs in real-ward mode** (D6, revised by D19). By default room-level views and room chat are for the stage ward only (open MIMIC-IV Demo patients, excluded from training). A real MIMIC-IV ward is served counts-only (`/api/rooms` returns `{"rooms": [], "counts_only": true}`, `check_first` is empty, the chat answers "counts only" to a room question) unless the board server was started with `--real-ward` on the local cluster. Rooms carry room numbers and invented names only. Never log questions or answers.
- **Every number has its range**, written "(a to b)" and explained once as 8 in 10 likely outcomes. Chances are whole percentages ("23%", "<5%", "No estimate"); clinical history values in the last 12 h list are shown as recorded.
- **Status never by colour alone**; text at 4.5:1 or better in day and night.
- **Honest labels, no warnings**: a plain data-source tag ("Demo data", "MIMIC-IV Demo", "MIMIC-IV · local"), "Not ready yet" only as a standalone state where no run has produced a number, and no hedging copy; admissions are excluded from the forecast and the footer says so once.
- **Decision support, never a treatment recommendation.**
- **Design**: follow [`../DESIGN.md`](../DESIGN.md) (the picture board: ink is now, blue is forecast). Use the Impeccable skill (`/impeccable`) for any UI work.

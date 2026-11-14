# Frontend spec: Lookahead, the ICU board

Lookahead ("The next 24 hours, in one place.") is the ICU team's board for 07:00 morning rounds. The unit name stays the big title. The backend (forecaster, workflows, dispatcher, `app/board.py`) lives in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin); this repo holds the frontend design, the mockup, and the contract it must meet. Journeys: [`USER_JOURNEY.md`](USER_JOURNEY.md). Decisions: [`DECISIONS.md`](DECISIONS.md). Words: [`NAMING_AND_WORDING.md`](NAMING_AND_WORDING.md). Visual system: [`../DESIGN.md`](../DESIGN.md).

## How it runs

- Static HTML, CSS and vanilla JavaScript in one file; no build step, no Node in the image, works offline.
- Served by `app/board.py` (as `app/static/index.html`) on the team's two NVIDIA GB10 nodes. Served over http(s), the page reads the same-origin API below. Only when opened from `file://`, or with `#synthetic`, does it use its built-in synthetic generator, labelled "Demo data". A transient load failure over http(s) never switches a live board to synthetic data: the page retries (3 tries with backoff, then every few seconds), shows "Can't reach the board server — retrying" and keeps the last good data. The data-source label (a small outlined tag in the top strip, not a warning) reads "MIMIC-IV Demo" (`ward.source` `open-demo`, the default), "MIMIC-IV · local" (`mimic-iv`, real MIMIC-IV room views approved for local use) or "Demo data" (synthetic). `forecast.json` and `rooms.json` carry `"ward": {"source": "open-demo"|"mimic-iv", "label": "..."}`.
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
| `GET /api/rooms` | `rooms.json`, stage ward only; example [`../examples/rooms.json`](../examples/rooms.json). Before the first run: `{"rooms":[],"note":"pending run"}` (not shown; the board says "No rooms yet") | lane 3, open MIMIC-IV Demo patients only (D6) |
| `GET /api/runs` | `{next_scheduled, window, running: null / {name} / {unknown:true}, updating, last:{unit,room}, recent, demo_clock_hours, demo_clock_label, min_gap_minutes}`, or `{available:false, reason}` | `app/dispatcher.py` |
| `GET /api/capacity` | `{life_support_patients, vents_free, updated_at}` | board server |

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

`now_patients` counts patients with IMV, a vasopressor infusion or CRRT running at the 07:00 cut. `check_first` is the High rooms by combined chance (`any_life_support`), at most three; the Bed board does not read it; it builds its Worry first rail from `rooms.json`. The board reads only the keys above; anything else is ignored.

### rooms.json (stage ward only)

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
| Set tonight's capacity | `POST /api/capacity {"life_support_patients": 0..50, "vents_free": 0..50, "role": "ICU nurse"}` (`vents_free` optional) | `200 {"ok": true, "capacity": {...}}` or `400 {"ok": false, "reason": "..."}` (shown) |
| Ask the chat | `POST /api/ask {"question", "role", "room"?, "seen_made_at"?}` | `{"answer", "made_at", "trace"?}`; the board sends back the last `made_at` it received, and the server adds "Forecast updated at HH:MM. Answers below use it." when it changed |

Roles accepted: `ICU nurse`, `ICU physician`, `pharmacy`, `respiratory therapy`, `bed manager`. The board never sends or stores names. The chat can start "update room 12" or "update the unit" only when the user asks in those words; chips never start an update.

Polling: `/api/runs` every 30 s while a run is going or updating, every 5 min otherwise. When `made_at` (or the last room run) changes, reload `/api/forecast` and `/api/rooms` and refresh the numbers in place; keyboard focus does not move. The demo-clock line uses `demo_clock_label` from `/api/runs` verbatim (for example "Ward clock 11:30 (07:00 + 4.5 h)"); the offline fallback writes "Demo clock: recorded patients, time advanced N h".

## Screens and what each must do

The page is titled **Lookahead** with the descriptor "ICU forecast · next 24 hours"; the unit ("Medical ICU · 25 beds") is a chip beside the data-source tag and comes from the forecast (`unit_name`, optional; "ICU" when absent, and `beds`). Two controls sit under the header and stay at the top while scrolling:

- **Tabs** (what you look at): **Bed board** (default) and **Unit strain**. `#view=beds|strain`, remembered in `localStorage` (`lookahead-view`).
- **Time switch** (when): **Now** and **Next 24 h** (default). `#when=now|next` beside `#view=`, remembered (`lookahead-when`), `aria-pressed`, left and right arrow keys. Now is ink and shows only what is running at 07:00, with nothing forecast; Next 24 h is blue and shows the forecast. It applies to both tabs and the room page. Switching re-renders in place: same grid, same room order, same scroll position.

Chances are **whole percentages** ("23%"; "<5%" when very small; "No estimate" for null).

- **Flag beds at** (which chance flags a bed): a segmented control **50% · 25% · 10%** beside the time switch on both tabs in Next 24 h (hidden in Now), default 25%, with a **Thresholds** popover: a − / + stepper for Ventilator, Vasopressor, CRRT and Leaving, each showing how many beds it catches, a custom line for all supports, and Reset. It is a **client-side view setting** kept on the device (`localStorage` `lookahead-lines`); nothing is sent to the server. The backend still sends `level` and `out` computed with its own thresholds, but **the page now computes each bed's status from `p` and the chosen lines**. Changing the line never moves tiles (same grid, same order); only their status changes, at once. The key shows live counts ("Worsening 1 · Watch 7 · Not improving 6 · Leaving 4"), and every definition, tooltip and the disclosure state the current lines.

1. **Header** (slim): "Lookahead" and its descriptor; "07:00 to 07:00"; the unit chip; the data-source tag ("MIMIC-IV Demo", "MIMIC-IV · local" or "Demo data"); the run line ("Updated 13:05", or "Updating the unit for ICU nurse (charge). The last forecast stays on screen."); a strain line that links to the Unit strain tab ("10 on life support now · +5 new expected in 24 h · USUAL"; in Now, "10 on life support now"); Night board / Day board; role picker ("I am"); **Update the unit**.
2. **Bed board, Next 24 h.** A sub-heading says what is forecast: "Forecast, per patient · chance in the next 24 h of starting a ventilator, vasopressor or CRRT, or leaving the ICU", with a one-line key beside it.
   - **Bed tile**: room number (the identifier), then the patient's display name with sex and age ("Rivera, J. · M 68"; the name is cut with an ellipsis when space is short and the full name is in its legend; no name when the data has none), one trajectory status, then two captioned columns joined by an arrow. **NOW**: solid icons for the life support running at 07:00, or "no support". **NEXT 24 H**: an outline icon and its percentage for each new support at its line or more; the bed-with-arrow and its percentage when leaving is at the leaving line or more, and from the flag line for any bed on life support; a plus in a ring with the combined chance when the bed is flagged but no single support reaches its line; "leaving <25%" (the line) on a Not improving bed; "nothing new" otherwise. In the Worry first rail each item also carries its name ("Vasopressor 43%"); on grid tiles the name is in the tooltip and the tile's label.
   - **Trajectory status**, one per bed, by fill or border, a shape and a word:

     | Status | Rule (line = the chosen flag line, default 25%) | Look |
     |---|---|---|
     | Worsening | any new life support, combined or one support, at the next step above the line (10 → 25, 25 → 50, 50 → 75) | full blue tile, solid triangle |
     | Watch | any new life support, combined or one support, at the line or more | light blue tile, outline triangle |
     | Not improving | on at least one life support now, leaving under the line, and nothing new flagged | tinted ground, 3px ink border, two bars |
     | Leaving | leaving at the leaving line or more (default 60%, set in Thresholds) | white tile, 2px green border, bed with arrow |
     | Steady | everything else | white tile, dot |

     The rules are checked in that order. Death never enters. **Every status is derived on the page** from `p` and the lines; Not improving comes from the five predictions too: there is no coming-off-support forecast, so "on support and unlikely to leave" stands in for lack of improvement. Nothing new is read from the API; the combined chance is recomputed from `p` for ordering.
   - **Worry first** (top of the tab, tiles on the board ground): the Worsening rooms (highest combined chance first), then the Not improving rooms. "No room is worsening or not improving." when both are empty.
   - **All N rooms**: every room in room order, five across on a desktop, two on a phone (where the two columns of a tile become two labelled rows). A tile opens the room page.
3. **Bed board, Now.** Sub-heading "Now, per patient · life support running at 07:00". A tile shows the room, sex and age, and large solid icons with their names ("Ventilator", "Vasopressor", "CRRT"). Weight is the number of supports running: none is white and reads "No life support", one has a light ink tint, two or more has an ink border and reads "2 supports". No statuses, percentages or arrows. The rail becomes **Sickest now**: beds on two or more supports, then one. The key reads "Life support running at 07:00".
4. **Unit strain, Next 24 h.** Titled "Unit forecast · next 24 h (07:00 to 07:00)".
   - **Life support** lead: the yardstick word as a chip with its name ("vs tonight's staffing" or "vs a typical day"), "10 on life support now", "+5 expected new starts (3 to 8)", a range bar of now plus new, and one line ("Now plus new 15 (13 to 18) · typical day 15" or "· staffing covers 14"). The chip is green-outlined for ON TRACK / USUAL, amber for TIGHT / BUSY, solid red for SHORT / VERY BUSY; the card takes an amber or red border to match. "Not ready yet" when `yardstick` is null.
     - Capacity set (server rule, `docs/CONTRACT.md`): ON TRACK when p90 <= capacity; TIGHT when p90 > capacity >= p50; SHORT when p50 > capacity.
     - No capacity: USUAL, BUSY, VERY BUSY against a typical day (from training data).
   - "Deaths expected in the unit 1 (0 to 3)", one quiet line.
   - **Set tonight's capacity** (a folded button; Dema's machine-total model): "Ventilators on the unit (total)", "CRRT machines on the unit (total)" and, optional, "Life-support patients tonight's staffing covers"; whole numbers 0 to 50. Free = total − in use now; lower a total when a machine is out of service. The two totals are kept on the device (`lookahead-machines`). When the staffing number is given the form sends `POST /api/capacity` as before, with `vents_free` derived from the ventilator total; without it nothing is sent ("Saved on this device."). The API is unchanged; **backend follow-up: a field for the CRRT total (and totals rather than a free count)**. After a server save: "Capacity set 07:12 by ICU nurse (charge)", and the yardstick is recomputed locally with the server's rule until the next forecast. "View against a typical day" is a view toggle on this screen only. **Reset** clears the machine totals (and, in the offline demo, the staffing number; the server cannot clear its own).
   - **One card per support** (Ventilator (IMV), Vasopressor, CRRT) and one for **Leaving the ICU**; the role's card comes first (pharmacy: vasopressor; respiratory therapy: ventilator; bed manager: leaving). Each: the icon, the name and a subtitle that says what is counted ("patients expected to start a ventilator in the next 24 h"), "N on now", "+N expected new starts (a to b)", a range bar, then the beds behind the count as Dema's person figures: "On now" (solid ink figures) and "Beds at 25% or more · 4 beds" (the support's line; figures fill with the chance, highest first, percentage under the room number; a bed at the next step above the line has a red fill and a soft static halo). Leaving: "N expected to leave (a to b)", the bar, and "Beds at 60% or more · 5 beds" in grey; a leaver on life support carries a small device badge. Cards are wider when they hold more beds, so the row stays even. A figure shows the room number only; its legend adds the name ("Room 20 · Rivera, J. · 40% chance of starting a ventilator"). A figure opens the room page.
   - With a machine total set (or a ventilators-free number from the server), the ventilator and CRRT cards show "N free of T", Dema's **total-length bar** (the whole bar is the total; solid = in use now, lighter = with the flagged beds, a tick for each, red when that passes the total), and a label only when it matters: **SHORT** when the flagged beds outnumber what is free (red border), **AT LIMIT** when they equal it (amber border), nothing when fine. The header strain line adds the same alert ("Ventilators short by 1", "CRRT at the limit"), so there is one alert place. The unit yardstick word is not changed by it.
   - **Devices leavers would free**: "N may free up if likely leavers go" on the ventilator and CRRT cards (beds on that support now at the leaving line or more), and on the Leaving card "If these beds leave, they free 2 ventilators, 1 CRRT".
   - **Range bar**: track, the 8-in-10 range in blue, a bead at the median, a solid ink line for what is free or covered, a dashed line for a typical day. The three support bars share one scale.
5. **Unit strain, Now.** Titled "Unit now · life support running at 07:00": "N patients on life support now", tonight's staffing and ventilators free when set, the capacity form, and a card per support with "N on now" and the solid figures of those beds. No expected numbers, bars, deaths line or leaving card.
6. **Room page** (`#room=N`; the browser's back button returns to the board). Back link, the time switch, previous and next room; one sub-line with the mode and the window ("Forecast for the next 24 h · 07:00 to 07:00 tomorrow · updated 07:00", from the room's own `window` and `updated_at`).
   - **Next 24 h**: the heading "Room 12 · James Rivera · M 68", its trajectory status chip and the same NOW / NEXT 24 H strip with names. Then "Five predictions for this patient · chance in the next 24 h", each named in full: "Starts a ventilator (IMV)", "Starts a vasopressor", "Starts CRRT", "Leaves the ICU (ward or step-down)", "Dies in hospital". Each row is an icon, a level word in its level tint (High 40% or more, Medium 20 to 39%, Low under 20%), a 10-dot array as the picture, and the percentage. A support running now has the solid icon and reads "On now"; a probability that is `null` while the support is not on reads "No estimate", never Low. A faint note per stopped support: "Ventilator: off (stopped before 07:00)".
   - **Now**: the same heading and a list of the three supports, each "On now" or "Not running". No status, strip or predictions.
   - "Last 12 hours" (five, then "Show more"; `h` is hours before the cut) and the buttons **Update this room** and **Ask about this forecast**, in both modes. Focus moves to the heading on open (programmatic, no visible ring) and back to the room's tile or figure on return.
7. **Update flows**. "Update the unit" and "Update this room" send `POST /api/rerun`. While running the button reads "Updating…" (aria-disabled, focus stays), an "updating" tag marks the numbers, and the last forecast stays visible. The numbers refresh in place when the run lands. A refusal shows verbatim in the run line (or the room's status line).
8. **Ask Lookahead** (chat widget). A launcher at the bottom right: a 52px circle with the chat icon, accessible name "Ask Lookahead", legend "Ask about the unit or a room", 24px from the edges (above the safe area on a phone). The page keeps bottom space so the launcher never sits on a tile or the disclosure when scrolled to the end. A small dot marks it when the forecast has changed since the chat was last open.
   - The panel opens above the launcher (about 400 by 600, at most 80% of the height; a bottom sheet at 85% of the height at 600px and below, riding above the keyboard). It is a non-modal `role="dialog"`: the board stays usable, and tab order is not trapped.
   - Header: "Ask Lookahead", a context chip ("Unit" on the board, "Room 12" on a room page; it follows navigation and, on a room page, switches between that room and the unit), minimise and close (44px). Minimise and Escape keep the conversation and the draft and return focus to the launcher; close clears them. Open or closed is remembered (`lookahead-chat`); messages and the draft last for the session, across tabs and rooms.
   - Empty state: suggested questions that follow the context, no welcome text. Unit: "Who should we worry about first?", "How many ventilators will we need?", "Who is likely to leave today?", "Summarise the next 24 hours". Room: "Why is this room Worsening?" (the room's own status), "What changed in the last 12 hours?", "Chance of leaving the ICU?".
   - Conversation: the team's questions right, Lookahead left; numbers in answers are bold and room numbers are links (44px hit area) that open the room with the panel still open; a room may be followed by its name, "room 20 (Rivera, J.)". Every rendered piece is escaped. "Thinking…" with a Stop button; "Can't reach the chat right now. Try again." when the server does not answer; "Forecast updated 08:10. Answers below use it." when the forecast changes mid-conversation.
   - Input: one line that grows to four; Enter sends, Shift+Enter adds a line; a 44px send button, disabled when empty; placeholder "Ask about the unit or a room". Treatment questions are declined. `POST /api/ask` is unchanged (`room` is the chip's room, `seen_made_at` as before).
9. **Figure legends (tooltips)**. One floating element (`role="tooltip"`, linked with `aria-describedby`) explains any icon, status mark, figure, bar, chip or number: on hover (150 ms), on keyboard focus (a tile describes its status), and on touch by a tap on a label, bar or chip or a long-press inside a tile or link (which does not open the room). Escape, a tap elsewhere or scrolling dismisses it. It is placed above or below its target and kept on screen; text only, at most two short lines. Hovering a tile does not describe the whole tile, only the element under the pointer. The wording comes from one map of definitions in the page (`DEF`), which also builds the key and the status lines in "How this forecast was made", so they cannot drift. Examples: "Ventilator running at 07:00"; "43% chance of starting a vasopressor in the next 24 h"; "Worsening: new life support 40% or more"; "Room 20 · 40% chance of starting a ventilator"; "Expected new starts: 2, likely range 1 to 4 (8 in 10 outcomes)"; "TIGHT: expected need is close to what is free"; "MIMIC-IV Demo: open demo patients".
10. **How this forecast was made** (foot): one folded disclosure. Its first line names the five predictions. Then each bed, the flag line, bed status, Not improving, the icons, the range bar and status words, the table of the five forecasts, model, method, where and when, "Excludes new admissions from the ED and OR.", a "Model performance (held-out patients)" row only once numbers exist, "For unit planning; the care team makes clinical decisions." and a credits line for Dema (deetherese).

### Icons

One family drawn for this board, inline as an SVG sprite (24 grid, `currentColor`, 1.75 stroke). Solid means running now, outline means expected. Ventilator: lungs with an airway tube and circuit. Vasopressor: a syringe with a drop. CRRT: a capped filter with blood lines and arrows. A plus in a ring: any new support. Leaving: a bed with an outward arrow. Where an icon stands alone it has an accessible name ("Ventilator running", "Vasopressor expected"); inside a tile the tile's own label says it in words. Sheet: [`screenshots/icons.png`](screenshots/icons.png).

## Cognitive load

The board is read at 07:00 by a tired team at a workstation or a wall screen, often mid-conversation and from a few metres. Target: "who do we worry about?" is answered in two seconds from the Worry first rail, and "are we covered?" from the header line; neither needs scrolling at 1440 px. Phone order: header, tabs and the time switch (sticky), Worry first, all rooms (two across), footer.

| What we surface | Rule | Why it lowers load |
|---|---|---|
| Who to worry about, first | The Worry first rail leads the default tab: Worsening, then Not improving. | Attention goes to a few rooms before anything else. |
| Now, then next | Every bed reads left to right: what is running, an arrow, what may start. | A change is seen as a change, not worked out from two numbers. |
| Pictures before words | One icon per support, solid for running, outline for expected; a tile carries one status word. | Read from across the room and by people who do not share a first language. |
| One status per bed | Worsening, Watch, Not improving, Leaving or Steady, by fill or border, shape and word. | No tile needs decoding. |
| The team sets the line | "Flag beds at 50% · 25% · 10%" changes which beds are flagged, never where they are. | Sensitivity is a choice the team makes, visibly, in one place. |
| Ink is now, blue is forecast | On every screen. Amber and red appear only on TIGHT / BUSY and SHORT / VERY BUSY. | Colour means one thing. |
| Strain on its own tab | The header keeps one line and one word; the counts, bars and capacity form live on Unit strain. | The bed board stays a bed board. |
| One yardstick, named | A chip with a word, and a name ("vs tonight's staffing" or "vs a typical day"). | Nobody guesses what "busy" is measured against. |
| Each role's card first | The role picker moves that team's card to the front of Unit strain. | Each team reads one card. |
| Percentages, one way | "23%" everywhere, "<5%" when very small; the room page keeps a 10-dot array as the picture. | One number format on every screen (J.C., 2026-11-14 evening). |
| Now, then the forecast | A Now / Next 24 h switch: Now is ink and shows only what is running; Next 24 h is blue. | Current sickness can be read without any forecast in the way. |
| Named, not implied | NOW and NEXT 24 H captions on every tile, a sub-heading that says what is forecast, and a legend on hover, focus or long-press. | A newcomer can tell what each figure is. |
| Fixed room page | New life support, Leaving the ICU, Death, always in this order. | The attending knows where to look. |
| Chat out of the way | A launcher at the bottom right; the panel is non-modal and keeps its conversation. | The board stays a board. |
| One horizon | Next 24 h, 07:00 to 07:00. No time slider; the switch only hides or shows the forecast. | Nothing to choose before reading. |
| Definitions folded | Every rule and the model details sit in one closed section at the foot. | The curious can look; the 07:00 reader never has to. |
| Day and night boards | Same layout and words; the user picks the board. | Nothing moves when the lights go down. |

## Forecast not ready (`forecast_state: "pending-model"`)

Both files may carry `"forecast_state": "pending-model"` (see the backend's `docs/CONTRACT.md`): there are no model weights or probes yet. Every room's `p` is null, the unit's expected counts are null with `available: false`, there is no yardstick, and the Now side (`on_now`, names, age and sex, `life_support.now_patients` and `now_by`) is real. A missing key or `"ready"` behaves as before.

- The page never prints "null", "NaN" or "undefined": every forecast number is checked before it is drawn, and in this state none is drawn.
- The time switch opens on **Now** (not saved). Choosing Next 24 h shows one calm line, "Forecast not ready yet: the model is still being prepared.", above the same Now content.
- No status is computed (no Worsening or Watch); "Worry first" is replaced by "Sickest now"; the "Flag beds at" control is disabled.
- The header strain line reads "N on life support now" only; the run line reads "Now as of 07:00 · forecast not ready yet".
- Unit strain shows the on-now counts, the figures of those beds and the capacity form; no expected numbers, bars or deaths line.
- The room page shows what is running and the last 12 hours, with "Forecast not ready yet" in place of the five predictions.
- The chat answers Now questions ("Who is sickest now?", "How many are on a ventilator now?"); forecast questions get the same line and the Now counts.
- Review flag `#pending` puts the built-in synthetic data in this state.

## States the frontend must handle

| State | Show |
|---|---|
| No forecast yet | "No forecast yet" on the Unit strain tab, no header strain line, a dash in the footer table, "No rooms yet" on the Bed board, and the update control |
| Forecast older than 24 h | the age and an update prompt |
| Run in progress (button, chat or scheduled) | "Updating…", an "updating" tag, the last forecast kept |
| Update refused | the server's reason, verbatim ("Updated 12 minutes ago. You can update again at 13:17.") |
| Capacity refused | the server's reason in the form |
| Chat not answering | "Can't reach the chat right now. Try again." |
| API unreachable (at load or later) | "Can't reach the board server — retrying", retry with backoff, last good data kept; synthetic only for `file://` or `#synthetic` |
| A room missing from `rooms.json` | no tile and no room page; deep link goes to the board |
| A room missing from `rooms.json` (link or hash) | "Room N is not in this forecast." on the board |
| Support already running | its solid icon left of the arrow; "On now" on the room page (never a number) |

## Rules

- **Counts only for real MIMIC-IV.** Room-level views and room chat only for the stage ward (open MIMIC-IV Demo patients, excluded from training). Never log questions.
- **Every number has its range**, written "(a to b)" and explained once as 8 in 10 likely outcomes. Chances are whole percentages ("23%", "<5%", "No estimate"); clinical history values in the last 12 h list are shown as recorded.
- **Status never by colour alone**; text at 4.5:1 or better in day and night.
- **Honest labels, no warnings**: a plain data-source tag ("Demo data", "MIMIC-IV Demo", "MIMIC-IV · local"), "Not ready yet" only as a standalone state where no run has produced a number, and no hedging copy; admissions are excluded from the forecast and the footer says so once.
- **Decision support, never a treatment recommendation.**
- **Design**: follow [`../DESIGN.md`](../DESIGN.md) (the picture board: ink is now, blue is forecast). Use the Impeccable skill (`/impeccable`) for any UI work.

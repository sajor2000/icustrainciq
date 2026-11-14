# Frontend spec: Lookahead, the ICU board

Lookahead ("The next 24 hours, in one place.") is the ICU team's board for 07:00 morning rounds. The unit name stays the big title. The backend (forecaster, workflows, dispatcher, `app/board.py`) lives in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin); this repo holds the frontend design, the mockup, and the contract it must meet. Journeys: [`USER_JOURNEY.md`](USER_JOURNEY.md). Decisions: [`DECISIONS.md`](DECISIONS.md). Words: [`NAMING_AND_WORDING.md`](NAMING_AND_WORDING.md). Visual system: [`../DESIGN.md`](../DESIGN.md).

## How it runs

- Static HTML, CSS and vanilla JavaScript in one file; no build step, no Node in the image, works offline.
- Served by `app/board.py` (as `app/static/index.html`) on the team's two NVIDIA GB10 nodes. Served over http(s), the page reads the same-origin API below. Only when opened from `file://`, or with `#synthetic`, does it use its built-in synthetic generator, labelled "Demo data". A transient load failure over http(s) never switches a live board to synthetic data: the page retries (3 tries with backoff, then every few seconds), shows "Can't reach the board server — retrying" and keeps the last good data. The data-source label (a small outlined tag in the top strip, not a warning) reads "MIMIC-IV Demo" (`ward.source` `open-demo`, the default), "MIMIC-IV · local" (`mimic-iv`, real MIMIC-IV room views approved for local use) or "Demo data" (synthetic). `forecast.json` and `rooms.json` carry `"ward": {"source": "open-demo"|"mimic-iv", "label": "..."}`.
- Every server-supplied string reaches the page through one `esc()` helper or `textContent`; numbers are checked with `Number.isFinite`; `level`, `sex`, `age` and yardstick words are checked against fixed sets. The page loads no third-party scripts (CSP: self and Google Fonts only).
- Every POST (`/api/rerun`, `/api/capacity`, `/api/ask`) is same origin with `Content-Type: application/json` and `X-Lookahead: 1`; a refusal such as `403 {"ok":false,"reason":"request refused"}` shows its reason.
- Review flags in the URL hash: `#view=beds`, `#view=strain`, `#night`, `#room=7`, `#role=pharmacy`, `#fast` (short polls and runs), `#morning` (the scheduled run in progress, fallback only), `#synthetic`.

## What the board predicts

Five predictions only, all for the next 24 h, 07:00 to 07:00: ICU discharge, IMV, vasopressor, CRRT, death. No hypotension, no readmission, nothing else.

**Life support** means IMV (breathing tube or tracheostomy), a vasopressor infusion (inotropes alone do not count) or CRRT. **Now** means running at the 07:00 cut (decided 2026-11-14, Q29/Q30). ECMO and other mechanical support are not in the data and are not shown anywhere on the board.

## Data the board reads

| Source | What | Who writes it |
|---|---|---|
| `GET /api/forecast` | `forecast.json`; example [`../examples/forecast.json`](../examples/forecast.json). Before the first run: `{"resources":{},"note":"no forecast yet: the 07:00 run has not finished"}` | `app/aggregate.py` after each `t7-forecast` run |
| `GET /api/rooms` | `rooms.json`, stage ward only; example [`../examples/rooms.json`](../examples/rooms.json). Before the first run: `{"rooms":[],"note":"pending run"}` (not shown; the board says "No rooms yet") | lane 3, open MIMIC-IV Demo patients only (D6) |
| `GET /api/runs` | `{next_scheduled, window, running: null / {name} / {unknown:true}, updating, last:{unit,room}, recent, demo_clock_hours, demo_clock_label, min_gap_minutes}`, or `{available:false, reason}` | `app/dispatcher.py` |
| `GET /api/capacity` | `{life_support_patients, vents_free, updated_at}` | board server |

### forecast.json

```json
{ "made_at": "ISO", "cut_time": "ISO", "window": {"start": "ISO", "end": "ISO"}, "scope": "unit",
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
    "on_now": {"imv": false, "vasopressor": false, "crrt": false, "ecmo": null},
    "on_life_support": false,
    "stopped_before_cut": {"imv": false, "vasopressor": false, "crrt": false},
    "p": {"imv": 0.06, "vasopressor": 0.15, "crrt": null, "icu_departure": 0.32, "death": 0.06},
    "any_life_support": 0.26, "level": "low|medium|high", "out": false,
    "past_12h": [{"h": -1, "text": "Lactate 3.1 (up from 2.2)"}] } ] }
```

`null` in `p` means the support is already running (shown as "on now", never forecast as new). `on_life_support` is true when two or more supports are running. `stopped_before_cut` marks supports switched off before 07:00 (room page note only). `any_life_support` is the chance of any new IMV, vasopressor or CRRT, skipping supports already on. `level` is High at 0.4 or more, Medium at 0.2 or more, else Low. `out` is true when `icu_departure` is 0.6 or more. Death never sets the level.

## Actions the board sends

| Action | Request | Response |
|---|---|---|
| Update the unit or one room | `POST /api/rerun {"role": "ICU nurse", "scope": "unit"}` or `{"scope": "room", "room": 12}` | `{"started": true, "workflow", "name", "scope", "room", "demo_clock_hours", "demo_clock_label"}` or `{"started": false, "reason": "..."}` (HTTP 200; the reason is shown verbatim, for example "Updated 12 minutes ago. You can update again at 13:17.") |
| Set tonight's capacity | `POST /api/capacity {"life_support_patients": 0..50, "vents_free": 0..50, "role": "ICU nurse"}` (`vents_free` optional) | `200 {"ok": true, "capacity": {...}}` or `400 {"ok": false, "reason": "..."}` (shown) |
| Ask the chat | `POST /api/ask {"question", "role", "room"?, "seen_made_at"?}` | `{"answer", "made_at", "trace"?}`; the board sends back the last `made_at` it received, and the server adds "Forecast updated at HH:MM. Answers below use it." when it changed |

Roles accepted: `ICU nurse`, `ICU physician`, `pharmacy`, `respiratory therapy`, `bed manager`. The board never sends or stores names. The chat can start "update room 12" or "update the unit" only when the user asks in those words; chips never start an update.

Polling: `/api/runs` every 30 s while a run is going or updating, every 5 min otherwise. When `made_at` (or the last room run) changes, reload `/api/forecast` and `/api/rooms` and refresh the numbers in place; keyboard focus does not move. The demo-clock line uses `demo_clock_label` from `/api/runs` verbatim (for example "Ward clock 11:30 (07:00 + 4.5 h)"); the offline fallback writes "Demo clock: recorded patients, time advanced N h".

## Screens and what each must do

The board has two tabs under the header, **Bed board** (default) and **Unit strain**, a segmented control. The tab is in the hash (`#view=beds` or `#view=strain`) and remembered in `localStorage` (`lookahead-view`, inside try/catch). The tab bar stays at the top of the screen while scrolling.

1. **Header** (slim): unit name (the big title) and bed count; "Lookahead", "07:00 to 07:00", the data-source tag ("MIMIC-IV Demo", "MIMIC-IV · local" or, for the file:// fallback, "Demo data") and the run line ("Updated 13:05", or "Updating the unit for ICU nurse (charge). The last forecast stays on screen."); a one-line strain summary that links to the Unit strain tab ("10 on life support · +5 expected · USUAL"); Night board / Day board; role picker ("I am"); **Update the unit**; **Ask**. On a phone the night and ask buttons are icons beside the title.
2. **Bed board tab.** Current state, then the forecast, per bed.
   - **Bed tile**: room number, sex and age ("F 67"), one trajectory status, then a strip that reads left to right as a change: **Now** (solid icons for life support running at 07:00, or a thin ring for none), an arrow, **Next 24 h** (an outline icon for each new support at 2 in 10 or more with "3 in 10" beside it; the bed-with-arrow icon when leaving the ICU is 6 in 10 or more; a dash when nothing new is flagged). The bed-with-arrow carries its own chance ("7 in 10"). When the room's level is Medium or High but no single support reaches 2 in 10, a plus in a ring carries the combined chance ("3 in 10"). A bed with nothing running and nothing flagged shows no strip.
   - **Trajectory status**, one per bed, by fill or border, a shape and a word:

     | Status | Rule | Look |
     |---|---|---|
     | Worsening | `level` is `high` (any new life support 4 in 10 or more) | full blue tile, solid triangle |
     | Watch | `level` is `medium` (2 in 10 or more) | light blue tile, outline triangle |
     | Not improving | on at least one life support now, `p.icu_departure` under 0.2, and no new support flagged | tinted ground, 3px ink border, two bars |
     | Leaving | `out` is true (leaving 6 in 10 or more) | white tile, 2px green border, bed with arrow |
     | Steady | everything else | white tile, dot |

     The rules are checked in that order. Death never enters. **Not improving is derived on the page** from the five predictions: there is no coming-off-support forecast, so "on support and unlikely to leave" stands in for lack of improvement. Nothing new is read from the API; `any_life_support` is recomputed from `p` for ordering.
   - **Worry first** (top of the tab, tiles on the board ground): the Worsening rooms (highest combined chance first), then the Not improving rooms (most supports running first, then lowest chance of leaving), each a full bed tile. "No room is worsening or not improving." when both are empty. It replaces the old "Check first" line. The offline chat answers "Worry first" from the same lists; the live chat answers from the server.
   - **All N rooms**: every room in room order, five across on a desktop, two on a phone. A tile opens the room page.
   - **Key** (one line beside the tabs): the four marked statuses, then solid icons "on now", an arrow, outline icons "may start", and the plus in a ring "any of them".
3. **Unit strain tab.**
   - **Life support** lead: the yardstick word as a chip with its name ("vs tonight's staffing" or "vs a typical day"), "10 patients on now", "+5 expected" with its range, a range bar of now plus new, and one line ("Now plus new 15 (13 to 18) · typical day 15" or "· staffing covers 14"). The chip is green-outlined for ON TRACK / USUAL, amber for TIGHT / BUSY, solid red for SHORT / VERY BUSY; the card takes an amber or red border to match. "Not ready yet" when `yardstick` is null.
     - Capacity set (server rule, `docs/CONTRACT.md`): ON TRACK when p90 <= capacity; TIGHT when p90 > capacity >= p50; SHORT when p50 > capacity.
     - No capacity: USUAL, BUSY, VERY BUSY against a typical day (from training data).
   - "Deaths expected 1 (0 to 3)", one quiet line.
   - **Set tonight's capacity** (folded; two 44px number inputs: "Life-support patients tonight's staffing covers", "Ventilators free (optional)"; whole numbers 0 to 50). After saving: "Capacity set 07:12 by ICU nurse (charge)" (the server's `set_at`), and the yardstick is recomputed locally with the server's rule until the next forecast. "View against a typical day" is a view toggle on this screen only; the saved number is not cleared. It shows only when a typical-day number exists.
   - **One card per support** (IMV, Vasopressor, CRRT) and one for **Leaving the ICU**; the role's card comes first (pharmacy: vasopressor; respiratory therapy: IMV; bed manager: leaving). Each: the icon and name, "N on now", "+N expected" with its range, a range bar, then the beds behind the count as person figures: "On now" (solid ink figures) and "May start" (figures that fill with the chance, 2 in 10 or more, highest first, with "3 in 10" under the room number). Leaving: "N expected to leave", the bar, and "Likely to leave" figures (6 in 10 or more, green fill). A figure opens the room page.
   - With "ventilators free" saved, the IMV card also shows "N free", an ink line on its bar, and its own ON TRACK / TIGHT / SHORT chip (the server's capacity rule applied on the page to IMV starts against ventilators free); TIGHT gives the card an amber border, SHORT a red one. The unit yardstick word is not changed by it.
   - **Range bar**: track, the 8-in-10 range in blue, a bead at the median, a solid ink line for what is free or covered, a dashed line for a typical day. The three support bars share one scale.
4. **Room page** (`#room=N`; the browser's back button returns to the board). "← All N rooms" (or "← Unit strain" when opened from that tab), previous and next room (rooms missing from the file are skipped); the heading "Room 12", its trajectory status chip, and the same Now → Next 24 h strip, labelled; one sub-line with sex, age and the window ("male, age 68 · 07:00 to 07:00 tomorrow · updated 07:00", from the room's own `window` and `updated_at`). The header keeps the unit strain line. Each row is an icon, a level word in its level tint, a 10-dot icon array and "about N in 10" (the room page keeps "about"; tiles and figures drop it for space):
   - **New life support**: IMV, Vasopressor, CRRT. A support running now has the solid icon and reads "On now" with no dots; a probability that is `null` while the support is not on (or a missing key) reads "No estimate" with no dots, never Low. A faint note per stopped support: "Ventilator: off (stopped before 07:00)".
   - **Leaving the ICU** (solid bed icon when `out`) and **Death**, two rows under the supports.
   - "Last 12 hours" (five, then "Show more"; `h` is hours before the cut, 1 = the last hour); buttons **Update this room** and **Ask about this forecast**. Focus moves to the heading on open (programmatic, no visible ring) and back to the room's tile or figure on return.
5. **Update flows**. "Update the unit" and "Update this room" send `POST /api/rerun`. While running the button reads "Updating…" (aria-disabled, focus stays), an "updating" tag marks the numbers, and the last forecast stays visible. The numbers refresh in place when the run lands. A refusal shows verbatim in the run line (or the room's status line).
6. **Ask about this forecast**. Opened by **Ask** in the header (never a floating button over content). From 1200 px it docks as a right-hand panel and the board reflows beside it; below that it is a panel at the bottom right, and on a phone a bottom sheet. Chips by role (at most three, always including "Summarise the shift"; on a room page the first is "Room N: what is most likely in the next 24 hours?"). Ask again, Close and Escape close it and return focus to the button. It clears on a room or role change. When the forecast changes while it is open and has messages, one quiet line: "Forecast updated at 13:05. Answers below use it." Treatment questions are declined.
7. **How this forecast was made** (foot): one folded disclosure. It holds every definition (each bed, Worsening and Watch, Not improving, Leaving and Steady, the icons, the range bar, the status words), the table of the five forecasts, model, method, where and when, "Excludes new admissions from the ED and OR.", a "Model performance (held-out patients)" row only once numbers exist, and "For unit planning; the care team makes clinical decisions."

### Icons

One family drawn for this board, inline as an SVG sprite (24 grid, `currentColor`, 1.75 stroke). Solid means running now, outline means expected. Ventilator: lungs with an airway tube and circuit. Vasopressor: a syringe with a drop. CRRT: a capped filter with blood lines and arrows. A plus in a ring: any new support. Leaving: a bed with an outward arrow. Where an icon stands alone it has an accessible name ("Ventilator running", "Vasopressor expected"); inside a tile the tile's own label says it in words. Sheet: [`screenshots/icons.png`](screenshots/icons.png).

## Cognitive load

The board is read at 07:00 by a tired team at a workstation or a wall screen, often mid-conversation and from a few metres. Target: "who do we worry about?" is answered in two seconds from the Worry first rail, and "are we covered?" from the header line; neither needs scrolling at 1440 px. Phone order: header, tabs, Worry first, all rooms (two across), footer.

| What we surface | Rule | Why it lowers load |
|---|---|---|
| Who to worry about, first | The Worry first rail leads the default tab: Worsening, then Not improving. | Attention goes to a few rooms before anything else. |
| Now, then next | Every bed reads left to right: what is running, an arrow, what may start. | A change is seen as a change, not worked out from two numbers. |
| Pictures before words | One icon per support, solid for running, outline for expected; a tile carries one status word. | Read from across the room and by people who do not share a first language. |
| One status per bed | Worsening, Watch, Not improving, Leaving or Steady, by fill or border, shape and word. | No tile needs decoding. |
| Ink is now, blue is forecast | On every screen. Amber and red appear only on TIGHT / BUSY and SHORT / VERY BUSY. | Colour means one thing. |
| Strain on its own tab | The header keeps one line and one word; the counts, bars and capacity form live on Unit strain. | The bed board stays a bed board. |
| One yardstick, named | A chip with a word, and a name ("vs tonight's staffing" or "vs a typical day"). | Nobody guesses what "busy" is measured against. |
| Each role's card first | The role picker moves that team's card to the front of Unit strain. | Each team reads one card. |
| Natural frequencies | "3 in 10" on tiles and figures, "about 3 in 10" with a 10-dot array on the room page; no percentages. | Plain numbers are read the same by everyone. |
| Fixed room page | New life support, Leaving the ICU, Death, always in this order. | The attending knows where to look. |
| Chat out of the way | Closed until asked; docked beside the board, never over it. | The board stays a board. |
| One horizon | Next 24 h, 07:00 to 07:00. No time slider. | Nothing to choose before reading. |
| Definitions folded | Every rule and the model details sit in one closed section at the foot. | The curious can look; the 07:00 reader never has to. |
| Day and night boards | Same layout and words; the user picks the board. | Nothing moves when the lights go down. |

## States the frontend must handle

| State | Show |
|---|---|
| No forecast yet | "No forecast yet" on the Unit strain tab, no header strain line, a dash in the footer table, "No rooms yet" on the Bed board, and the update control |
| Forecast older than 24 h | the age and an update prompt |
| Run in progress (button, chat or scheduled) | "Updating…", an "updating" tag, the last forecast kept |
| Update refused | the server's reason, verbatim ("Updated 12 minutes ago. You can update again at 13:17.") |
| Capacity refused | the server's reason in the form |
| Chat model not up | "Lookahead is not answering yet. The rest of the board works." |
| API unreachable (at load or later) | "Can't reach the board server — retrying", retry with backoff, last good data kept; synthetic only for `file://` or `#synthetic` |
| A room missing from `rooms.json` | no tile and no room page; deep link goes to the board |
| A room missing from `rooms.json` (link or hash) | "Room N is not in this forecast." on the board |
| Support already running | its solid icon left of the arrow; "On now" on the room page (never a number) |

## Rules

- **Counts only for real MIMIC-IV.** Room-level views and room chat only for the stage ward (open MIMIC-IV Demo patients, excluded from training). Never log questions.
- **Every number has its range**, written "(a to b)" and explained once as 8 in 10 likely outcomes. No percentage appears on screen except clinical history values in the last 12 h list.
- **Status never by colour alone**; text at 4.5:1 or better in day and night.
- **Honest labels, no warnings**: a plain data-source tag ("Demo data", "MIMIC-IV Demo", "MIMIC-IV · local"), "Not ready yet" only as a standalone state where no run has produced a number, and no hedging copy; admissions are excluded from the forecast and the footer says so once.
- **Decision support, never a treatment recommendation.**
- **Design**: follow [`../DESIGN.md`](../DESIGN.md) (the picture board: ink is now, blue is forecast). Use the Impeccable skill (`/impeccable`) for any UI work.

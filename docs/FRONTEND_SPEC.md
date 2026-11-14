# Frontend spec: Lookahead, the ICU board

Lookahead ("The next 24 hours, in one place.") is the ICU team's board for 07:00 morning rounds. The unit name stays the big title. The backend (forecaster, workflows, dispatcher, `app/board.py`) lives in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin); this repo holds the frontend design, the mockup, and the contract it must meet. Journeys: [`USER_JOURNEY.md`](USER_JOURNEY.md). Decisions: [`DECISIONS.md`](DECISIONS.md). Words: [`NAMING_AND_WORDING.md`](NAMING_AND_WORDING.md). Visual system: [`../DESIGN.md`](../DESIGN.md).

## How it runs

- Static HTML, CSS and vanilla JavaScript in one file; no build step, no Node in the image, works offline.
- Served by `app/board.py` (as `app/static/index.html`) on the team's two NVIDIA GB10 nodes. Served over http(s), the page reads the same-origin API below. Only when opened from `file://`, or with `#synthetic`, does it use its built-in synthetic generator, labelled "Demo data". A transient load failure over http(s) never switches a live board to synthetic data: the page retries (3 tries with backoff, then every few seconds), shows "Can't reach the board server — retrying" and keeps the last good data. The data-source label (a small outlined tag in the top strip, not a warning) reads "MIMIC-IV Demo" (`ward.source` `open-demo`, the default), "MIMIC-IV · local" (`mimic-iv`, real MIMIC-IV room views approved for local use) or "Demo data" (synthetic). `forecast.json` and `rooms.json` carry `"ward": {"source": "open-demo"|"mimic-iv", "label": "..."}`.
- Every server-supplied string reaches the page through one `esc()` helper or `textContent`; numbers are checked with `Number.isFinite`; `level`, `sex`, `age` and yardstick words are checked against fixed sets. The page loads no third-party scripts (CSP: self and Google Fonts only).
- Every POST (`/api/rerun`, `/api/capacity`, `/api/ask`) is same origin with `Content-Type: application/json` and `X-Lookahead: 1`; a refusal such as `403 {"ok":false,"reason":"request refused"}` shows its reason.
- Review flags in the URL hash: `#night`, `#room=7`, `#role=pharmacy`, `#fast` (short polls and runs), `#morning` (the scheduled run in progress, fallback only), `#synthetic`.

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

`now_patients` counts patients with IMV, a vasopressor infusion or CRRT running at the 07:00 cut. `check_first` is the High rooms by combined chance (`any_life_support`), at most three. The board reads only the keys above; anything else is ignored.

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

1. **Top strip**: unit name (the big title), "Lookahead · The next 24 hours, in one place. · 07:00 to 07:00 · patients in the ICU at least 24 h"; data-source tag ("MIMIC-IV Demo", "MIMIC-IV · local" or, for the file:// fallback, "Demo data"); Day/Night board switch; role picker ("I am"); **Update the unit**; the run line ("Updated 13:05 (unit) · demo clock +6 h", or "Updating the unit for ICU nurse (charge). The last forecast stays on screen."). A scheduled morning run shows the last forecast marked "updating" until it lands.
2. **Strain panel** (top of the right column; first on a phone). Headline "10 patients on life support now · 6 more expected (4 to 9)". Then three lines, IMV, Vasopressor, CRRT, each "5 on now · +3 expected (1 to 5)", the role's line first (pharmacy: vasopressor; respiratory therapy: IMV; bed manager: the discharge line). Then "expected to leave 10 (7 to 13)" and a small "Deaths expected: 1 (0 to 3)". The yardstick word sits beside the title with its name: "vs tonight's staffing" or "vs a typical day". It always renders white, amber or red with the word ("Not ready yet" when `yardstick` is null; the rest of the panel stays); the load it compares is now plus new life support, with its range.
   - Capacity set (server rule, `docs/CONTRACT.md`): ON TRACK when p90 <= capacity; TIGHT when p90 > capacity >= p50; SHORT when p50 > capacity. "Ventilators free" is saved and shown; it does not change the word.
   - No capacity: USUAL, BUSY, VERY BUSY against a typical day (from training data). The yardstick sentence appears only when there is a capacity or a typical-day number to compare with; it is omitted otherwise.
   - **Set tonight's capacity** (folded; two 44px number inputs: "Life-support patients tonight's staffing covers", "Ventilators free (optional)"; whole numbers 0 to 50). After saving the panel says "Capacity set 07:12 by ICU nurse (charge)" (the server's `set_at`) and the yardstick is recomputed locally with the server's rule until the next forecast. "View against a typical day (staffing number kept)" is a view toggle on this screen only; the saved number is not cleared (the server cannot clear it). It shows only when a typical-day number exists.
3. **Check first**: one line under the panel, "Check first: rooms 20, 12, 7", each a link; "no room is High" when none is. There is no shift brief.
4. **Room board** (left two-thirds; all 25 rooms on one screen). A tile shows the room number, one word, and tags:
   - Word: Low, Medium or High (the combined chance of any new life support in 24 h), or "On life support" when two or more supports are running now. The word is always shown.
   - Fill: Low white, Medium pale amber, High pale red; High has a 3px red border. "On life support" has a 3px dark-ink border and keeps the fill of its level. Night board has its own versions of the fills, text at 4.5:1 or better. No glyphs, no bars. Death never colours a tile.
   - Tags: V, P, C for supports running at 07:00; a green-outlined OUT when the chance of leaving the ICU is 6 in 10 or more. No ECMO tag.
   - A key and one note sit under the grid. A tile opens the room page.
5. **Room page** (`#room=N`; the browser's back button returns to the board). "← All N rooms" (N from `rooms.json`), previous and next room (rooms missing from the file are skipped); a unit context line ("Unit: 10 on life support now · 6 more expected (4 to 9) · BUSY vs a typical day"); the heading "Room 12: next 24 hours" with its level; its own timestamp line ("updated 13:05 · next 24 h to 13:05 tomorrow"). Fixed groups, each row a level word, a 10-dot icon array and "about N in 10":
   - **New life support**: IMV, Vasopressor, CRRT. A support running now reads "On now" with no dots; a probability that is `null` while the support is not on (or a missing key) reads "No estimate" with no dots, never Low. A faint note per stopped support: "Ventilator: off (stopped before 07:00)".
   - **Leaving the ICU**: ICU discharge (with the OUT tag when it applies).
   - **Death**.
   - "Last 12 hours" (five, then "Show more"; `h` is hours before the cut, 1 = the last hour); buttons **Update this room** and **Ask about this forecast**. Focus moves to the heading on open and back to the room's tile on return.
6. **Update flows**. "Update the unit" and "Update this room" send `POST /api/rerun`. While running the button reads "Updating…" (aria-disabled, focus stays), an "updating" tag marks the numbers, and the last forecast stays visible. The numbers refresh in place when the run lands. A refusal shows verbatim in the run line (or the room's status line).
7. **Ask about this forecast** (floating widget, closed by default). Chips by role (at most three, always including "Summarise the shift"; on a room page the first is "Room N: what is most likely in the next 24 hours?"). Close and Escape close it and return focus to the button. It clears on a room or role change. When the forecast changes while it is open and has messages, one quiet line: "Forecast updated at 13:05. Answers below use it." Treatment questions are declined.
8. **How this forecast was made** (foot): a plain line, then a folded "The five forecasts, and what each one means" (table, "Life support: IMV, vasopressor infusion or CRRT.", model, method, where and when, "Excludes new admissions from the ED and OR."; a "Model performance (held-out patients)" row appears only once numbers exist) and the intended-use line "For unit planning; the care team makes clinical decisions."

## Cognitive load

The board is read at 07:00 by a tired team at a workstation or a projector, often mid-conversation. Target: the shift question ("how much life support, and are we covered?") is answered within 10 seconds, without scrolling at 1440 px. Phone order: strain panel, check first, 25 rooms (5 columns), footer, floating chat.

| What we surface | Rule | Why it lowers load |
|---|---|---|
| The answer first | The strain panel is the top of the right column and first on a phone: one sentence of counts, one yardstick word. | The answer comes before the evidence. |
| One yardstick, named | White, amber or red with a word, and a name ("vs tonight's staffing" or "vs a typical day"). | Nobody guesses what "busy" is measured against. |
| Each role's line first | The role picker moves that team's line to the top of the breakdown. | Each team reads one line, not the whole unit. |
| Few tags, one word | A tile is the room number, one level word, and at most V P C OUT. | Twenty-five tiles read at a glance and from a distance. |
| Exceptions marked | The fill and a 3px border mark High; "Check first" names at most three rooms. | Attention goes to a few rooms. |
| Natural frequencies | "about 4 in 10" with a 10-dot array; no percentages anywhere on the board. | Plain numbers are read the same by everyone. |
| Fixed room page | New life support, Leaving the ICU, Death, always in this order. | The attending knows where to look. |
| Chat out of the way | Closed floating widget; opens on demand; clears on room or role change; updates only on an explicit ask. | The board stays a board. |
| One horizon | Next 24 h, 07:00 to 07:00. No tabs, no slider. | Nothing to choose before reading. |
| Model details folded | The five forecasts and the model details sit in one closed section at the foot. | The curious can look; the 07:00 reader never has to. |
| Day and night boards | Same layout and words; the user picks the board. | Nothing moves when the lights go down. |

## States the frontend must handle

| State | Show |
|---|---|
| No forecast yet | "No forecast yet. Updates start at 07:00." in the panel, a dash in the footer, "No rooms yet" in the grid, and the update control |
| Forecast older than 24 h | the age and an update prompt |
| Run in progress (button, chat or scheduled) | "Updating…", an "updating" tag, the last forecast kept |
| Update refused | the server's reason, verbatim ("Updated 12 minutes ago. You can update again at 13:17.") |
| Capacity refused | the server's reason in the form |
| Chat model not up | "Lookahead is not answering yet. The rest of the board works." |
| API unreachable (at load or later) | "Can't reach the board server — retrying", retry with backoff, last good data kept; synthetic only for `file://` or `#synthetic` |
| A room missing from `rooms.json` | no tile and no room page; deep link goes to the board |
| A room missing from `rooms.json` (link or hash) | "Room N is not in this forecast." on the board |
| Support already running | "On now" (never a number); two or more: "On life support" tile |

## Rules

- **Counts only for real MIMIC-IV.** Room-level views and room chat only for the stage ward (open MIMIC-IV Demo patients, excluded from training). Never log questions.
- **Every number has its range**, written "(a to b)" and explained once as 8 in 10 likely outcomes. No percentage appears on screen except clinical history values in the last 12 h list.
- **Status never by colour alone**; text at 4.5:1 or better in day and night.
- **Honest labels, no warnings**: a plain data-source tag ("Demo data", "MIMIC-IV Demo", "MIMIC-IV · local"), "Not ready yet" only as a standalone state where no run has produced a number, and no hedging copy; admissions are excluded from the forecast and the footer says so once.
- **Decision support, never a treatment recommendation.**
- **Design**: follow [`../DESIGN.md`](../DESIGN.md) (the unit whiteboard world). Use the Impeccable skill (`/impeccable`) for any UI work.

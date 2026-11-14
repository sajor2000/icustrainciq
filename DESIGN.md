---
name: Lookahead (ICU-Twin)
description: The unit whiteboard nurses already read, made to forecast the next 24 hours.
colors:
  board: "#F4F5F2"
  board-2: "#E9EBE6"
  surface: "#FFFFFF"
  ink: "#1E2A33"
  ink-2: "#4A5862"
  rule: "rgba(30,42,51,.12)"
  magnet: "#2F6FB0"
  magnet-ink: "#FFFFFF"
  focus: "#2F6FB0"
  selection: "rgba(47,111,176,.22)"
  level-low: "#FFFFFF"
  level-medium: "#FBE6BD"
  level-high: "#F8D0CB"
  status-ok: "#2E7D5B"
  status-tight: "#9A5410"
  status-short: "#B23A3A"
  night-board: "#1C2126"
  night-board-2: "#232A30"
  night-surface: "#252D34"
  night-ink: "#E8ECE6"
  night-ink-2: "#A9B4AE"
  night-rule: "rgba(232,236,230,.14)"
  night-magnet: "#7FB2E5"
  night-magnet-ink: "#10161B"
  night-focus: "#9CC6EE"
  night-selection: "rgba(127,178,229,.28)"
  night-level-low: "#252D34"
  night-level-medium: "#4D3E1B"
  night-level-high: "#552B29"
  night-status-ok: "#6CC59B"
  night-status-tight: "#E8A85C"
  night-status-short: "#EE8A80"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  numeral:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 800
    lineHeight: 1
    fontFeature: "\"tnum\" 1"
  room-heading:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "40px"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\" 1"
  check-line:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  line:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  tag:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.45
    letterSpacing: "0.04em"
    fontFeature: "\"tnum\" 1"
  room-number:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "26px"
    fontWeight: 800
    lineHeight: 1
    fontFeature: "\"tnum\" 1"
  body:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  body-sm:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  label:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 800
    lineHeight: 1.45
    letterSpacing: "0.05em"
    fontFeature: "\"tnum\" 1"
rounded:
  tag: "3px"
  badge: "4px"
  magnet: "6px"
  control: "8px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
components:
  magnet:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.magnet}"
    padding: "8px 10px"
    height: "92px"
  board-toggle:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "7px 12px"
  status-word:
    backgroundColor: "transparent"
    typography: "{typography.label}"
    rounded: "{rounded.badge}"
    padding: "3px 4px"
  status-on-track:
    textColor: "{colors.status-ok}"
  status-tight:
    textColor: "{colors.status-tight}"
  status-short:
    textColor: "{colors.status-short}"
  synthetic-badge:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.badge}"
    padding: "2px 6px"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  ask-input:
    backgroundColor: "{colors.board}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  ask-button:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.board}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  chat-question:
    backgroundColor: "{colors.board-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
  chat-answer:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 10px"
---

# Design System: Lookahead (ICU-Twin)

## Overview

**Creative North Star: "The Unit Whiteboard"**

The board is the whiteboard an ICU team already reads at shift change, made to forecast. An enamel-white ground carries marker-navy ink, rooms are flat magnets with ink borders. A magnet is white (Low), pale amber (Medium) or pale red with a thick border (High), always with its word. One blue (the magnet) draws the icon arrays on the room page. Everything else is ink, rules, and words. It refuses the KPI-tile dashboard and the departure board: no hero numbers floating in cards, no flipping split-flap rows.

Density is operational, and the answer comes first. The first viewport holds the strain panel (patients on life support now, more expected, and a one-word yardstick) and a "Check first" line in a ruled right column, and on the left all 25 rooms coded Low, Medium or High, so a charge nurse and an attending can answer "what will we be short of, when, and how sure are we" from across a room or on a projector. Numerals are large, tabular, and heavy; prose is short, plain, and honest about what is mock, synthetic, or not yet run.

A night board (charcoal ground, chalk ink) is the same grammar with lifted colours, chosen by the user, not by the OS.

**Key Characteristics:**
- Two boards, one grammar: day (`data-board="day"`) and night (`data-board="night"`) swap only custom-property values.
- Flat magnets with 1.5px ink borders (3px for High) and 6px corners; level shown by a pale fill, a border weight and a word. No glyphs, no signal bars.
- A ruled margin column: 2px ink rules separate regions, 12-14% ink rules separate rows.
- Every forecast number carries its range, written "(a to b)" and explained once as 8 in 10 likely outcomes; no percentages on screen.
- Honesty labels are part of the visual system, not footnotes.

## Colors

A near-monochrome board of ink on enamel, one working blue, and three status inks that are always paired with a word.

### Primary
- **Magnet Blue** (`magnet`; night `night-magnet`): the filled dots of the room page's icon arrays, and the day focus ring. It no longer shades tiles.

### Level
- **Level fills** (`level-low` white, `level-medium` pale amber, `level-high` pale red; night counterparts): the tile, the legend swatch, the room heading chip and the yardstick word share them. The same three fills mean ON TRACK / TIGHT / SHORT or USUAL / BUSY / VERY BUSY on the strain panel. Ink is picked in code for 4.5:1 on each fill.

### Status
- **On-Track Green** (`status-ok`), **Tight Amber** (`status-tight`), **Short Red** (`status-short`): ink for the status words ON TRACK / TIGHT / SHORT, outlined in the same colour. Each colour means its word and nothing else: red is SHORT only. The capacity line and the SYNTHETIC DATA badge are ink.

### Neutral
- **Enamel Board** (`board`): page ground; also the ground of the ask input.
- **Board Shadow** (`board-2`): hover fill for controls and the fill of the team's own chat messages.
- **Magnet Surface** (`surface`): the unshaded magnet face that magnet blue mixes into.
- **Marker Navy** (`ink`): text, magnet borders, 2px region rules, the median tick, the capacity line, the SYNTHETIC badge, the Ask button.
- **Faded Marker** (`ink-2`): secondary text, subtitles, ranges, timestamps, "not forecast" rows.
- **Rule** (`rule`): 1px row dividers, the range-bar track, quiet borders.
- **Night counterparts** (`night-*`): charcoal ground, chalk ink, lifted blue and status inks; `night-focus` is a lighter blue than the night magnet so the focus ring separates from selected fills.

### Named Rules
**The Level Rule.** Three fills only: white, pale amber, pale red. High also gets a 3px border in Short Red, so the level never rests on colour alone; the word is always shown. Death never colours a tile. No second accent is introduced.

**The Word Beside the Colour Rule.** Status is never colour alone. The yardstick word (ON TRACK, TIGHT, SHORT, or USUAL, BUSY, VERY BUSY) sits in a pale fill, with a 3px red border for the worst state, and the panel names what it is measured against ("vs tonight's staffing", "vs a typical day").

**The Readable Ink Rule.** Text ink must reach 4.5:1 against its own ground on both boards. Tile ink is chosen in code from the four board inks by contrast against the level fill, which must reach 4.5:1. Status inks are held to the same bar: day Tight Amber is #9A5410 (5.26:1 on the board; the earlier #B8661A measured 3.87:1 and was darkened).

## Typography

**Display Font:** none; the system has no display role.
**Body Font:** system UI stack (`system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`)
**Label/Mono Font:** same stack; tabular numerals everywhere (`font-variant-numeric: tabular-nums` on body).

**Character:** The marker on the board: one plain, legible family that varies only in weight and size, so counts line up in columns and read at distance.

### Hierarchy
- **Headline** (700, 24px, 1.1, -0.01em): the unit name in the top strip only.
- **Title** (700, 18px): panel headings (rooms, strain, chat). The open room heading is 40px/700 on desktop; group headings and team names sit at 14-15px.
- **Numeral** (800, 30px headline numbers, 18px in the breakdown lines): the strain panel's counts.
- **Room Number** (800, 26px, 1): the magnet's room number. Drops to 20px (11px level word and tags) under 560px.
- **Body** (400, 15px, 1.45): base text; row names at 14px/600, risk table at 14px.
- **Body small** (13px): subtitles, legend, magnet risk line (600), chips (600), event history.
- **Label** (800, 12px, 0.05em, uppercase): status words. Related uppercase labels: SYNTHETIC DATA (700, 12px, 0.06em) and tile tags V P C E and OUT (700, 11px, 0.04em). Plain 12px in Faded Marker carries ranges, captions, and notes.

### Named Rules
**The Tabular Rule.** Every numeral is tabular; counts, ranges, and percentages must align in columns without per-element overrides.

**The Weight Ladder Rule.** Hierarchy comes from weight (400, 600, 700, 800) and a short size ladder (11-28px), not from a second family.

## Layout

The page is a 1440px-max frame with 16px/24px/32px padding. A top strip (unit name as the big title, the line "Lookahead · The next 24 hours, in one place.", SYNTHETIC DATA badge, board toggle, role picker, "Update the unit", and the run line) closes with a 2px ink rule. Below it a two-column grid: the room board at `2fr` (sticky at 12px from the top; all 25 magnets in a 5-column grid with 12px gaps, then a tag key and one note) and the right column at `minmax(340px, 1fr)`, divided by a 2px ink rule with 24px gutters. The right column holds the strain panel (headline, breakdown lines, yardstick sentence, the folded "Set tonight's capacity" form) and the "Check first" line under it. A "How this forecast was made" footer closes the page behind a 2px rule.

The breakdown lines are a two-track grid (7.5rem label, flexible text) separated by 1px rules.

Rhythm runs on 4/8/12/16/24/32px; component interiors use 6px and 10px half-steps.

Responsive: under 960px the columns stack as strain panel, check first, 25 rooms, footer, with the floating chat button over all of it; the vertical rule becomes a horizontal one. Under 560px magnets shrink (6px gaps, 20px room numbers, 11px words and tags) and stay in 5 columns, and the chat panel spans the width and closes when the page changes.

**The Ruled Margin Rule.** Regions are separated by 2px ink rules; rows by 1px rules at 12% ink (14% at night). No cards, no panel backgrounds.

## Elevation & Depth

The board is flat. Depth is carried by ink rules and borders, not by panels. The single exception is the magnet, which carries a faint contact shadow so it reads as a physical piece on the board, and lifts 1px on hover.

### Shadow Vocabulary
- **Magnet contact** (`box-shadow: 0 1px 1px rgba(0,0,0,.18), 0 2px 4px rgba(0,0,0,.06)`): magnets only.

**The Flat Board Rule.** Only magnets and the two floating chat pieces (launcher and panel, which sit above the board) cast a shadow. Panels, controls and chat messages stay flat.

## Shapes

Corners are small and practical: 3px on magnet tags and legend swatches, 4px on status words and the synthetic badge, 6px on magnets, the close button and the focus ring, 8px on the toggle, the select, the ask input and button, and chat messages, and full pills only on suggested-question chips. Borders are 1.5px solid ink on anything interactive or board-like (magnets, toggle, select, chips, input), 1.5px currentColor on status words and tags, and 1.5px dashed ink on the SYNTHETIC badge.

## Components

### Magnet (room tile)
The signature piece: a flat tile with an ink border, the room number, the level word and tags. Nothing else.
- **Shape:** 6px corners, 1.5px ink border (3px Short Red for High, padding reduced to keep the size), min-height 96px.
- **Fill:** Low white, Medium pale amber, High pale red (see Level). Ink is the higher-contrast of the four board inks and must reach 4.5:1.
- **Level word:** always shown (14px/700): Low, Medium or High. Level is the combined chance of any new life support (IMV, vasopressor, CRRT; ones already on are skipped) in the next 24 hours: High at 4 in 10 or more, Medium at 2 in 10 or more. Death never colours a tile.
- **Tags** (bottom, 11px/700, 1.5px currentColor outline, 3px corners): V (IMV on now), P (vasopressor on now), C (CRRT on now), E (ECMO or MCS on now, not forecast), and OUT with a 2px green outline when the chance of leaving the ICU is 6 in 10 or more. The tile state comes from `rooms.json` (`on_now`, `level`, `out`), so a new state (for example a room already on two or more supports) is one more branch in `renderGrid`.
- **States:** hover lifts 1px; the accessible label spells level, supports on and OUT in words.
- **Legend:** three swatches (Low, Medium, High) and a tag key under the grid, plus one note that says how level is worked out.

### Strain panel
Top of the right column (first on a phone). Title "Strain · next 24 hours" (18px/700) and the yardstick word beside it with its name ("vs tonight's staffing" or "vs a typical day"). The headline is one sentence, "10 patients on life support now · 6 more expected (4 to 9)", with the counts at 30px/800. Under it three breakdown lines, IMV, Vasopressor, CRRT, each "5 on now · +3 expected (1 to 5)"; the signed-in role's line comes first (pharmacy: vasopressor; respiratory therapy: IMV; bed manager: the "Leaving" line). Then "Leaving: 10 expected to leave (7 to 12) · arrivals not forecast", a small ECMO line ("1 on now · not forecast") and a small "Deaths expected: 1 (0 to 3)". A 14px sentence shows the load (now plus new) against the yardstick, and one caption explains the range. While an update runs, a dashed "updating" tag sits beside the title and the last numbers stay.

### Yardstick word
13px/800 uppercase in a 1.5px ink outline on a level fill: white for ON TRACK or USUAL, pale amber for TIGHT or BUSY, pale red with a 3px red border for SHORT or VERY BUSY. With a capacity set (patients tonight's staffing covers, optional ventilators free): SHORT when the median of now-plus-new passes it, TIGHT when the range reaches it, else ON TRACK. Without one: compared with a typical day.

### Set tonight's capacity
A folded `details` (44px summary) under the panel with two number inputs (44px tall) and "Save capacity". Once saved the panel says "Capacity set 07:12 by ICU nurse (charge)" and a "Use a typical day" button appears. Mock: saved in this browser; the real board POSTs `/api/capacity`.

### Check first
One 16px line under the panel: "Check first: rooms 20, 12, 7", each number a link (underlined, 44px target). "Check first: no room is High." when none is.

### Room page
Its own view at `#room=N`: "← All 25 rooms" and previous / next links (44px targets), a unit-context line, the heading "Room 12: next 24 hours" with the level in a chip using the tile fills, the room's own timestamp line ("updated 13:05 · next 24 h to 13:05 tomorrow") and a status line for updates. Two columns behind a 2px ink rule. Left: three fixed groups, New life support (IMV, Vasopressor, CRRT, and ECMO "on now · not forecast"), Leaving the ICU (with the OUT tag), Death. Each row is a level word, a 10-dot icon array (12px dots; filled magnet, empty outlined in Faded Marker) and "about 4 in 10"; supports already running read "On now" with no dots. Right: "What the forecast read · last 12 h" (five, then "Show more"), the line "These are what the forecast read. They do not show why something happens.", and the buttons "Update this room" and "Ask about this forecast".

### Chat widget
A launcher pill "Ask about this forecast" (ink fill, board text, 48px tall) fixed bottom right; the panel (surface, 1.5px ink border, 8px corners, up to 72% of the viewport) opens above it with a heading, Close, chips, the log and the ask form. Closed by default; Escape and Close return focus to the launcher; on a phone it spans the width and closes when the page changes. When the forecast changes while it is open and has messages, one quiet 12px line says "Forecast updated at 13:05. Answers below use it."

### Suggested questions
Pill chips (1.5px ink border, 13px/600, 44px tall): at most three by role, always including "Summarise the shift"; with a room open the first chip asks about that room. No chip starts an update. Hover fills Board Shadow.

### Ask about this forecast (chat)
- **Messages:** 8px corners, 14px text, max 92% width; the team's questions right-aligned on Board Shadow, answers left-aligned with a 1.5px Rule border; a 12px/700 Faded Marker speaker line.
- **Input and button:** 44px tall, board ground and ink fill.
- **Actions:** only on an explicit ask ("update room 12", "update the unit") does the chat start an update; treatment questions are declined.

### Board toggle, role picker and update buttons
- **Board toggle:** 1.5px ink border, 8px corners, `aria-pressed`; the label names the board it switches to.
- **Role picker:** a native select ("I am ..."). It reorders the strain lines and picks the chips; it never stores a name.
- **Update the unit / Update this room:** the same outlined button. While running it reads "Updating…" and is `aria-disabled`; focus stays put. A refusal prints in the run line: "Updated 12 minutes ago. You can update again at 13:17."

### Run line and demo clock
13px under the top strip: "Updated 13:05 (unit) · demo clock +6 h". With a demo clock above zero, "Demo clock: recorded patients, time advanced 6 h" follows it.

### Footer: how this forecast was made
A plain line, then a folded "The five forecasts, and what each one means" (table of median with range and who uses it, the life-support definition, model, method, accuracy and run time, each "Not ready yet" until a run supplies it).

### Honesty labels
- **SYNTHETIC DATA:** a dashed ink badge in the top strip whenever numbers are made up (red stays reserved for the worst level).
- **(mock):** on drafted replies (Nemotron 3 Nano).
- **Not ready yet:** italic Faded Marker in place of any measured number that does not exist yet.
- **not forecast:** ECMO and arrivals.

### Focus
All focusable elements: 3px solid focus colour, 2px offset, 6px corners (`:focus-visible`).

## Do's and Don'ts

### Do:
- **Do** fill magnets only with the three level fills, always show the level word, and pick the ink by contrast so it reaches 4.5:1.
- **Do** pair every level or yardstick colour with its word, and name what the yardstick compares against.
- **Do** lead with the strain panel and the rooms to check first; the role's own line goes first.
- **Do** give every forecast number its range as "(a to b)", and say numbers as natural frequencies ("about 4 in 10").
- **Do** separate regions with 2px ink rules and rows with 1px Rule lines.
- **Do** label mock, synthetic, and missing numbers in place: SYNTHETIC DATA, (mock), Not ready yet, not forecast.
- **Do** keep both boards on the same custom properties; a new surface sets values for `data-board="day"` and `data-board="night"`.
- **Do** keep the 3px focus ring with 2px offset on every focusable element.

### Don't:
- **Don't** build KPI tiles or departure-board rows; counts live in the ruled strain panel.
- **Don't** use glyphs, signal bars or a watch list; the level word and fill carry the level.
- **Don't** forecast anything beyond the five predictions, and never colour a tile by death.
- **Don't** show percentages; use "about N in 10".
- **Don't** add horizon tabs, time sliders or probability tables: the board has one horizon, the next 24 h.
- **Don't** introduce a second accent colour or fill panels with colour.
- **Don't** convey status, risk, or capacity by colour alone.
- **Don't** add shadows to anything but magnets and the floating chat pieces.
- **Don't** show a measured number that does not come from a run; use "Not ready yet".

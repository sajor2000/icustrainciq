---
name: ICU-Twin
description: The unit whiteboard nurses already read, made to forecast.
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
    fontSize: "28px"
    fontWeight: 800
    lineHeight: 1
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

# Design System: ICU-Twin

## Overview

**Creative North Star: "The Unit Whiteboard"**

The board is the whiteboard an ICU team already reads at shift change, made to forecast. An enamel-white ground carries marker-navy ink, rooms are flat magnets with ink borders, and one blue (the magnet) means risk: magnet shading and range bars. Everything else is ink, rules, and words. It refuses the KPI-tile dashboard and the departure board: no hero numbers floating in cards, no flipping split-flap rows.

Density is operational, and the answer comes first. The first viewport holds a three-line shift brief (the verdict on top) and the six task rows in a ruled right column, and on the left the three highest-risk rooms as magnets with the full 25-room board one tap away ("Show all 25 rooms"), so a charge nurse and an attending can answer "what will we be short of, when, and how sure are we" from across a room or on a projector. Numerals are large, tabular, and heavy; prose is short, plain, and honest about what is mock, synthetic, or not yet run.

A night board (charcoal ground, chalk ink) is the same grammar with lifted colours, chosen by the user, not by the OS.

**Key Characteristics:**
- Two boards, one grammar: day (`data-board="day"`) and night (`data-board="night"`) swap only custom-property values.
- Flat magnets with 1.5px ink borders and 6px corners; risk shown by mixing magnet blue into the surface.
- A ruled margin column: 2px ink rules separate regions, 12-14% ink rules separate rows.
- Every forecast number carries its 80% range; status words appear only where a capacity is set.
- Honesty labels are part of the visual system, not footnotes.

## Colors

A near-monochrome board of ink on enamel, one working blue, and three status inks that are always paired with a word.

### Primary
- **Magnet Blue** (`magnet`; night `night-magnet`): the only chromatic fill. Shades magnets by risk, draws the 80% range bar and the room drawer's risk bars, and doubles as the day focus ring.

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
**The One Blue Rule.** Magnet blue is the only chromatic fill on the board. On tiles it marks the exception (the three watch-first rooms), not a risk gradient: bar length carries the size of each risk (colour is not ordered, NN/g; Few). Controls show selection with ink, not blue. No second accent is introduced.

**The Word Beside the Colour Rule.** Status is never colour alone. Every status colour appears as the ink of a word (ON TRACK, TIGHT, SHORT) with a matching outline, and the capacity line is an ink line explained in text ("ink line = what is free").

**The Readable Ink Rule.** Text ink must reach 4.5:1 against its own ground on both boards. Magnet ink is chosen in code from the four board inks by contrast, and the fill is nudged along the mix until the better ink reaches 4.5:1. Status inks are held to the same bar: day Tight Amber is #9A5410 (5.26:1 on the board; the earlier #B8661A measured 3.87:1 and was darkened).

## Typography

**Display Font:** none; the system has no display role.
**Body Font:** system UI stack (`system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`)
**Label/Mono Font:** same stack; tabular numerals everywhere (`font-variant-numeric: tabular-nums` on body).

**Character:** The marker on the board: one plain, legible family that varies only in weight and size, so counts line up in columns and read at distance.

### Hierarchy
- **Headline** (700, 24px, 1.1, -0.01em): the unit name in the top strip only.
- **Title** (700, 18px): panel headings (rooms, unit strain, brief, chat). The open room's heading steps up to 22px; drawer sub-headings and team names sit at 14-15px.
- **Numeral** (800, 28px, 1): the median count in each margin row, right-aligned. Drops to 22px under 420px.
- **Room Number** (800, 26px, 1): the magnet's room number. Drops to 20px under 560px.
- **Body** (400, 15px, 1.45): base text; row names at 14px/600, risk table at 14px.
- **Body small** (13px): subtitles, legend, magnet risk line (600), chips (600), event history.
- **Label** (800, 12px, 0.05em, uppercase): status words. Related uppercase labels: SYNTHETIC DATA (700, 12px, 0.06em) and magnet tags VENT / PRESS (700, 11px, 0.04em). Plain 12px in Faded Marker carries ranges, captions, and notes.

### Named Rules
**The Tabular Rule.** Every numeral is tabular; counts, ranges, and percentages must align in columns without per-element overrides.

**The Weight Ladder Rule.** Hierarchy comes from weight (400, 600, 700, 800) and a short size ladder (11-28px), not from a second family.

## Layout

The page is a 1440px-max frame with 16px/24px/32px padding. A top strip (unit name with the fixed horizon "next 24 h, 07:00 to 07:00", SYNTHETIC DATA badge, board toggle, role picker, Rerun, and the run line) closes with a 2px ink rule. Below it a two-column grid: the room board at `2fr` (sticky at 12px from the top; the three highest-risk rooms as larger magnets in a 3-column row, the full 5-column board under a "Show all 25 rooms" disclosure) and the right column at `minmax(340px, 1fr)`, divided by a 2px ink rule with 24px gutters either side. The right column opens with the three-line shift brief, then the unit rows, the room drawer when open, and the chat. The room board is a 5-column grid with 12px gaps. A run-details strip closes the page behind a 2px rule.

Inside the margin column, panels are separated by 1px rules with 14px/18px vertical padding. Each task row is a four-track grid: name and team (flexible), median numeral (44px), range bar with its range in words (flexible), status word (88px), separated by 1px rules. Rows without a verdict fold under a `details` summary that says why ("N more rows · 1 on track, 3 capacity not assessed").

Rhythm runs on 4/8/12/16/24/32px; component interiors use 6px and 10px half-steps (magnet tags, row padding).

Responsive: under 960px the columns stack in the order brief, unit rows, room drawer, board, chat (the verdict and each role's own row before the 25 magnets), the vertical rule becomes horizontal ones, and opening a room scrolls the drawer into view. Under 560px magnets shrink (68px, 6px gaps) and labels shorten (Vent, Press, V, P). Under 420px row tracks tighten to 96/36/flex/64px.

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
The signature piece: a flat tile with an ink border, the room number large, the top risk beneath.
- **Shape:** 6px corners, 1.5px ink border, min-height 92px, 8px/10px padding.
- **Fill:** magnet blue mixed into the surface by the room's highest risk in the next 24 h (leaving the ICU is not a risk) (6% at zero, full magnet at 45% or more). Ink is the higher-contrast of the four board inks; the mix moves until that ink reaches 4.5:1.
- **Content:** room number (26px/800), risk line (13px/600, event name + percent), and top-right VENT / PRESS / CRRT tags for tasks already on before 07:00 (V / P / C on a phone).
- **States:** hover lifts 1px; selected gets a 3px ink outline offset 2px; `aria-pressed` reflects selection; the accessible label spells the risk in words.
- **Legend:** three swatches (under 5%, about 1 in 4, 45% or more) above the grid, readable by screen readers; a note under the grid says what the shade and tags mean.

### Unit strain header
Top of the right column (first on a phone). Title "Unit strain · next 24 h" (18px/700) with the band word (QUIET / USUAL / BUSY / VERY BUSY) outlined, Tight Amber for the two busy bands, Faded Marker otherwise; the ratio as a 48px/800 numeral ("1.3×") beside "a typical day" (18px/600) and its 80% range; a scale of four bands on Rule tracks with a dashed "typical" mark, the range as a 10px magnet-blue stroke and the median as a 3px ink tick; one 14px line naming the tasks above their usual.

### Room tile (all 25 on one screen)
Neutral surface with ink by default. Content: room number (26px/800), the three highest adverse risks as rows (name 12px/600, a 6px bar in currentColor on a 24% track, percent right-aligned), on-now tags top right. Watch-first rooms (the three highest single risks) take the full magnet fill with magnet ink, a 2.5px border and a numbered round badge (1 to 3) after the number; with two tags they switch to short tags (V, P, C). A "Watch first" line above the grid links the same three rooms.

### Room page
Its own view at `#room=N`: "← All 25 rooms" and previous / next links (44px targets), a unit-context line, the room number as a 44px/800 heading, then two columns behind a 2px ink rule: large risk bars (14px track, 24px/800 percent) with on-now tags and the trust line; the last 12 h with "Show more" and "Ask about this room".

### Chat widget
A launcher pill (ink fill, board text, 48px tall) fixed bottom right; the panel (surface, 1.5px ink border, 8px corners, up to 72% of the viewport) opens above it with a heading, Close, chips, the log and the ask form. Closed by default; Escape and Close return focus to the launcher; on a phone it spans the width and closes when the page changes.

### Margin row and range bar
- **Row:** four tracks (name with team or "your row" beneath, median numeral (the p50, never called "most likely"), bar with "range p10 to p90" beneath, status word or "no capacity set").
- **Bar:** a rounded 6px Rule track; the 80% range as a 10px rounded magnet-blue stroke; the median as a 3px ink tick spanning the bar; where a capacity is set, a 3px ink line at the free count.
- **Not forecast:** a row with no model output shows "not forecast", an em dash in Faded Marker, and a dashed Faded Marker line instead of a bar.

### Status word
ON TRACK / TIGHT / SHORT, 12px/800 uppercase, outlined in currentColor, 4px corners. Shown only where a capacity is set; elsewhere the cell reads "no capacity set" in plain Faded Marker, with no outline. SHORT when the median exceeds what is free, TIGHT when the 90th percentile does, ON TRACK otherwise.

### Board toggle and role picker
- **Board toggle:** 1.5px ink border, 8px corners, one button, `aria-pressed`; the label names the board it switches to.
- **Role picker:** a native select with the same border ("I am ..."). It reorders the unit rows and the suggested questions; it never stores a name.

### Shift brief
Top of the right column (first block on a phone). Title "Shift brief (mock)" and a 13px sub-line, then at most three lines separated by 1px rules: the verdict (18px/700, with the status word as an outlined label), the two busiest rows with their ranges, and "Watch first" with three room links (700, 1.5px underline).

### Room drawer
Opens under the unit rows; "Close room" removes it. Holds a sub-line, the room's live tasks as bars sorted by risk (10px Rule track, magnet-blue fill, 18px/800 percent), an "On now, not forecast as new" line of tags, one trust line ("held-out check ... pending run"), the last 12 h of events (five, then "Show more"), and the evidence-not-cause note.

### Suggested questions
Pill chips (1.5px ink border, 13px/600) above the chat log: at most three by role plus "Rerun the forecast"; with a room open the first chip asks about that room. Hover fills Board Shadow.

### Ask the board (chat)
- **Messages:** 8px corners, 14px text, max 92% width; the team's questions right-aligned on Board Shadow, answers left-aligned with a 1.5px Rule border; a 12px/700 Faded Marker speaker line.
- **Input:** board ground, 1.5px ink border, 8px corners; placeholder "Or type a question" in Faded Marker. The log starts empty and hides until the first question.
- **Ask button:** ink fill, board text, 700, 8px corners.

### Honesty labels
- **SYNTHETIC DATA:** a dashed ink outlined badge in the top strip whenever numbers are made up (red stays reserved for SHORT).
- **(mock):** appended to any panel or speaker whose content is mocked (Shift brief, Nemotron 3 Nano).
- **pending run:** italic Faded Marker in place of any measured number that does not exist yet.
- **not forecast:** Faded Marker under a row the model does not cover.

### Focus
All focusable elements: 3px solid focus colour, 2px offset, 6px corners (`:focus-visible`).

## Do's and Don'ts

### Do:
- **Do** shade magnets only by mixing magnet blue into the surface, and pick the magnet ink by contrast so it reaches 4.5:1.
- **Do** pair every status colour with its word (ON TRACK, TIGHT, SHORT), show the word only where a capacity is set, and keep red for SHORT alone.
- **Do** lead with the verdict and the exceptions; fold rows with nothing to decide.
- **Do** give every forecast number its 80% range, as "p10 to p90" text and as a range bar with a median tick.
- **Do** separate regions with 2px ink rules and rows with 1px Rule lines.
- **Do** label mock, synthetic, and missing numbers in place: SYNTHETIC DATA, (mock), pending run, not forecast.
- **Do** keep both boards on the same custom properties; a new surface sets values for `data-board="day"` and `data-board="night"`.
- **Do** keep the 3px focus ring with 2px offset on every focusable element.

### Don't:
- **Don't** build KPI tiles or departure-board rows; counts live in ruled margin rows.
- **Don't** add horizon tabs, time sliders or probability tables: the board has one horizon, the next 24 h.
- **Don't** introduce a second accent colour or fill panels with colour.
- **Don't** convey status, risk, or capacity by colour alone.
- **Don't** add shadows to anything but magnets.
- **Don't** show a measured number that does not come from a run; use "pending run".

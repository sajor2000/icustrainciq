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
  segment:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  segment-selected:
    backgroundColor: "{colors.magnet}"
    textColor: "{colors.magnet-ink}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
  segment-hover:
    backgroundColor: "{colors.board-2}"
    textColor: "{colors.ink}"
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
    textColor: "{colors.status-short}"
    rounded: "{rounded.badge}"
    padding: "2px 6px"
  chip:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  chip-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.board}"
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

The board is the whiteboard an ICU team already reads at shift change, made to forecast. An enamel-white ground carries marker-navy ink, rooms are flat magnets with ink borders, and one blue (the magnet) does double duty as risk shading and as the mark of the current choice. Everything else is ink, rules, and words. It refuses the KPI-tile dashboard and the departure board: no hero numbers floating in cards, no flipping split-flap rows.

Density is operational. The first viewport holds 25 rooms in a 5-column grid on the left two-thirds and a ruled margin column of team counts on the right, so a charge nurse and an attending can answer "what will we be short of, when, and how sure are we" from across a room or on a projector. Numerals are large, tabular, and heavy; prose is short, plain, and honest about what is mock, synthetic, or not yet run.

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
- **Magnet Blue** (`magnet`; night `night-magnet`): the only chromatic fill. Shades magnets by risk, fills the selected horizon segment, draws the 80% range bar, tints the selected horizon band in the futures chart (12% alpha), and doubles as the day focus ring.

### Status
- **On-Track Green** (`status-ok`), **Tight Amber** (`status-tight`), **Short Red** (`status-short`): ink for the status words ON TRACK / TIGHT / SHORT, outlined in the same colour. Short Red also draws the capacity line on range bars, the in-horizon event marks in the futures chart, and the SYNTHETIC DATA badge.

### Neutral
- **Enamel Board** (`board`): page ground; also the ground of the futures chart and the ask input.
- **Board Shadow** (`board-2`): hover fill for controls and the fill of the team's own chat messages.
- **Magnet Surface** (`surface`): the unshaded magnet face that magnet blue mixes into.
- **Marker Navy** (`ink`): text, magnet borders, 2px region rules, the median tick, selected chips, the Ask button.
- **Faded Marker** (`ink-2`): secondary text, subtitles, ranges, timestamps, "not forecast" rows.
- **Rule** (`rule`): 1px row dividers, the range-bar track, quiet borders.
- **Night counterparts** (`night-*`): charcoal ground, chalk ink, lifted blue and status inks; `night-focus` is a lighter blue than the night magnet so the focus ring separates from selected fills.

### Named Rules
**The One Blue Rule.** Magnet blue is the only chromatic fill on the board. It means "risk" on a magnet and "chosen" on a control; no second accent is introduced.

**The Word Beside the Colour Rule.** Status is never colour alone. Every status colour appears as the ink of a word (ON TRACK, TIGHT, SHORT) with a matching outline, and the capacity line is explained in text ("red line = what is free").

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

The page is a 1440px-max frame with 16px/24px/32px padding. A top strip (unit name, SYNTHETIC DATA badge, horizon segments, board toggle) closes with a 2px ink rule. Below it a two-column grid: the room board at `2fr` (sticky at 12px from the top) and the margin column at `minmax(320px, 1fr)`, divided by a 2px ink rule with 24px gutters either side. The room board is a 5-column grid with 12px gaps; the shift brief sits under it behind another 2px rule. A run-details strip closes the page behind a 2px rule.

Inside the margin column, panels are separated by 1px rules with 14px/18px vertical padding. Each team row is a fixed four-track grid: name and range (120px), median numeral (44px), range bar (flexible), status word (78px), separated by 1px rules.

Rhythm runs on 4/8/12/16/24/32px; component interiors use 6px and 10px half-steps (magnet tags, row padding).

Responsive: under 960px the columns stack, the vertical rule becomes a horizontal one, and opening a room scrolls the drawer into view. Under 560px magnets shrink (68px, 6px gaps) and labels shorten (Vent, Press, V, P). Under 420px row tracks tighten to 96/36/flex/64px.

**The Ruled Margin Rule.** Regions are separated by 2px ink rules; rows by 1px rules at 12% ink (14% at night). No cards, no panel backgrounds.

## Elevation & Depth

The board is flat. Depth is carried by ink rules and borders, not by panels. The single exception is the magnet, which carries a faint contact shadow so it reads as a physical piece on the board, and lifts 1px on hover.

### Shadow Vocabulary
- **Magnet contact** (`box-shadow: 0 1px 1px rgba(0,0,0,.18), 0 2px 4px rgba(0,0,0,.06)`): magnets only.

**The Flat Board Rule.** Only magnets cast a shadow. Panels, controls, the chart, and chat messages stay flat on the board.

## Shapes

Corners are small and practical: 3px on magnet tags and legend swatches, 4px on status words and the synthetic badge, 6px on magnets, the futures chart, the close button and the focus ring, 8px on segmented controls, the toggle, the ask input and button, and chat messages, and full pills only on event chips. Borders are 1.5px solid ink on anything interactive or board-like (magnets, segments, toggle, chips, input), 1.5px currentColor on status words and tags, and 1px rule on quiet containers (chart frame).

## Components

### Magnet (room tile)
The signature piece: a flat tile with an ink border, the room number large, the top risk beneath.
- **Shape:** 6px corners, 1.5px ink border, min-height 92px, 8px/10px padding.
- **Fill:** magnet blue mixed into the surface by the room's highest non-discharge risk for the chosen horizon (6% at zero, full magnet at 45% or more). Ink is the higher-contrast of the four board inks; the mix moves until that ink reaches 4.5:1.
- **Content:** room number (26px/800), risk line (13px/600, event name + percent), and top-right VENT / PRESS tags for devices already running.
- **States:** hover lifts 1px; selected gets a 3px ink outline offset 2px; `aria-pressed` reflects selection; the accessible label spells the risk in words.
- **Legend:** three swatches (under 5%, about 1 in 4, 45% or more) above the grid.

### Margin row and range bar
- **Row:** four tracks (name with "p10 to p90" range beneath, median numeral, bar, status word).
- **Bar:** a rounded 6px Rule track; the 80% range as a 10px rounded magnet-blue stroke; the median as a 3px ink tick spanning the bar; where a capacity is set, a 3px Short Red line at the free count.
- **Not forecast:** a row with no model output shows "not forecast", an em dash in Faded Marker, and a dashed Faded Marker line instead of a bar.

### Status word
ON TRACK / TIGHT / SHORT, 12px/800 uppercase, outlined in currentColor, 4px corners. Shown only where a capacity is set; elsewhere the cell is empty. SHORT when the median exceeds what is free, TIGHT when the 90th percentile does, ON TRACK otherwise.

### Horizon segments and board toggle
- **Segments:** a 1.5px ink-bordered group with 8px corners and 1.5px dividers; selected segment fills magnet blue with magnet ink; hover fills Board Shadow. Labels: Next 24 h, Day 2, Day 3, Rest of stay.
- **Board toggle:** the same border and corners, one button, `aria-pressed`, label names the board it switches to.

### Room drawer
Replaces the unit-strain panel in the margin column; "Back to unit" restores it. Holds a sub-line, a risk table (events by horizon, right-aligned percentages, "on now" for running devices), event chips (pill, 1.5px ink border; selected fills ink with board text), the futures chart, drivers with counts "in n of N futures", and a 12-hour history list with Faded Marker timestamps. Closes with the evidence-not-cause note.

### 100-futures chart
A canvas on the board ground with a 1px rule frame and 6px corners. One faint ink line per future (22% alpha) ending at discharge or death; event marks 6px wide, Short Red inside the chosen horizon and half-alpha ink after it; the horizon band tinted magnet at 12%; day gridlines in Rule with 07:00 labels. A caption states the count in words ("in n of 100 futures") and the accessible label repeats it.

### Ask the board (chat)
- **Messages:** 8px corners, 14px text, max 92% width; the team's questions right-aligned on Board Shadow, answers left-aligned with a 1.5px Rule border; a 12px/700 Faded Marker speaker line.
- **Input:** board ground, 1.5px ink border, 8px corners; placeholder in Faded Marker carries an example question.
- **Ask button:** ink fill, board text, 700, 8px corners.

### Honesty labels
- **SYNTHETIC DATA:** a Short Red outlined badge in the top strip whenever numbers are made up.
- **(mock):** appended to any panel or speaker whose content is mocked (Shift brief, Nemotron 3 Nano).
- **pending run:** italic Faded Marker in place of any measured number that does not exist yet.
- **not forecast:** Faded Marker under a row the model does not cover.

### Focus
All focusable elements: 3px solid focus colour, 2px offset, 6px corners (`:focus-visible`).

## Do's and Don'ts

### Do:
- **Do** shade magnets only by mixing magnet blue into the surface, and pick the magnet ink by contrast so it reaches 4.5:1.
- **Do** pair every status colour with its word (ON TRACK, TIGHT, SHORT) and show the word only where a capacity is set.
- **Do** give every forecast number its 80% range, as "p10 to p90" text and as a range bar with a median tick.
- **Do** separate regions with 2px ink rules and rows with 1px Rule lines.
- **Do** label mock, synthetic, and missing numbers in place: SYNTHETIC DATA, (mock), pending run, not forecast.
- **Do** keep both boards on the same custom properties; a new surface sets values for `data-board="day"` and `data-board="night"`.
- **Do** keep the 3px focus ring with 2px offset on every focusable element.

### Don't:
- **Don't** build KPI tiles or departure-board rows; counts live in ruled margin rows.
- **Don't** introduce a second accent colour or fill panels with colour.
- **Don't** convey status, risk, or capacity by colour alone.
- **Don't** add shadows to anything but magnets.
- **Don't** show a measured number that does not come from a run; use "pending run".

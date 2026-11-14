---
name: Lookahead (ICU-Twin)
description: A picture board for the ICU. Ink means now, blue means the next 24 hours.
colors:
  board: "#F3F5F9"
  board-2: "#E8ECF2"
  surface: "#FFFFFF"
  ink: "#111827"
  ink-2: "#4A5567"
  rule: "rgba(17,24,39,.10)"
  line: "#7A8597"
  blue: "#1E5BB8"
  focus: "#1E5BB8"
  selection: "rgba(30,91,184,.22)"
  figure: "#DDE2EA"
  level-medium: "#D2E2F8"
  on-level-medium: "#111827"
  level-high: "#1E5BB8"
  on-level-high: "#FFFFFF"
  ok: "#18794E"
  amber: "#8A4B08"
  amber-bg: "#FCE8C3"
  amber-edge: "#C27A14"
  red: "#B3261E"
  on-red: "#FFFFFF"
  shadow-04: "rgba(16,24,40,.04)"
  shadow-06: "rgba(16,24,40,.06)"
  shadow-12: "rgba(16,24,40,.12)"
  shadow-18: "rgba(16,24,40,.18)"
  night-board: "#0E131B"
  night-board-2: "#1C2533"
  night-surface: "#151C28"
  night-ink: "#E6E9EF"
  night-ink-2: "#A3ADBD"
  night-rule: "rgba(230,233,239,.13)"
  night-line: "#667286"
  night-blue: "#8DBBFF"
  night-focus: "#A9CCFF"
  night-selection: "rgba(141,187,255,.3)"
  night-figure: "#2B3445"
  night-level-medium: "#1B2E50"
  night-on-level-medium: "#F1F4F9"
  night-level-high: "#8DBBFF"
  night-on-level-high: "#0B1220"
  night-ok: "#6CC59B"
  night-amber: "#F0B466"
  night-amber-bg: "#3B2D12"
  night-amber-edge: "#C58A2F"
  night-red: "#F28B82"
  night-on-red: "#1B0C0A"
typography:
  lead-numeral:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "2.75rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  room-heading:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: 1.05
    letterSpacing: "-0.02em"
    fontFeature: "\"tnum\" 1"
  numeral:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "2rem"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  room-number:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  room-number-phone:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  headline:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.375rem"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
    fontFeature: "\"tnum\" 1"
  title:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.2
    fontFeature: "\"tnum\" 1"
  body-large:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 600
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  body:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: ".9375rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  control:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: ".875rem"
    fontWeight: 700
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  caption:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: ".8125rem"
    fontWeight: 400
    lineHeight: 1.45
    fontFeature: "\"tnum\" 1"
  label:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif"
    fontSize: ".75rem"
    fontWeight: 600
    lineHeight: 1.2
    fontFeature: "\"tnum\" 1"
rounded:
  swatch: ".25rem"
  chip: ".3125rem"
  focus: ".5rem"
  control: ".625rem"
  tile: ".75rem"
  switch: ".8125rem"
  card: "1rem"
  thumb: "6px"
  pill: "999px"
  dot: "50%"
spacing:
  hair: ".125rem"
  xs: ".25rem"
  sm: ".375rem"
  md: ".5rem"
  tile-gap: ".625rem"
  grid-gap: ".75rem"
  card-gap: "1rem"
  card-pad: "1.25rem"
  gutter: "1.5rem"
  page-bottom: "3rem"
components:
  strain-pill:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.pill}"
    padding: ".25rem .875rem"
    height: "2.75rem"
  toggle:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: ".375rem .75rem"
    height: "2.75rem"
  toggle-hover:
    backgroundColor: "{colors.board-2}"
  toggle-expanded:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.board}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.board}"
    rounded: "{rounded.control}"
    padding: ".375rem 1rem"
    height: "2.75rem"
  segmented-tabs:
    backgroundColor: "{colors.board-2}"
    rounded: "{rounded.switch}"
    padding: ".1875rem"
  segmented-tab:
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "0 1.125rem"
    height: "2.75rem"
  segmented-tab-hover:
    backgroundColor: "{colors.surface}"
  segmented-tab-selected:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.board}"
  bed-tile-steady:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.room-number}"
    rounded: "{rounded.tile}"
    padding: ".625rem .75rem"
    height: "5.75rem"
  bed-tile-worsening:
    backgroundColor: "{colors.level-high}"
    textColor: "{colors.on-level-high}"
    rounded: "{rounded.tile}"
    padding: ".625rem .75rem"
  bed-tile-watch:
    backgroundColor: "{colors.level-medium}"
    textColor: "{colors.on-level-medium}"
    rounded: "{rounded.tile}"
    padding: ".625rem .75rem"
  bed-tile-not-improving:
    backgroundColor: "{colors.board-2}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tile}"
    padding: ".625rem .75rem"
  bed-tile-leaving:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.tile}"
    padding: ".625rem .75rem"
  status-chip-ok:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ok}"
    typography: "{typography.label}"
    rounded: "{rounded.chip}"
    padding: ".1875rem .5rem"
  status-chip-amber:
    backgroundColor: "{colors.amber-bg}"
    textColor: "{colors.amber}"
    rounded: "{rounded.chip}"
    padding: ".1875rem .5rem"
  status-chip-red:
    backgroundColor: "{colors.red}"
    textColor: "{colors.on-red}"
    rounded: "{rounded.chip}"
    padding: ".1875rem .5rem"
  lead-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "1rem 1.25rem"
  support-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "1rem 1.125rem"
  person-figure:
    backgroundColor: "{colors.figure}"
    textColor: "{colors.ink}"
    width: "3.25rem"
    size: "2.5rem"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: ".375rem .625rem"
    height: "2.75rem"
  room-status-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body-large}"
    rounded: "{rounded.focus}"
    padding: ".3125rem .75rem"
  level-chip:
    backgroundColor: "{colors.board-2}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.chip}"
    padding: ".1875rem .25rem"
  chat-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "1rem"
    width: "26rem"
  question-chip:
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: ".375rem .875rem"
    height: "2.75rem"
---

# Design System: Lookahead (ICU-Twin)

## Overview

**Creative North Star: "The Picture Board"**

The unit is read from three metres as icons, figures and numbers, with almost no sentences. A charge nurse at 07:00 sees which rooms to worry about and what the unit will be short of in the next 24 hours without reading a paragraph. The ground is a cool grey, the cards are white with soft corners, and there is one blue. Everything on the board is either ink or blue: ink means now, blue means forecast.

Colour outside that pair is rationed to meaning. Amber appears only for TIGHT and BUSY, red only for SHORT and VERY BUSY, green only for Leaving and for ON TRACK and USUAL. Every status is carried three ways at once, by a fill or border, a drawn shape and a word. There are two boards, day and night, and both are first-class: they swap custom properties and nothing else.

Credit. The cluster cards, the person figure that fills with a bed's chance (a head-and-shoulders path, two stacked SVGs with a clip-path inset), the range bar with an ink line for free capacity, the status chip, the card radius, hairline and shadow language and the segmented view switch come from Dema's (GitHub: deetherese) design on the `alternative` branch (`origin/alternative`, `mockups/command-center.html`). The blue acuity scale comes from the earlier board at commit 65b36c6. The icon family was drawn for this board; no icon was copied or adapted from an external set.

**Key Characteristics:**
- Ink is now, blue is the next 24 hours.
- Pictures before words: one drawn icon family, solid for running, outline for expected.
- Every bed is drawn as a change: Now, an arrow, Next 24 h.
- Chances are counts out of ten, never percentages.
- Two boards (day, night) with the same grammar; wall screens scale the root to 120% from 1800px.
- Two tabs only: Bed board (default) and Unit strain.

## Colors

A cool grey ground, white cards, near-black ink and one blue; amber, red and green exist only as status.

### Primary
- **Forecast Blue** (`blue`, night `night-blue`): everything that is a forecast. Expected counts, the 8-in-10 range on the bar, the fill of a person figure, the filled dots on the room page, the caret and form accent. `level-high` is the same blue used as a full tile fill for Worsening, with `on-level-high` text.
- **Watch Blue** (`level-medium`, night `night-level-medium`): the light step of the acuity scale. Fills Watch tiles and Medium level chips, with `on-level-medium` text.

### Secondary
- **Leaving Green** (`ok`): the 2px border and status word of a Leaving bed, the fill of a leaving figure, and the border and word of the ON TRACK and USUAL chips. Nowhere else.

### Tertiary
- **Tight Amber** (`amber` text on `amber-bg`, edged `amber-edge`): the TIGHT and BUSY chip, and the 2px border of the card that carries it.
- **Short Red** (`red` fill with `on-red` text): the SHORT and VERY BUSY chip, and the 2px border of the card that carries it.

### Neutral
- **Board Grey** (`board`): the page ground, the sticky tab bar, and the text colour on ink-filled controls.
- **Board Grey 2** (`board-2`): the segmented switch trough, control hover, the Still on support tile ground, the asker's chat bubble, the unlevelled level chip.
- **Card White** (`surface`): cards, tiles, controls, the bead on the range bar.
- **Ink** (`ink`): text, everything that is running now, selected controls, the free-capacity line.
- **Ink 2** (`ink-2`): secondary text, labels, ranges, the Steady word.
- **Hairline** (`rule`): card and tile borders, dividers.
- **Line** (`line`): control borders, the empty dot outline, scrollbar thumb.
- **Figure Grey** (`figure`): the empty person figure and the range bar track.
- **Shadow tints** (`shadow-04`, `shadow-06`, `shadow-12`, `shadow-18`): the four alphas of one shadow colour, used only inside the two shadows below.

Night values carry the same names with a `night-` prefix. On the night board blue lightens, ink and ground invert, the card shadow is removed, and text on the blue and red fills turns dark.

### Named Rules
**The Ink and Blue Rule.** Ink means now, blue means forecast. A count, icon or figure in ink is happening at 07:00; the same thing in blue is expected in the next 24 hours. Never use blue for decoration or for a link.

**The Rationed Colour Rule.** Amber only for TIGHT and BUSY. Red only for SHORT and VERY BUSY. Green only for Leaving and for ON TRACK and USUAL. Red never marks a bed.

**The Three Carriers Rule.** Status is never colour alone. Each status has a fill or border, a shape and a word.

## Typography

**Display Font:** system UI stack (system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif)
**Body Font:** the same stack
**Label/Mono Font:** none

**Character:** One native sans in every role, so the board looks like the machine it runs on and loads with no network. Hierarchy comes from size and weight (400, 600, 700, 800); numerals are tabular everywhere so counts hold their column.

### Hierarchy
- **Lead numeral** (800, 2.75rem, 1.05): the two counts on the Life support lead card.
- **Room heading** (700, 2.5rem, 1.05, -0.02em): the room number on the room page; 2rem on phone.
- **Numeral** (800, 2rem, 1.05): counts on support cards, room numbers on wall screens.
- **Room number** (800, 1.75rem, 1): the room number on a bed tile; 1.5rem on phone.
- **Headline** (700, 1.375rem, 1.15): the unit name in the header.
- **Title** (700, 1.125rem, 1.2): section and card headings, the counts in the strain summary pill.
- **Body large** (600, 1rem): room page rows and the room status chip; the percentage beside icons on wall screens.
- **Body** (400, .9375rem, 1.45): base text.
- **Control** (600 to 700, .875rem): buttons, tab labels, chat messages, the percentage on tiles, small headings.
- **Caption** (400 to 700, .8125rem): ranges, count captions, status words on tiles, notes.
- **Label** (600 to 800, .75rem): the status chip (800, 0.05em tracking, the word already in capitals), field labels, percentages under figures, the NOW and NEXT 24 H captions (700, 0.05em tracking, capitals).

All sizes are rem. From 1800px the root is 120%, so every size and space on a wall screen grows together.

### Named Rules
**The Count Rule.** A chance is a whole percentage on every screen ("23%"), "<5%" when very small, and "No estimate" when it is null (J.C., 2026-11-14 evening; this replaces the earlier natural frequencies). The room page keeps its 10-dot array as the picture beside the percentage. The lines that flag a bed are chosen by the team (default 25%, Worsening at the next step up, Leaving 60%).

**The Range Rule.** Every forecast count carries its range in Caption weight 400 beside it ("+3" then "1 to 5").

## Layout

One centred column, max 92rem, with a 1.5rem gutter (1rem on phone). The header is a single wrapping row: unit name and run line, then the strain summary pill, Night board, role, Update the unit, Ask. Below it the tab bar is sticky at the top with the one-line key at its right.

- **Bed board:** the priority rail, then All rooms. The room grid is five across, four below 1200px, three at 960px and below, two at 560px and below, with a .75rem gap (.5rem on phone, .625rem on wall screens). With the chat docked the grid becomes auto-fill at a 12.5rem minimum.
- **Unit strain:** the Life support lead card (two columns, one at 960px and below), then support cards in an auto-fill grid at an 18.5rem minimum with a 1rem gap. The card for the reader's role is ordered first.
- **Room page:** two cards, 1.2fr and 1fr, stacking at 960px and below.
- **Chat:** a launcher fixed 1.5rem from the bottom right (a 3.25rem circle); the page keeps 6.5rem of bottom padding so it never rests on content at the end of the page. The panel is 25rem by 37.5rem (at most 80vh) in the same corner; at 560px and below it is a bottom sheet at 85% of the height.
- **Wall screens (1800px and up):** root 120%, tiles slightly shorter (5.25rem), larger room numbers and percentages.

Spacing is a short rem scale: .125, .25, .375, .5, .625, .75, 1, 1.25, 1.5. Every interactive target is at least 2.75rem (44px) tall.

## Elevation & Depth

Nearly flat. Depth is one soft two-layer shadow under white cards on a grey ground, plus a hairline border. Dema's card language: radius, hairline, soft shadow. The night board removes the card shadow and relies on surface tone and the hairline.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px rgba(16,24,40,.06), 0 4px 12px rgba(16,24,40,.04)`; `none` at night): bed tiles, cards, the strain summary pill, the room page strip.
- **Floating panel** (`box-shadow: 0 2px 4px rgba(16,24,40,.12), 0 16px 40px rgba(16,24,40,.18)`): the chat panel below 1200px only. Docked, it has no shadow and a hairline left border.

### Named Rules
**The Two Shadows Rule.** There is a card shadow and a floating shadow. Nothing else lifts. Hover moves a tile or figure up 1px over .15s; it does not add shadow.

## Shapes

Soft rounded rectangles on a stepped scale: cards 1rem, tiles and chat bubbles .75rem, the tab trough .8125rem around .625rem tabs, controls .625rem, status chips .3125rem, legend swatches .25rem. Pills (999px) are for the strain summary, the ward tag and suggested questions. Circles are for the ten-dot arrays and the bead on the range bar.

Borders carry meaning. A 1px hairline is the default. A 2px green border is Leaving, a 3px ink border is Still on support, a 2px amber or red border is a card whose status is not ON TRACK or USUAL. A 1.5px dashed border is the "updating" tag. Thicker borders reduce padding by the same amount so tiles stay aligned.

## Components

### Header and strain summary pill
The unit name in Headline, then a caption row: the product name in ink at 800, the 07:00 to 07:00 window, a pill ward tag and the run line. The strain summary is a 2.75rem pill link on the surface with the card shadow: the count on life support in ink, the expected count in blue, then the status chip. It opens Unit strain. Header buttons are surface with a line border; pressed or expanded they turn ink with board text.

### Segmented tabs
Dema's segmented view switch. A board-2 trough with a hairline and .1875rem padding holds two 2.75rem buttons, each an icon and a label at 700: Bed board (a 2 by 2 grid) and Unit strain (three bars on a baseline). The selected tab is ink with board text; hover is surface. On phone the two tabs share the full width.

### Bed tile
A button, min-height 5.75rem, radius .75rem, with the card shadow. Top row: room number (Room number), age and sex in Caption 600, then one trajectory status at the right as a shape and a word. Bottom row: the Now -> Next 24 h strip. The fill scale is the blue acuity scale from commit 65b36c6.

- **Worsening:** full blue fill (`level-high`), text in `on-level-high`, solid triangle.
- **Watch:** light blue fill (`level-medium`), outline triangle.
- **Still on support:** board-2 ground, 3px ink border, two horizontal bars.
- **Leaving:** white, 2px green border, the bed-with-arrow icon and the word in green.
- **Steady:** white, a small dot, the word in ink-2 at 600.

**Now -> Next 24 h strip.** Two captioned columns joined by an arrow (see Strip captions). NOW: solid icons for the life support running at 07:00, or "no support". NEXT 24 H: an outline icon and its percentage for each new support at 20% or more; a plus in a ring with the combined chance when no single support reaches 20%; the bed with an arrow and its percentage when leaving is 60% or more, and from 20% for a bed on life support; "leaving <20%" on a Still on support bed; "nothing new" otherwise.

> **Bed status removed (2026-11-14).** The Bed board no longer has Worsening / Watch / Still on support / Leaving statuses, status colours on tiles, or the "Bed colours" settings. An event (a new ventilator, vasopressor or CRRT, death, discharge) shows on a bed's card as a circle icon with its chance when it is at or above that event's threshold in Settings. When a new life support or death is at its threshold, the person icon on the bed's tile turns red and pulses (the circle icons keep their own colours and do not pulse); discharge alone does not. The plus-in-a-ring combined chance is gone from the board. Where the text below still describes statuses or tile colours, this note wins.

### Priority rail
Removed (2026-11-14). There is no row above All rooms. Each bed tile carries Dema's person figure from Unit strain left of the bed number, as one flat tint (no level fill). In Next 24 h the figure turns red and pulses (beat and halo, 1.2s; still under reduced motion) when a new life support or death is at its threshold in Settings; the circle icons keep their own colours. In Now the figure is solid ink on a bed on life support, and a bed on two or more supports (Critical, named in the key) has a red border.

### Status chip
Dema's status chip. Capitals at Label 800 with 0.05em tracking, radius .3125rem, 1.5px border. ON TRACK and USUAL: surface with a green border and green word. TIGHT and BUSY: amber-bg fill, amber-edge border, amber word. SHORT and VERY BUSY: red fill, on-red word. Not ready: line border, ink-2 word at 600, no tracking. The word is always shown.

### Life support lead card and capacity form
A Dema cluster card at full width: surface, radius 1rem, hairline, card shadow, two columns. Left: "Life support" with the status chip and what it is measured against, then patients on now in ink and expected in blue at Lead numeral, a tall range bar (1.75rem) and one caption line. Right: a line on expected deaths in plain ink-2 text, then "Set tonight's capacity", a 2.75rem disclosure with a chevron that turns when open. The form is two labelled number inputs (surface, line border, radius .625rem, 2.75rem), an ink Save button, and a live status line. Amber and red statuses add a 2px border to the card.

### Support cards
Dema's cluster cards, one per support (IMV, Vasopressor, CRRT) and one for Leaving. Header: the support's solid icon at 2.5rem, a Title name, the status chip at the right. Then counts at Numeral: on now and free in ink, expected in blue with its range. Then the range bar, then groups of person figures under small ink-2 labels (On now, May start, Likely to leave) separated by a hairline.

**Range bar** (Dema's, with the ink line for free capacity). A 6-unit rounded track in figure grey; a 10-unit rounded blue segment for the 8-in-10 range; a surface bead with a blue ring at the median; a solid ink line for what is free or what tonight's staffing covers; a dashed ink line for a typical day.

**Person figure** (Dema's). A 2.5rem by 2.625rem head-and-shoulders silhouette above a room number (800) and its percentage (Label). It is two stacked SVGs of the same path: a base in figure grey and a fill in blue clipped with `clip-path: inset(calc(100% - var(--p)) 0 0 0)`, so it fills from the bottom to the bed's chance. Solid ink means the support is on now. A grey (secondary ink) fill means leaving. Each figure is a button that opens the room; hover lifts the silhouette 1px.

### Room page
A back link and previous and next room links, underlined ink at 700 with the arrow icon. Then the room number in Room heading, the room status chip (the bed tile's five statuses as a chip at 1rem, radius .5rem), and the Now -> Next 24 h strip in its own small card with "Now" and "Next 24 h" labels. Two cards below. The first lists each event as a row: icon and name, a level chip (Low on board-2, Medium on `level-medium`, High on `level-high`, On now in ink), a ten-dot array (.75rem circles, filled blue to the count, outlined in line otherwise) and the percentage. Death is a plain row with no icon and no colour. The second card holds the last 12 hours and the two room actions.

### "How this forecast was made" disclosure
One folded disclosure in the footer above a hairline holds every definition: the tile grammar, the thresholds, the icon key, the five forecasts with median and range in a plain ruled table, and the model facts as short definition lists. The summary is Control 700 in ink-2 and turns ink on hover. Nothing here is shown on the board by default.

### Icon family
One inline SVG sprite, drawn for this board on a 24 grid: `currentColor`, 1.75 stroke, round caps and joins, no fill by default. Symbols ending in "-on" are solid and mean running now; plain symbols are outline and mean expected. No icon was copied or adapted from an external set. Sheet: `docs/screenshots/icons.png`.

- **Ventilator:** lungs under an airway tube and circuit T-piece.
- **Vasopressor:** a syringe with a drop.
- **CRRT:** a capped haemofilter with blood lines and arrows.
- **Leaving:** a bed with an outward arrow.
- **Trajectory shapes:** solid triangle (Worsening), outline triangle (Watch), two bars (Still on support), dot (Steady).
- **Marks:** plus in a ring (combined chance), ring (no support now), dash (nothing new).
- **Interface:** arrow, chevron, moon, chat, bed grid and strain bars, on the same grid and stroke. The person figure is Dema's.

### Focus ring
A 3px outline in `focus` with a 2px offset and a .5rem radius on every focusable element. On the person figure the ring is drawn around the silhouette with a 3px offset.

### Motion
State changes only: a .2s ease-out on the board colour swap, a .15s ease-out 1px lift on tile and figure hover, a .15s chevron turn. Nothing pulses or loops. Reduced motion removes all of it.

### Product title and unit chip
The H1 is the product, "Lookahead", with the descriptor "ICU forecast · next 24 hours" beside it at 1rem / 600 in secondary ink. The unit ("Medical ICU · 25 beds") is a pill chip in the sub-line next to the data-source tag and is read from the forecast, never written into the page.

### Flag line control (Dema's threshold toggle)
"Flag beds at" in secondary ink, then a three-part segmented control (50%, 25%, 10%; surface ground, line border, radius .625rem, 2.75rem tall; the chosen part is blue with its on-colour) and an outlined "Thresholds" button. The popover under it (surface, line border, radius 1rem, floating shadow, 24rem wide) has one row per line: icon and name, a 2.75rem − and + stepper, the value at 800, and the beds it catches; then a custom field for all supports and Reset. Hidden in Now. Credit: Dema (deetherese).

### Person figure, highest risk and leavers (Dema's)
A figure at the next step above its line takes a red fill, a red-tinted base and a soft radial red halo behind it; the halo is static (no pulse, no ring animation), and its percentage is red at 800. Leavers fill in secondary ink (grey), not green. A leaver on life support carries 1.125rem round device badges at its top right. This is the one place red marks a bed; tiles never use it.

### Capacity bar and labels (Dema's)
When a machine total is set the card's bar is the whole total (in use + free): a solid run for in use now, a lighter run to in use plus flagged beds, an ink tick at each with its number, "N total" at the right end. It is blue while it fits and red when it passes the total. Labels appear only when they matter: SHORT (solid red chip, 2px red card border), AT LIMIT (amber chip, amber border). The same alert is repeated once in the header strain line. Cards grow with the beds they hold so the row stays even.

### Patient name
The room number stays the identifier. The display name ("Rivera, J.") sits on the same line as sex and age at .8125rem / 700 in the tile's ink, followed by " · M 68" in secondary ink. Only the name shrinks: it is cut with an ellipsis and its legend gives the full name. The room page heading reads "Room 20 · James Rivera · M 68". Person figures on Unit strain keep room numbers only. Names in the demo are fictional.

### Time switch (Now | Next 24 h)
A pill-shaped two-state switch beside the tabs and on the room page, visually lighter than the tabs (surface ground, line border, .875rem / 700, 2.75rem targets). The selected side carries the system's two time colours: **Now is ink, Next 24 h is blue**. It decides when; the tabs decide what. Now shows only what is running at 07:00; Next 24 h shows the forecast. Switching keeps the grid, the room order and the scroll position; tiles cross-fade for 180ms when motion is allowed.

### Bed tile, Now
Room, sex and age, and 1.75rem solid icons with their names. Weight is the number of supports running: none is a white tile that reads "No life support"; one sits on the tinted ground (`board-2`); two or more adds the 3px ink border and reads "2 supports". No blue appears in Now.

### Strip captions
In Next 24 h every tile and the room page carry two captioned columns joined by the arrow: **NOW** over the solid icons (or "no support") and **NEXT 24 H** over the forecast items (or "nothing new", or "leaving <20%" on a Still on support bed). Captions are Label size, 700, capitals, in the tile's secondary ink. On a phone the two columns become two labelled rows and the arrow is dropped. On the room page each forecast item also shows its name ("Vasopressor 43%").

### Chat widget
A launcher (a 3.25rem ink circle with the chat icon in board colour, floating shadow, accessible name "Ask Lookahead") and a non-modal panel (surface, line border, radius 1rem, the same floating shadow, no scrim). Header: "Ask Lookahead", a context pill button ("Unit" or "Room 12", `board-2` fill), and minimise and close as 2.75rem icon buttons. Suggested questions are stacked pills shown only while the conversation is empty. The team's messages sit right on `board-2`; answers sit left with a rule border, numbers at 800 and room numbers as blue underlined links. "Thinking…" carries an outlined Stop button. The input is a textarea that grows to four lines beside a 2.75rem send button that is `board-2` when disabled and ink when it can send. A blue dot on the launcher means the forecast changed since the chat was last open. On a phone the sheet has a short handle bar at its top edge.

### Figure legend (tooltip)
One element for the whole page: ink fill, board text, .8125rem / 600, radius .5rem, at most 19rem wide, floating shadow, `pointer-events: none`. It appears 150ms after hover, at once on keyboard focus, and on touch by tap or long-press; it leaves at once. It sits above its target, or below when there is no room, and is clamped to the viewport. Text only, two short lines at most, the same wording as the key and "How this forecast was made" (one `DEF` map in the page builds all three). It adds to the visible labels and never replaces them.

### Staffing card and the 1:1 tag
The Staffing card leads the Unit strain row: the nurse icon, "Staffing", the ratio rule as its subtitle, then two blocks side by side (Nurses, Respiratory therapists), each a small heading with its drawn icon, the number needed now in ink, the next 24 h number in blue with its range, the number on shift when entered, and one split line ("1:1 × 3 · 1:2 × 22"). SHORT and AT LIMIT use the same chips as capacity. On a bed, 1:1 is a quiet outlined tag (Label size, 700, radius .3125rem, the tile's own ink) in the top row; a 1:2 bed carries nothing. The nurse (cap with a cross) and respiratory therapist (figure with lungs) icons belong to the same family: 24 grid, 1.75 stroke.

### Stale forecast
A forecast a day old or more turns the run line into an amber chip ("Forecast from yesterday 07:00 · update the unit") and adds an amber "From yesterday" chip to the header strain line. Amber here means "not today's", the one use outside TIGHT / BUSY / AT LIMIT.

### Forecast not ready
When the forecast is not ready (`pending-model`) the board is all ink: Now content only, no blue, no statuses. One sentence, "Forecast not ready yet: the model is still being prepared.", leads the sub-heading in bold; the flag control drops to 55% opacity and is disabled. No placeholder numbers are drawn.

### Credits
Cluster cards, bed figures, risk-threshold toggle and capacity model: Dema (deetherese), from the `alternative` branch.

## Do's and Don'ts

### Do:
- **Do** draw now in ink and forecast in blue, on every surface.
- **Do** write chances as whole percentages ("23%"), "<5%" when very small, and "No estimate" for null.
- **Do** carry every status as a fill or border, a shape and a word.
- **Do** show the range beside every forecast count.
- **Do** use solid icons for support running now and outline icons for support expected.
- **Do** keep every target at least 2.75rem (44px) tall and all text at 4.5:1 or better on both boards.
- **Do** change only custom properties between the day and night boards.
- **Do** keep to the five predictions: IMV, vasopressor, CRRT, leaving the ICU, death.
- **Do** credit Dema (deetherese) wherever the cluster card, person figure, range bar, status chip or segmented switch is reused.

### Don't:
- **Don't** let death colour or mark a bed. It is a plain count on Unit strain and a plain row on the room page.
- **Don't** use red for anything but SHORT and VERY BUSY, or amber for anything but TIGHT and BUSY.
- **Don't** signal status by colour alone.
- **Don't** use signal-bar glyphs or letter tags (V, P, C) for supports.
- **Don't** add pulsing or looping animation.
- **Don't** write hedging or disclaimer copy on the board.
- **Don't** add a sixth prediction or a forecast count without its range.
- **Don't** bring in icons from an external set; extend the drawn family on the 24 grid.

## Diagrams

Figures in `docs/diagrams/` and on the project page (`docs/index.html`) use this design system: the same tokens, the same system font, the same icon family. They are written by `docs/diagrams/make_figures.py` and recorded for the diagram-design skill as the profile `lookahead` (`.diagram-design`; a copy is in `docs/diagrams/lookahead-profile.md`, to place in `~/.diagram-design/profiles/lookahead.md` on a new machine).

| Diagram role | Token and treatment |
|---|---|
| Ground | `board` |
| Structure: a service, a page, a step | `surface` card, 1px `line` border, radius .75rem, `ink` title, `ink-2` second line |
| Data store: a Fuzzball volume | `board-2` fill, 1px `line` border |
| Our patient model | solid `blue` (`level-high`) with `on-level-high` text; at most one per figure |
| What our model produces: classifiers, forecast files, the forecast step | `level-medium` fill, 1px `blue` border, `ink` text |
| NVIDIA model, used as is | solid `ink` with `board` text |
| Boundary: patient data stays inside | 1.5px dashed `ink` container, radius 1rem, `ink` label in Label type |
| Arrow, a call between parts | `ink`, 1.5px |
| Arrow, the forecast being written or read | `blue`, 1.5px |
| Arrow, on request | `ink-2`, dashed |
| Step status | the status chip: green border and word (Done), `amber-bg` with `amber-edge` (To do first), `line` border with an `ink-2` word (Ready) |

Type is the board's scale: node title 1rem at 700 (1.125rem on the two README figures), second line .8125rem (.875rem), tags and arrow labels .75rem at 700 in capitals with 0.05em tracking, caption .875rem in `ink-2`. Icons come from the board's sprite, outline, 1.75 stroke. Figures have no shadows and no red; every figure has one caption line and no legend block.

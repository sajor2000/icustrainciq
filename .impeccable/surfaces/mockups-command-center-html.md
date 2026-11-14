---
version: 1
slug: "mockups-command-center-html"
primary_target: "mockups/command-center.html"
related_targets: []
---

# Surface: Lookahead ICU board (command center)

Scope: `mockups/command-center.html`, the static board served by `app/board.py`. Operate mode. Redesign of the look (2026-11-14, J.C.) on top of the working data handling; the API contract in `docs/FRONTEND_SPEC.md` is unchanged.
Audience and job: the charge nurse and attending at 07:00 see what the unit will be short of in the next 24 hours and which rooms to look at; pharmacy, respiratory therapy and the bed manager find their own block first; a physician opens one room.
Constraints: five predictions only; no percentages; death never marks a tile; status never by colour alone; red only for SHORT / VERY BUSY; day and night boards, both first-class; phone at 390 px.
Credit: the cluster cards, the person figure that fills with the chance, the range bar with an ink line for free capacity, the status chip and the segmented view switch come from Dema's (deetherese) `origin/alternative` design.

## Direction contract

THESIS: A picture board: the unit read from three metres as icons, figures and numbers, almost no sentences. Refuses the ruled text panel of the previous board and the KPI-tile dashboard.
OWN-WORLD: Cool grey ground (#F3F5F9), white cards with 16 px corners and a soft offset shadow, hairline rules, near-black ink (#111827), one blue (#1E5BB8). Ink means now, blue means forecast. Bed tiles carry one trajectory status: full blue Worsening, light blue Watch, tinted ground with a 3 px ink border Not improving, green border Leaving, white Steady. One drawn icon family (lungs on an airway tube and circuit, syringe with a drop, capped filter with blood lines, bed with arrow), solid for running, outline for expected. Amber only for TIGHT / BUSY, red only for SHORT / VERY BUSY. System UI stack, tabular numerals. Night: #0E131B ground, same grammar.
STORY: The charge nurse reads "Worry first" (Worsening, then Not improving), opens a room, and checks cover from the one-line strain summary or the Unit strain tab; pharmacy, respiratory therapy and the bed manager go to Unit strain and find their card first. Signature move: every bed drawn as a change, solid icons for now, an arrow, outline icons with "N in 10" for the next 24 hours; on Unit strain, Dema's person figure filling to a bed's chance under each support's icon.
FIRST VIEWPORT: Slim header (unit, Lookahead, 07:00 to 07:00, ward tag, run line, strain summary link, Night board, role, Update the unit, Ask). A segmented switch, Bed board | Unit strain, with a one-line key. Bed board (default): the Worry first rail, two groups of bed tiles on the ground, then all rooms five across, each tile room number, "F 67", one status (shape + word; full blue Worsening, light blue Watch, ink border Not improving, green border Leaving, white Steady) and the Now -> Next strip. Unit strain: a Life support lead card (status chip, on now in ink, expected in blue, range bar, capacity form) and four cards (IMV, Vasopressor, CRRT, Leaving) with counts, a range bar and figures. Phone: tabs sticky, rail first, tiles two across.
FORM: seed: none (pinned). "Take the best of both" = "Dema's cluster design + the older blue acuity tiles"; "make icons for vent, CRRT, pressors better than V/C/P font ... much more visual, not words"; then "a bed board with CURRENT data, then FORECASTED data with changes to patient status ... easy to see which patients the team should worry about ... strain on a different tab"; both tabs and the tile were specified region by region.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

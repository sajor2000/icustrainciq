---
version: 1
slug: "mockups-command-center-html"
primary_target: "mockups/command-center.html"
related_targets: []
---

---
version: 1
slug: "docs-mockups-command-center-html"
primary_target: "docs/mockups/command-center.html"
related_targets: []
---

# Surface: ICU command center (bed board mockup)

Scope: static HTML mockup of the ICU-Twin board, Operate mode. Synthetic numbers only, labelled. Replaces the unstyled table in app/board.py later; app/board.py is untouched now.
Audience and job: the ICU team (charge nurse and attending) at shift start plans tomorrow's staffing and beds; a physician opens one room; pharmacy, respiratory therapy and the bed manager read their rows; judges see the mechanism.
Constraints: docs/DECISIONS.md D4-D7 (per-room views on the open stage ward only; counts only for real MIMIC-IV; drivers shown as evidence, not cause). Status never by color alone. Day and night boards, user-chosen.

## Direction contract

THESIS: The unit whiteboard nurses already read, made to forecast. Refuses the KPI-tile dashboard and the departure board.
OWN-WORLD: Enamel-white board (#F4F5F2), marker-navy ink (#1E2A33), magnet blue (#2F6FB0) for the selected horizon and risk shading; status words ON TRACK / TIGHT / SHORT in green, amber, red; rules at 12% ink; system UI stack with tabular numerals; 64x48 magnets, 6 px corners, 8 px grid. Night board: charcoal ground, chalk ink, same grammar.
STORY: In ten seconds the team sees what the unit will be short of in the next 24 h and how sure the forecast is; they scrub to Day 2, Day 3 or rest of stay, open a room to see its futures and what preceded the risk, and ask Nemotron in plain words.
FIRST VIEWPORT: Left two-thirds: the 25-room board of magnets, each shaded by its highest risk, room number large. Right third: the margin column of team counts, median tick inside an 80% range bar against a capacity line, status word beside each. Top strip: horizon scrubber (Next 24 h, Day 2, Day 3, Rest of stay) and the day/night switch. Room drawer and chat open in the margin column on selection.
FORM: Unit whiteboard, the team's pinned world: playbook "Demo plan and UI/UX decisions", row Visual world = "Unit bed board, the whiteboard nurses already read" (team pick over departure board and KPI tiles), position 1. No concept-seed roll: precise request inside an established world.
ADAPTATION: magnets are larger than the playbook's 64x48 (about 168x92 desktop) so room numbers and risk words read on a projector and across a unit; the grammar (flat tile, ink border, 6 px corners, magnet-blue shading) is unchanged.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

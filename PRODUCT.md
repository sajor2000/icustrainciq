# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated: static HTML + vanilla JS (no build step), written at the event with a Python stdlib server. It runs as a Fuzzball service on port 8080 on the team's own nodes and reads `forecast.json` / `workflow.json`. Chosen because it needs no Node in the image, no build, and works offline on hospital-owned hardware.

## Users

- **Primary: the ICU team, the charge nurse and the attending physician together,** at the start of a shift (for example 07:00 or 19:00), reviewing every count, deciding whether to call in or float a nurse and which beds to free.
- **Also: the physician on a single room**, opening a stage-ward room's five predictions and the last events the model read, and asking the chat about it; and pharmacy and respiratory therapy, reading their own rows.
- **Secondary: bed manager / house supervisor**, deciding how many ICU beds to hold for ED and OR admissions in the next 24 hours.
- **Evaluators: hackathon judges** (CIQ x NVIDIA, SC26 track). They need to see what was built and what the second node unlocked.

## Product Purpose

Lookahead ("The next 24 hours, in one place."; working name ICU-Twin in the backend) makes exactly five predictions for every patient in the ICU, each for the same fixed window, the next 24 hours from 07:00 to 07:00, refreshed daily for 07:00 rounds: ICU discharge (leaves the ICU to a ward or step-down unit), invasive mechanical ventilation (IMV) start, vasopressor start, CRRT start and in-hospital death. The board adds patients up into unit counts with a likely range (8 in 10 outcomes, p10 to p90). Nothing else is forecast on the board (no hypotension, no ICU readmission). For each current patient it does one forward pass of a small generative event model and reads its last hidden state with a logistic probe per task, then adds the patients up. Success: the ICU team of nurses and physicians, pharmacy, respiratory therapy and the bed manager can act on the next day's staffing and beds before the unit is short, and a judge can see the scaling result in one glance.

## Positioning

Built for the small or rural ICU: one unit, scarce ventilators and CRRT machines, transfers that take hours, no data-science team and no cloud contract. Two desk-size local machines run the whole product, and patient data never leaves the building. Trained and run on local hardware (MIMIC-IV in CLIF format); a hospital with CLIF-format data can run the same pipeline on its own records.

Local compute for a busy ICU. Right-sized models (tens of millions of parameters) trained on open, credentialed CLIF-format data run on hardware the hospital owns, so patient data never leaves the site. Contrast: Epic Curiosity is cloud-hosted inside Cosmos and predicts per patient; ICU-Twin forecasts unit-level demand for the next 24 hours, locally. Tagline in use: "Compute buys certainty." Promise: "One forecast per unit, on hardware you own."

## Operating Context

- Built and demonstrated at the CIQ x NVIDIA Local AI Hackathon (Chicago, 2026-11-14/15) by team7: five people, two Lenovo ThinkStation PGX (NVIDIA GB10) nodes, Fuzzball 4.3 orchestration, five-minute demo.
- Data: MIMIC-IV-Ext-CLIF (credentialed), moved once into the team7 persistent volume `mimic_clif`. Per-patient views use the open MIMIC-IV demo, synthetic patients, or (approved, local only) real MIMIC-IV room views, marked "MIMIC-IV · local" in the top strip.
- Real-world use is a daily forecast for 07:00 morning rounds (started at 06:30 so it is ready at 07:00, and on request) on local hardware from a live CLIF feed.

## Capabilities and Constraints

- 25 beds (50-bed stretch only if fast); one fixed horizon for all five predictions, the next 24 h (07:00 to 07:00), set by `backend/icutwin/config/winnowing.yaml` (`horizon_after_threshold_s` 86400); five predictions only.
- Outputs: a bed board (each bed now, then the next 24 h, with one trajectory status), a unit strain tab (patients on life support now, more expected, with p10/p50/p90, against tonight's staffing or a typical day), a room page; each team reads its own line first: pharmacy (vasopressor starts), respiratory therapy (IMV starts), ICU team of nurses and physicians (CRRT starts and deaths), bed manager (ICU discharges to ward or step-down); backtest against what happened after time T and against persistence; training speed 1 vs 2 nodes.
- ICU-only cohort; each forecast starts 24 h after ICU arrival (`docs/DECISIONS.md` D3). Current ICU patients only: new arrivals need a separate model (open).
- Screens: the bed board and unit strain tabs (command center), per-room drill-down and room chat for the open stage ward only, each room's five predictions with the last events the model read (D4 to D7).
- Research prototype on retrospective data; makes no treatment recommendations.
- Capacity is set on the Unit strain tab ("Set tonight's capacity"): total ventilators and CRRT machines on the unit (free = total − in use now), and optionally the life-support patients tonight's staffing covers. Until the staffing number is set the board compares with a typical day.

## Evidence on Hand

- ICU strain and staffing evidence with PubMed citations in the team playbook (Bravata 2021, Wilde 2021, Anesi 2018/2026, Kiekkas 2022, Needleman 2011, Murray 2023, Palmer 2024).
- No real forecast numbers, backtest results or scaling results exist yet. Never fabricate them in UI or copy; show "Not ready yet" as a standalone state until `results/bench.jsonl` and `forecast.json` exist.

## The five predictions (decided 2026-11-14, J.C.)

| Prediction | Question it answers, next 24 h (07:00 to 07:00) | Label | Team |
|---|---|---|---|
| ICU discharge | Is this patient going to leave the ICU (to a ward or step-down)? | `ADT//TRANSFER_IN//ward` or `//stepdown` | bed manager |
| IMV | Will invasive mechanical ventilation start? | `RESP//device_category//imv` | respiratory therapy |
| Vasopressor | Will a vasopressor start? | `LABEL//pressor_init` | pharmacy |
| CRRT | Will CRRT start? | `LABEL//crrt_init` | ICU team |
| Death | Will the patient die in hospital? | `HOSP//discharge_category//expired` | ICU team |

Removed from the board: hypotension and ICU readmission. A task already under way at 07:00 is shown as "on now", not forecast as new.

## Life support, the strain panel and updates (decided 2026-11-14, J.C.)

**Life support** means IMV (breathing tube or tracheostomy), a vasopressor infusion (inotropes alone do not count) or CRRT. **Now** means running at the 07:00 cut. ECMO and other mechanical support are not in the data and are not shown on the board.

**Room level** is the combined chance of any new life support in the next 24 hours, skipping supports already running: High at 40% or more, Medium at 20% or more, else Low. Death never colours or marks a bed.

**Bed board** (the default tab): a **Now / Next 24 h** switch chooses when. **Now** shows only current sickness: the life support running at 07:00 on each bed, weighted by how many supports are running, with "Sickest now" on top; nothing forecast is shown. **Next 24 h** (the default) shows the forecast: under NOW the support running at 07:00, under NEXT 24 H each new support at the flag line or more with its percentage, and the chance of leaving the ICU. The team sets the flag line ("Flag beds at 50% · 25% · 10%", default 25%, kept on the device; from Dema's design). Each bed has one status, worked out on the board from the five predictions and that line: **Worsening** (new life support at the next step above the line), **Watch** (at the line), **Not improving** (on life support now, leaving under the line, nothing new flagged; coming off support is not forecast), **Leaving** (60% or more unless changed) or **Steady**. "Worry first" at the top lists the Worsening rooms, then the Not improving rooms. The page is titled Lookahead, "ICU forecast · next 24 hours"; the unit name is a label beside it.

**Unit strain** (its own tab; one line of it sits in the header): "N patients on now · +M expected (range)" and a one-word yardstick. With a capacity set ("Set tonight's capacity": life-support patients tonight's staffing covers, optionally ventilators free) the word is ON TRACK (p90 at or under it), TIGHT (p90 over it) or SHORT (the median over it), named "vs tonight's staffing"; otherwise USUAL, BUSY or VERY BUSY "vs a typical day". Then a card for IMV, vasopressor, CRRT and leaving the ICU (the role's card first): on now, expected with its range, and the beds behind the count. "Deaths expected" is one small line. There is no shift brief.

**Staffing** (D23): a nurse is 1:1 for a patient on CRRT or on two or more vasoactive infusions and 1:2 for everyone else; one respiratory therapist covers six ventilated patients. Unit strain shows nurses and RTs needed now and in the next 24 hours, against the number on shift when entered.

**Updates**: "Update the unit" (header) and "Update this room" (room page) start a forecast for the unit or one room, for the role chosen (never a name), at most once every 20 minutes. The last forecast stays on screen and is marked "updating"; the numbers refresh in place; a refusal reads "Updated 12 minutes ago. You can update again at 13:17." The 07:00 morning run is the scheduled update. The chat can start an update only when asked ("update room 12", "update the unit"). In the demo the replay clock is advanced and labelled ("Demo clock: recorded patients, time advanced N h").

## Product Principles

1. Answer the shift question first: what will we be short of, when, and how sure are we.
2. Uncertainty is the product: every forecast number carries its range.
3. Local and private by construction: say where it ran and that data stayed on site.
4. Honest evidence: measured numbers only; projections are labelled.
5. Decision support, never a treatment recommendation.
6. Plain words and one number format: chances are whole percentages ("23%", "<5%"); every figure explains itself on hover (J.C., 2026-11-14 evening; replaces natural frequencies).

## Accessibility & Inclusion

Readable at a glance in a dim unit and on a projector: large numerals, status not by color alone, WCAG AA contrast.

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

ICU Horizon ("From bench to bedside"; working name ICU-Twin in the backend) makes exactly five predictions for every patient in the ICU, each for the same fixed window, the next 24 hours from 07:00 to 07:00, refreshed daily for 07:00 rounds: ICU discharge (leaves the ICU to a ward or step-down unit), invasive mechanical ventilation (IMV) start, vasopressor start, CRRT start and in-hospital death. The board adds patients up into unit counts with a likely range (8 in 10 outcomes, p10 to p90). Nothing else is forecast on the board (no hypotension, no ICU readmission). For each current patient it does one forward pass of a small generative event model and reads its last hidden state with a logistic probe per task, then adds the patients up. Success: the ICU team of nurses and physicians, pharmacy, respiratory therapy and the bed manager can act on the next day's staffing and beds before the unit is short, and a judge can see the scaling result in one glance.

## Positioning

Built for the small or rural ICU: one unit, scarce ventilators and CRRT machines, transfers that take hours, no data-science team and no cloud contract. Two desk-size local machines run the whole product, and patient data never leaves the building. Trained and run on local hardware (MIMIC-IV in CLIF format); a hospital with CLIF-format data can run the same pipeline on its own records.

Local compute for a busy ICU. Right-sized models (tens of millions of parameters) trained on open, credentialed CLIF-format data run on hardware the hospital owns, so patient data never leaves the site. Contrast: Epic Curiosity is cloud-hosted inside Cosmos and predicts per patient; ICU-Twin forecasts unit-level demand for the next 24 hours, locally. Tagline in use: "Compute buys certainty." Promise: "One forecast per unit, on hardware you own."

## Operating Context

- Built and demonstrated at the CIQ x NVIDIA Local AI Hackathon (Chicago, 2026-11-14/15) by team7: five people, two Lenovo ThinkStation PGX (NVIDIA GB10) nodes, Fuzzball 4.3 orchestration, five-minute demo.
- Data: MIMIC-IV-Ext-CLIF (credentialed), moved once into the team7 persistent volume `mimic_clif`. Per-patient views use the open MIMIC-IV demo, synthetic patients, or (approved, local only) real MIMIC-IV room views, marked "MIMIC-IV · local" in the top strip.
- Real-world use is a daily forecast for 07:00 morning rounds (started at 06:30 so it is ready at 07:00, and on request) on local hardware from a live CLIF feed.

## Capabilities and Constraints

- 25 beds (50-bed stretch only if fast); one fixed horizon for all five predictions, the next 24 h (07:00 to 07:00), set by `backend/icutwin/config/winnowing.yaml` (`horizon_after_threshold_s` 86400); five predictions only.
- Outputs: a bed board (each bed now, then the next 24 h, with the events at the team's thresholds and no bed status), a unit strain tab (patients on life support now, more expected, with p10/p50/p90, against tonight's staffing or a typical day), a room page; each team reads its own line first: pharmacy (vasopressor starts), respiratory therapy (IMV starts), ICU team of nurses and physicians (CRRT starts and deaths), bed manager (ICU discharges to ward or step-down); backtest against what happened after time T and against persistence; training speed 1 vs 2 nodes.
- ICU-only cohort; each forecast starts 24 h after ICU arrival (`docs/DECISIONS.md` D3). Current ICU patients only: new arrivals need a separate model (open).
- Screens: the bed board and unit strain tabs (command center), per-room drill-down and room chat for the open stage ward (a real MIMIC-IV ward only when the server is started with `--real-ward` on the local cluster, D19; counts only otherwise), each room's five predictions with the last events the model read (D4 to D7).
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

**Death never marks a bed.** Death is one of the five predictions, and it is shown in two places only: as one unit count ("Deaths expected 1 (0 to 3)" in the line above the beds, and the Deaths card on Unit strain) and as a row in an opened bed. A bed tile never carries a death icon, a death percentage or a red figure for death, and death never ranks a bed (D13, D26, D27). **Level** on an opened bed's rows is High, Medium or Low against the flag line.

**Bed board** (the default tab; Dema's final design, D25, with the refinements in D27): a **Now / Next 24 h** switch chooses when. **Now** shows only current sickness: the life support running at 07:00 on each bed, weighted by how many supports are running; a bed on two or more is Critical; nothing forecast is shown. **Next 24 h** (the default) shows the forecast: a **See first** row with the three beds most likely to need a new life support, then every bed with the support running at 07:00 and, under NEXT 24 H, each event at or above its threshold in a circle with its percentage (a new ventilator, vasopressor or CRRT, or discharge). The team sets the thresholds in Settings ("Flag beds at 40% · 20% · 10%", default 20%, and one per event; kept on the device). The standard lines are 20% watch, 40% worsening and 60% leaving (D13, D14, D26), and a visible "Reset to standard" returns to them. A bed has no status word and no status colour: its person figure turns red and pulses when a new life support is at its threshold. The page is titled ICU Horizon, "next 24 hours"; the unit name is a chip beside it.

**Unit strain** (its own tab; one line of it sits above both tabs): what is short against the unit's machines, "Deaths expected" as one count, the three highest-risk beds, "N on life support now · +M new expected in 24 h" and a one-word yardstick (ON TRACK, TIGHT or SHORT against tonight's staffing when it is set; otherwise USUAL, BUSY or VERY BUSY against a typical day). Then one card per event: Deaths (the unit count and its range only), Ventilator, Vasopressor, CRRT and Leave the ICU, each with on now, free machines, the beds at the threshold and the unit forecast with its range. A card reads SHORT when the flagged beds outnumber the free machines and AT LIMIT when they equal them.

**Staffing** (D23): a nurse is 1:1 for a patient on CRRT or on two or more vasoactive infusions and 1:2 for everyone else; one respiratory therapist covers six ventilated patients. The page does not draw staffing (D25); the backend works it out and the API and the chat report it.

**Updates**: "Update the unit" (header) and "Update this bed" (in an opened bed) start a forecast for the unit or one bed, at most once every 20 minutes. The last forecast stays on screen while a strip shows the job's steps (Queued, Running on the GPU, Scoring, Done); when the new forecast lands the numbers refresh in place and the strip reads "Updated 07:42". A refusal reads "Not started. Updated 12 minutes ago. You can update again at 13:17."; a run that is stopped or brings no new forecast says so in plain words. The 07:00 morning run is the scheduled update. The chat can start an update only when asked ("update bed 12", "update the unit"). In the demo the replay clock is advanced and labelled.

## How this forecast was made

A native model, trained from scratch on our own token vocabulary; one forward pass per patient, then small classifiers on its last-layer summary; how Fuzzball ran it and what is only written so far. Full account, with sources: [`README.md`](README.md#how-this-forecast-was-made). One page for judges: [`ONE_PAGER.md`](docs/ONE_PAGER.md). Accuracy and its limits: [`RESULTS.md`](docs/RESULTS.md).

## Product Principles

1. Answer the shift question first: what will we be short of, when, and how sure are we.
2. Uncertainty is the product: every forecast number carries its range.
3. Local and private by construction: say where it ran and that data stayed on site.
4. Honest evidence: measured numbers only; projections are labelled.
5. Decision support, never a treatment recommendation.
6. Plain words and one number format: chances are whole percentages ("23%", "<5%"); every figure explains itself on hover (J.C., 2026-11-14 evening; replaces natural frequencies).

## Accessibility & Inclusion

Readable at a glance in a dim unit and on a projector: large numerals, status not by color alone, WCAG AA contrast.

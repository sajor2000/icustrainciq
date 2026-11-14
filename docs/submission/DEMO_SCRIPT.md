# Lookahead: five-minute demo script

Team7 · CIQ × NVIDIA Local AI Hackathon · Chicago · Nov 14–15, 2026

- **Speaker:** [FILL: who speaks]. **Driver (clicks):** [FILL: who drives].
- The judges are engineers, not clinicians. Say each clinical word in plain words once, in passing, then use it.
- Lines marked **[FILL]** depend on results that do not exist yet. Fill them or skip them. Never improvise a number.

## Words to explain once

| Word | Say it like this |
|---|---|
| ICU | the hospital unit for the sickest patients |
| Life support | machines and drugs that keep a patient alive |
| Ventilator | a breathing machine |
| Vasopressor | a drug that holds blood pressure up |
| CRRT | continuous dialysis: a machine doing the kidneys' work |
| Unit strain | how stretched the unit is |

## Before the demo

From `docs/ARCHITECTURE.md` "Before the live demo" and `backend/docs/COMPUTE_PLAN.md` section 7. The cluster owner does this; nobody else starts a workflow.

1. Training has finished (`t7-build`). No `t7-*` workflow is queued or running except `t7-twin`. [FILL: model status]
2. `t7-fit` has saved the classifiers ("probes").
3. The 25 demo patients are on the volume.
4. `t7-twin` is up with three services running: Nemotron, board server, dispatcher.
5. One unit forecast has landed. Write down the seconds from button to board: [FILL: forecast time].
6. On the board, check both tabs, Now and Next 24 h, one room page and one chat question.
7. Press "Update the unit" at least 20 minutes before the slot, not later. The button refuses a second update of the same scope inside 20 minutes.
8. Role is "ICU nurse (charge)". "Flag beds at" is 25%. Day board, not Night board. Chat closed.
9. Set capacity once: Unit strain → "Set tonight's capacity" → the unit's ventilator and CRRT totals → "Save capacity". [FILL: the two totals used on stage]
10. Laptop fallback is running in a second window (below), zoomed to match.

## Tabs to pre-open, in this order

| # | Tab | URL |
|---|---|---|
| 1 | Live board | [FILL: the board's Fuzzball endpoint, from `fuzzball workflow endpoints <twin-id> board web`] |
| 2 | Live board, Unit strain | tab 1 URL + `#view=strain` |
| 3 | Diagram: the button to the job | `docs/diagrams/trigger.png` |
| 4 | One-sheet | `docs/submission/one-sheet.pdf` |
| 5 | Laptop fallback | `http://localhost:8000/mockups/command-center.html#synthetic` |

Fallback server, from the repo root: `python3 -m http.server 8000`.

Deep links that work on both the live board and the fallback: `#when=now` (Now view), `#view=strain` (Unit strain), `#room=20` (one room), `#night` (Night board).

Room numbers and percentages below are from the demo data (`#synthetic`). On the live board, use the room that is actually first under "Worry first" and read the numbers on screen. [FILL: the live room number]

## Run of show

| Time | On screen | Click | Say |
|---|---|---|---|
| 0:00 | One-sheet (tab 4), top half | nothing | "An ICU is the hospital unit for the sickest patients. Life support keeps them alive: a breathing machine, drugs that hold blood pressure up, a dialysis machine. A small or rural hospital has only a few of these machines. If three patients need a breathing machine tonight and two are free, one is transferred hours away, and the staff find out when it happens. That hospital has no data-science team and no cloud contract for patient data. Lookahead tells them at 7 am, on two machines the hospital owns." |
| 0:30 | Live board (tab 1), Bed board | the **Now** side of the **Now \| Next 24 h** switch | "This is the unit at 7 am. Every tile is a bed. Now shows only what is running: this patient is on a breathing machine and a blood-pressure drug, this one is on nothing. This part is not a prediction. It is read straight from the chart tables." |
| 1:00 | same | point at the header line: "N on life support now" | "Ten patients on life support this morning. That is today's workload. The question is tomorrow's." |
| 1:15 | Bed board | **Next 24 h** | "Same beds, next 24 hours. Each bed reads left to right: what is on now, then what may start, as a percentage. And one status word per bed: Worsening, Watch, Not improving, Leaving, Steady." |
| 1:35 | Bed board, top row | point at **Worry first** | "The team does not read 25 tiles. Worry first puts the beds to see before rounds at the top. Room 20 has no life support now and a 43% chance of needing a blood-pressure drug by tomorrow morning." |
| 1:55 | Bed board | **Flag beds at** → **10%**, then back to **25%** | "The team chooses how sensitive the board is. At 10% more beds are flagged. At 25% fewer. It is their line, not ours." |
| 2:15 | Room page | the room 20 card under Worry first | "One room. Five predictions for this patient: breathing machine, blood-pressure drug, dialysis, leaving the ICU, and death. Next to them, the last 12 hours of the chart, the events the model read. Death is a plain row. It never colours a bed." |
| 2:40 | Room page | **All rooms** (back link) | (no words) |
| 2:45 | Unit strain | the **Unit strain** tab | "Now add the patients up. Unit strain is how stretched the unit will be. Five on a breathing machine now, two more expected, and the range beside it. The unit owns six. The card says SHORT, and it names the beds behind the number. That is the transfer call, a day early." |
| 3:05 | Unit strain | **Set tonight's capacity** (open it, show the three fields, close it) | "The charge nurse types in how many machines the unit has. That is the only setup." |
| 3:15 | Unit strain | **Update the unit** (header) | "This button starts a real job on the cluster. The board never touches a GPU itself." If the board refuses ("Updated N minutes ago. You can update again at HH:MM"), say: "It refuses a second run inside 20 minutes, by design," and go straight to the diagram. |
| 3:25 | Diagram (tab 3) | nothing | "The board asks a small dispatcher service. The dispatcher starts a CIQ Fuzzball workflow: a check, one pass of our model on a GPU, then scoring. Fuzzball places it on the free GPU, writes the results to a volume, and the board redraws. The same job runs by itself at 7 am every day. [FILL: 'It takes about N seconds.'] Patient rows stay on Fuzzball volumes inside these two machines." |
| 3:50 | Live board (tab 1) | nothing; show the "updating" tag, or the new "Updated HH:MM" | "The last forecast stays on screen while the new one runs." |
| 4:00 | Bed board | the **Ask Lookahead** button (bottom right), then the suggested question **"Who should we worry about first?"** | "Anyone on the team can ask in plain words. This answer comes from the second model, and it names the rooms. Click a room number and you are there." |
| 4:20 | Chat open | **Close** (the X) | (no words) |
| 4:30 | One-sheet (tab 4), the dark diagram | point at the two model boxes | "Two models, two jobs. The patient model we trained ourselves, on these two Lenovo machines. It reads a patient's chart as a sequence of events, the way a language model reads words. At 7 am we run it once per patient and keep the output of its last layer: one vector that summarises the patient. Then five small classifiers, fitted on past patients with known outcomes, turn that vector into the five percentages. One pass per patient, no simulating thousands of futures. The chat model is NVIDIA Nemotron 3 Nano, used as it is, served with vLLM. It predicts nothing. It answers by calling tools that read the forecast. One knows ICU data. The other knows language." |
| 4:50 | One-sheet, bottom | point at "What the second machine unlocks" | "The second machine is what makes this work. Training uses both GPUs. In service, the chat keeps one GPU and each forecast takes the other, so the board never goes dark. [FILL: training time on 1 GPU against 2.] [FILL: held-out accuracy, one sentence.] Fuzzball runs all of it. Nothing leaves the building." |
| 5:00 | One-sheet | stop | "Lookahead. Thank you." |

Timing notes: the 4:30 block is 20 seconds at a steady pace; rehearse it. If you are behind at 3:15, skip the 1:55 threshold beat next time, not the Fuzzball beat.

## Fallback plan

**Tier 1: the cluster is up, but the forecast is slow or the update is refused.**

- Do not wait on stage. The last forecast stays on screen and is marked "updating".
- Say: "The job is running on the cluster now. The board keeps the last forecast until the new one lands." Show the diagram (tab 3), carry on to the chat.
- If the button refused the update: read the refusal aloud. It is the 20-minute guard working.
- If the chat does not answer: "The chat model is not answering. The board does not depend on it." Carry on; the forecast is the product.

**Tier 2: the cluster or the network is unavailable.**

- Switch to tab 5, the laptop copy with `#synthetic`. The badge in the header reads "Demo data".
- Say it plainly, first: "The cluster is not reachable from this room, so this is the same page on my laptop with made-up patients. Nothing you see now is a model prediction."
- Every click in the run of show works there. "Update the unit" and the chat are simulated on the page in this mode. Say so: "On the laptop the update and the chat are scripted. On the cluster they start a Fuzzball job and call Nemotron."
- Use the diagram and the one-sheet for the 3:15 and 4:30 beats as written.

## Three questions judges are likely to ask

| Question | Answer |
|---|---|
| **Privacy: where does patient data go?** | "Nowhere. Patient rows live on Fuzzball volumes on the two machines. The browser and the chat model see room numbers, counts and percentages. GitHub holds code only. The names on screen are made up." |
| **How accurate is it? Is it validated?** | "It is a research prototype trained on MIMIC-IV, a public research dataset, in CLIF format. It has not been tested prospectively and it is not a medical device. [FILL: 'On patients the model never saw, …' one measured sentence, or: 'Held-out numbers come out of the classifier fit; we will not quote one until we have measured it.']" |
| **Why local? Why not a cloud API?** | "A rural hospital often has no cloud contract for patient data and no team to run one. Two desk-size machines it owns need no contract and no connection. And a model this small does not need more: one pass per patient on one GPU." |

Also be ready for: "Did you fine-tune Nemotron?" → "No. It is used as it is. We trained only the patient model." And: "Is this trained on this hospital's patients?" → "No. Trained and run on local hardware, on MIMIC-IV in CLIF format. A hospital with CLIF data can run the same pipeline on its own records."

## What not to claim

- No accuracy, AUROC, calibration, speed, speed-up or tokens-per-second figure that is not written in `FILL_IN.md` as measured.
- Not "validated", not "clinically tested", not "a medical device", not "recommends treatment". It is for unit planning; the care team makes clinical decisions.
- Not "trained on this hospital's patients". Say "trained and run on local hardware (MIMIC-IV in CLIF format)".
- Not "we trained two models" and not "we fine-tuned Nemotron". One model trained by us; one NVIDIA model used as it is.
- Not "real patients on screen" unless the header tag says "MIMIC-IV · local". Names are always made up.
- Not "it explains why". The board shows the events the model read, not reasons.
- Not "it ran end to end on the cluster" until it has. [FILL: confirm before the slot]
- Not "open source" as a licence claim: the code is public on GitHub and built on open-source tools; the repo has no licence file yet.
- "Not improving" is worked out on the page from the five predictions. Coming off life support is not forecast.

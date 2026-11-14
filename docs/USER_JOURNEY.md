# User journeys: the 07:00 ICU morning

The board exists for one moment: **07:00 morning rounds**, when the ICU team plans the day. The forecast is ready before rounds (the dispatcher starts it at 06:30) and covers every patient who has been in the ICU at least 24 hours. "Next 24 h" means 07:00 today to 07:00 tomorrow; Day 2 and Day 3 run 07:00 to 07:00.

Everything a user sees is a count with an 80% range, or one stage-ward room's sampled futures. No real patient rows ever reach the board (see `docs/DECISIONS.md` D6).

## Charge nurse: staffing for the day (06:45 to 07:15)

1. **06:45, before rounds.** Opens the board on the unit workstation. The header says the forecast is for 07:00 rounds and when it ran. The default tab is **Next 24 h**.
2. **Scans the margin.** Reads the team rows top to bottom: ICU team (deaths), pharmacy (vasopressor starts), respiratory therapy (ventilator, NIPPV, high-flow starts), bed manager (net beds). Each row: big median, 80% range bar, and where a capacity is set, the free count and a status word.
3. **Sees a TIGHT row.** "Ventilator starts 2, range 0 to 4, 3 free: TIGHT." Decides to ask for a second respiratory therapist for the night shift and tells the bed manager.
4. **Scans the room board.** 25 room magnets, shaded by each room's highest risk. Notes the three darkest rooms for rounds.
5. **Checks Day 2.** Switches tabs to see whether tomorrow is worse; plans float coverage.
6. **Reads the shift brief** (AI-drafted from the counts, labelled) and takes it to rounds.

What the frontend must make true: the shift question (what will we be short of, when, how sure) is answered within ten seconds, without scrolling on a 1440 px screen and with one scroll on a phone.

## Attending physician: the room they worry about (07:00 rounds)

1. **During rounds** opens room 14 (a stage-ward patient) from the board.
2. **Reads the drawer.** Risks per horizon for each event; the room's 100 sampled futures on a 3-day timeline, with marks where the chosen event happens inside the horizon.
3. **Picks "Ventilator"** and reads "in 31 of 100 futures, next 24 h" and "what most often came before it, in those futures": rising lactate, norepinephrine start, FiO2 at or above 0.6.
4. **Reads what the model read**: the room's last 12 hours of events.
5. **Asks the chat**: "Room 14: is intubation likely in the next 24 hours?" Nemotron answers from that room's futures and the counts, says it is model evidence, not a cause, and gives no treatment advice.
6. **Decides with the team.** The board never recommends a treatment.

What the frontend must make true: every risk shows its evidence (count of futures, preceding events, recent past) and its limits, in plain words.

## Pharmacy (07:15)

Opens the board, reads the pharmacy row: vasopressor starts, median and range. Pre-mixes norepinephrine for the busy case. Optional: asks the chat "how many vasopressor starts on Day 2?".

## Respiratory therapy (07:15)

Reads the respiratory therapy rows: ventilator, NIPPV and high-flow starts, and the ventilator free count. Preps circuits and machines; staffs for the TIGHT case.

## Bed manager (07:30 and through the day)

Reads beds freed (net) for the next 24 h and Day 2. Plans ED boarding, step-down transfers and elective surgery holds. Knows arrivals from the ED or OR are outside the forecast (the row says "not forecast").

## Midday: something changed (any role)

1. A nurse or physician thinks the morning forecast is out of date (a sick admission, a code).
2. Picks their role ("I am ICU nurse") and presses **Rerun forecast**, or types "rerun the forecast" in the chat.
3. The board says "Started t7-forecast-1114-1302 for ICU nurse; the board updates when it finishes", or explains why not ("a forecast is still running", "last run was under 20 minutes ago").
4. A few minutes later the counts refresh.

What the frontend must make true: one obvious way to rerun, the reason when it cannot, and the role (never a name) recorded with the run.

## Night shift

Switches to the **Night board** (charcoal ground, chalk ink) for a dim unit. Same layout, same words.

## Judges (five-minute demo)

See the board at 07:00 framing, open a room, ask the chat, watch the agent or a nurse start a forecast, and read the run strip: which Fuzzball workflow ran and on how many GPUs (shown as "pending run" until a real run supplies numbers).

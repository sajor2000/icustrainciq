# User journeys: the 07:00 ICU morning

The board exists for one moment: **07:00 morning rounds**, when the ICU team plans the day. The forecast is ready before rounds (the dispatcher starts it at 06:30) and covers every patient who has been in the ICU at least 24 hours. The one horizon is "Next 24 h": 07:00 today to 07:00 tomorrow.

Everything a user sees is a count with an 80% range, or one stage-ward room's five predictions. No real patient rows ever reach the board (see `docs/DECISIONS.md` D6).

## Charge nurse: staffing for the day (06:45 to 07:15)

1. **06:45, before rounds.** Opens the board on the unit workstation. The header says the forecast is for 07:00 rounds and when it ran. It reads **Next 24 h**.
2. **Reads the first line of the shift brief.** "Ventilators TIGHT 3 (1–5); 3 free" (the caption says the numbers are median and 80% range). That is the answer; the rows below are the evidence.
3. **Checks the unit rows.** As charge nurse (ICU nurse) she sees the rows with a verdict (TIGHT or SHORT); the rest fold. Decides to ask for a second respiratory therapist for the night shift and tells the bed manager.
4. **Reads "Watch first"**: the three highest-risk rooms, as magnets on the board and links in the brief. Notes them for rounds; "Show all 25 rooms" opens the whole unit.
5. **Taps a suggested question** if she wants it in words: "What will we be short of tonight?"; Nemotron answers from the counts.
6. **Takes the three-line brief to rounds** (AI-drafted from the counts, labelled).

What the frontend must make true: the shift question (what will we be short of, when, how sure) is answered within ten seconds, without scrolling on a 1440 px screen and with one scroll on a phone.

## Attending physician: the room they worry about (07:00 rounds)

1. **During rounds** opens room 14 (a stage-ward patient) from the board.
2. **Reads the room page** (its own page; a line at the top keeps the unit verdict in view; previous and next room for rounds). The room's five predictions for the next 24 h, highest first, each as a level word and "about N in 10" (ventilator: about 3 in 10, ...); tasks already on are tags ("VENT", "PRESS"), not percentages; one line says how far to trust them (held-out check).
3. **Reads what the model read**: the room's last 12 hours of events (rising lactate, norepinephrine start, FiO2 at or above 0.6).
4. **Asks the chat**: "Room 14: is intubation likely in the next 24 hours?" Nemotron answers from that room's probabilities and the counts, says it is model evidence, not a cause, and gives no treatment advice.
5. **Decides with the team.** The board never recommends a treatment.

What the frontend must make true: every risk shows its evidence (the held-out check, the recent past) and its limits, in plain words.

## Pharmacy (07:15)

Picks "pharmacy": the vasopressor row comes first, marked "your row"; other teams fold unless something is short. Pre-mixes norepinephrine for the busy case. Optional: taps "How many vasopressor starts?".

## Respiratory therapy (07:15)

Picks "respiratory therapy": the ventilator row comes first, with the free count and status word. Preps circuits and machines; staffs for the TIGHT case.

## Bed manager (07:30 and through the day)

Picks "bed manager": the row of patients leaving the ICU to ward or step-down in the next 24 h comes first. Plans ED boarding, step-down transfers and elective surgery holds. Knows arrivals from the ED or OR are outside the forecast (the row says "not forecast").

## Midday: something changed (any role)

1. A nurse or physician thinks the morning forecast is out of date (a sick admission, a code).
2. Picks their role ("I am ICU nurse") and presses **Rerun forecast**, or types "rerun the forecast" in the chat.
3. The board says "Started t7-forecast-1114-1302 for ICU nurse; the board updates when it finishes", or explains why not ("a forecast is still running", "last run was under 20 minutes ago").
4. A few minutes later the counts refresh.

What the frontend must make true: one obvious way to rerun, the reason when it cannot, and the role (never a name) recorded with the run.

## Cognitive load

The full list is in `FRONTEND_SPEC.md` under "Cognitive load". In short: the verdict comes first, the board shows exceptions only, each role's own row comes first, every row has one number with a range bar and a status word, the board names the top three rooms, the room page is sorted by risk, the chat offers suggested questions, the shift brief is three lines at most, and there is one time window with no tabs.

## Night shift

Switches to the **Night board** (charcoal ground, chalk ink) for a dim unit. Same layout, same words.

## Judges (five-minute demo)

See the board at 07:00 framing, open a room, ask the chat, watch the agent or a nurse start a forecast, then open **The five forecasts** at the foot of the page: every event the model estimates (six for staffing, eight research only), each with its definition and range, and how the forecast was made (model, method, where it ran; "pending run" until a real run supplies numbers).

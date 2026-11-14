# User journeys: the 07:00 ICU morning

Lookahead exists for one moment: **07:00 morning rounds**, when the ICU team plans the day. The forecast is ready before rounds (the morning run) and covers every patient who has been in the ICU at least 24 hours. The one horizon is the next 24 hours, 07:00 to 07:00. "Now" means what is running at the 07:00 cut.

Everything a user sees is a count with a likely range, or one stage-ward room's five predictions. No real patient rows ever reach the board (see `docs/DECISIONS.md` D6).

## Charge nurse: staffing for the day (06:45 to 07:15)

1. **06:45, before rounds.** Opens the board on the unit workstation. The header gives the run time ("Updated 06:58 (unit)").
2. **Reads the strain panel.** "10 patients on life support now, 6 more expected (4 to 9)", and one word beside it: TIGHT vs tonight's staffing. That is the answer; the lines below are the evidence.
3. **Sets tonight's capacity if it is not set.** Opens "Set tonight's capacity", types how many life-support patients tonight's staffing covers (and ventilators free if she knows), saves. The word is now ON TRACK, TIGHT or SHORT against that number, and the panel says "Capacity set 07:12 by ICU nurse (charge)".
4. **Reads "Check first: rooms 20, 12, 7".** The three High rooms by combined chance of new life support. She notes them for rounds; the board shows all 25 rooms with their level word, tags (V, P, C) and OUT where a discharge is likely.
5. **Taps "Summarise the shift"** if she wants it in words; Nemotron answers from the counts.
6. **Decides**: asks for a second respiratory therapist for the night, tells the bed manager.

What the frontend must make true: the shift question (how much life support, and are we covered?) is answered within ten seconds, without scrolling on a 1440 px screen and with one scroll on a phone.

## Attending physician: the room they worry about (07:00 rounds)

1. **During rounds** opens room 14 (a stage-ward patient) from the board, or from "Check first".
2. **Reads the room page** ("Room 14: next 24 hours" and its level; previous and next room for rounds; a line at the top keeps the unit context; its own timestamp). New life support (IMV, vasopressor, CRRT), then Leaving the ICU, then Death, each a level word, a 10-dot array and "about 3 in 10". Supports already running read "On now"; a support that stopped before 07:00 has a faint note.
3. **Reads what the forecast read**: the last 12 hours (rising lactate, a norepinephrine start). "These are what the forecast read. They do not show why something happens."
4. **Asks the chat** ("Ask about this forecast"): "Room 14: what is most likely in the next 24 hours?" Nemotron answers from that room and the counts, and declines treatment questions.
5. **Updates the room** if something changed (a code, a new infusion): "Update this room". The last numbers stay on screen, marked "updating", and refresh in place.
6. **Decides with the team.** The board never recommends a treatment.

## Pharmacy (07:15)

Picks "pharmacy": the Vasopressor line moves to the top of the breakdown ("4 on now · +3 expected (1 to 5)"). Pre-mixes for the busy case. Optional: "How many vasopressor starts?".

## Respiratory therapy (07:15)

Picks "respiratory therapy": the IMV line comes first, and the capacity form takes "ventilators free". Preps circuits and machines; staffs for the TIGHT case.

## Bed manager (07:30 and through the day)

Picks "bed manager": the "expected to leave" line comes first ("10 expected to leave (7 to 12) · arrivals not forecast"). Rooms with the OUT tag are the likely discharges. Plans ED boarding, step-down transfers and elective surgery holds.

## Midday: something changed (any role)

1. A nurse or physician thinks the morning forecast is out of date (a sick admission, a code).
2. Picks their role ("I am") and presses **Update the unit** (or **Update this room**), or types "update the unit" or "update room 12" in the chat. The chat never starts an update unless asked.
3. If the last update was too recent the board says so: "Updated 12 minutes ago. You can update again at 13:17."
4. Otherwise it reads "Updating the unit for ICU nurse (charge). The last forecast stays on screen." A few minutes later the numbers refresh in place and the run line reads "Updated 13:05 (unit)". In the demo it adds "Demo clock: recorded patients, time advanced 6 h".

What the frontend must make true: one obvious way to update, the reason when it cannot, the role (never a name) recorded with the run, and the board never blanks while it runs.

## Cognitive load

The full list is in `FRONTEND_SPEC.md` under "Cognitive load". In short: the answer comes first, one yardstick word that names what it is measured against, each role's line first, tiles carry only a room number, a level word and a few tags, numbers are natural frequencies, the room page has a fixed order, the chat is closed until asked, and there is one time window with no tabs.

## Night shift

Switches to the **Night board** (charcoal ground, chalk ink) for a dim unit. Same layout, same words.

## Judges (five-minute demo)

See the board at 07:00 framing, open a room, ask the chat, press "Update the unit" and watch the numbers refresh and the demo clock advance, then open **The five forecasts** at the foot of the page: each event the model estimates, its definition and range, and how the forecast was made (model, method, where it ran; "Not ready yet" until a real run supplies numbers).

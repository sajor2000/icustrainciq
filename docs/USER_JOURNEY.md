# User journeys: the 07:00 ICU morning

ICU Lookahead exists for one moment: **07:00 morning rounds**, when the ICU team plans the day. The forecast is ready before rounds (the morning run) and covers every patient who has been in the ICU at least 24 hours. The one horizon is the next 24 hours, 07:00 to 07:00. "Now" means what is running at the 07:00 cut.

Everything a user sees is a count with a likely range, or one stage-ward room's five predictions. No real patient rows ever reach the board (see `docs/DECISIONS.md` D6).

## Charge nurse: who to worry about, then staffing (06:45 to 07:15)

1. **06:45, before rounds.** Opens the board on the unit workstation or the wall screen. It opens on the **Bed board**, on **Next 24 h**. To see only how sick the unit is right now she flips the switch to **Now**: each bed shows just the life support running at 07:00, and "Sickest now" lists the beds on two or more supports first. The header gives the run time ("Updated 06:58") and one line of strain ("10 on life support now · +5 new expected in 24 h · USUAL").
2. **Sets how sensitive the board is, if she wants.** "Flag beds at 50% · 25% · 10%" (25% unless changed, remembered on the device): a lower line flags more beds, a higher one fewer; the tiles stay where they are and the counts beside the key change.
3. **Reads "Worry first".** Two groups of bed tiles: **Worsening** (a new life support is likely) and **Not improving** (on life support now, unlikely to leave, nothing new flagged). Each tile leads with the room number, then the patient's name, sex and age ("Ward, M. · M 68"; names in the demo are made up), and reads left to right: what is running now, an arrow, what may start in the next 24 hours, with its chance ("43%").
3. **Opens a room** from the rail for the detail, and notes the rooms for rounds. Below the rail every room is in room order with the same tile, so Watch, Leaving and Steady rooms are one glance away.
4. **Checks cover on the Unit strain tab** (or taps the header line). One word against tonight's staffing or a typical day, and a card per support with the beds behind each count.
6. **Sets tonight's capacity if it is not set.** Opens "Set tonight's capacity", types the ventilators and CRRT machines on the unit (and, if she wants the staffing word, how many life-support patients tonight's staffing covers), saves. A card whose flagged beds outnumber the free machines turns red and reads SHORT, and the header says "Ventilators short by 1". The word is now ON TRACK, TIGHT or SHORT against that number, and the card says "Capacity set 07:12 by ICU nurse (charge)".
6. **Taps Ask** (bottom right), then "Who should we worry about first?" or "Summarise the next 24 hours" if she wants it in words; Nemotron answers from the counts, and room numbers in the answer open that room. Anything she does not recognise on the board (an icon, a bar, a status mark) explains itself on hover or long-press.
7. **Decides**: asks for a second respiratory therapist for the night, tells the bed manager.

What the frontend must make true: "who do we worry about?" is answered in two seconds from the Worry first rail, and "are we covered?" from the header line, without scrolling on a 1440 px screen; on a phone the rail is the first thing under the tabs.

## Attending physician: the room they worry about (07:00 rounds)

1. **During rounds** opens room 14 (a stage-ward patient) from "Worry first" or the room grid.
2. **Reads the room page**: "Room 14", its status (Worsening, Watch, Not improving, Leaving or Steady) and the same Now → Next 24 h strip; previous and next room for rounds; the window ("07:00 to 07:00 tomorrow") and when it was updated. Then New life support (IMV, vasopressor, CRRT), Leaving the ICU and Death, each named in full ("Starts a ventilator (IMV)") with an icon, a level word, a 10-dot array and the percentage ("30%"). On **Now** the page shows only what is running and the last 12 hours. Supports already running read "On now"; a support that stopped before 07:00 has a faint note.
3. **Reads the last 12 hours** (rising lactate, a norepinephrine start).
4. **Asks the chat** (the chip in its header now reads "Room 14"): "Why is this room Worsening?" Nemotron answers from that room and the counts, and declines treatment questions.
5. **Updates the room** if something changed (a code, a new infusion): "Update this room". The last numbers stay on screen, marked "updating", and refresh in place.
6. **Decides with the team.** The board never recommends a treatment.

## Pharmacy (07:15)

Opens the **Unit strain** tab and picks "pharmacy": the Vasopressor card comes first ("6 on now · +2 expected new starts (1 to 4)") with the beds on a vasopressor now and the beds that may start one, each with its percentage. Pre-mixes for the busy case. Optional: "How many vasopressor starts?".

## Respiratory therapy (07:15)

Opens **Unit strain** and picks "respiratory therapy": the IMV card comes first. With the ventilator total set in the capacity form, the card shows how many are free, a bar the length of the total, SHORT or AT LIMIT when it matters, and how many ventilators may free up if likely leavers go. Preps circuits and machines for the beds under "May start".

## Bed manager (07:30 and through the day)

Opens **Unit strain** and picks "bed manager": the Leaving the ICU card comes first ("10 expected to leave (7 to 13)") with the beds likely to leave and the devices they would free ("If these beds leave, they free 2 ventilators, 1 CRRT"). On the Bed board the same rooms have a green border and the bed-with-arrow icon. Plans ED boarding, step-down transfers and elective surgery holds.

## Midday: something changed (any role)

1. A nurse or physician thinks the morning forecast is out of date (a sick admission, a code).
2. Picks their role ("I am") and presses **Update the unit** (or **Update this room**), or types "update the unit" or "update room 12" in the chat. The chat never starts an update unless asked.
3. If the last update was too recent the board says so: "Updated 12 minutes ago. You can update again at 13:17."
4. Otherwise it reads "Updating the unit for ICU nurse (charge). The last forecast stays on screen." A few minutes later the numbers refresh in place and the run line reads "Updated 13:05". In the demo it adds "Demo clock: recorded patients, time advanced 6 h".

What the frontend must make true: one obvious way to update, the reason when it cannot, the role (never a name) recorded with the run, and the board never blanks while it runs.

## Cognitive load

The full list is in `FRONTEND_SPEC.md` under "Cognitive load". In short: who to worry about comes first, every bed reads now then next, NOW and NEXT 24 H are captioned on every bed, a Now / Next 24 h switch shows current sickness without the forecast, icons carry the supports and one word carries the status, ink is now and blue is forecast, strain has its own tab, chances are percentages, every figure has a legend on hover, the room page has a fixed order, the chat is closed until asked, and there is one time window.

## Night shift

Switches to the **Night board** (dark ground, light ink) for a dim unit. Same layout, same words, same icons.

## Judges (five-minute demo)

See the Bed board at 07:00 framing, read Worry first, open a room, switch to Unit strain, ask the chat, press "Update the unit" and watch the numbers refresh and the demo clock advance, then open **How this forecast was made** at the foot of the page: each event the model estimates, its definition and range, and how the forecast was made (model, method, where it ran; "Not ready yet" until a real run supplies numbers).

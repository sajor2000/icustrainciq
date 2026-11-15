# User journeys: the 07:00 ICU morning

ICU Lookahead exists for one moment: **07:00 morning rounds**, when the ICU team plans the day. The forecast is ready before rounds (the morning run) and covers every patient who has been in the ICU at least 24 hours. The one horizon is the next 24 hours, 07:00 to 07:00. "Now" means what is running at the 07:00 cut.

Everything a user sees is a count with a likely range, or one stage-ward room's five predictions. No real patient rows ever reach the board (see `docs/DECISIONS.md` D6).

## Charge nurse: which beds, then the machines (06:45 to 07:15)

1. **06:45, before rounds.** Opens the board on the unit workstation or the wall screen. It opens on the **Bed board**, on **Next 24 h**. To see only how sick the unit is right now she flips the switch to **Now** (or swipes sideways): each bed shows just the life support running at 07:00, and a bed on two or more supports is marked Critical.
2. **Reads the beds.** Each tile leads with a person icon and the bed number, then the patient's name, sex and age (names are generated and fictional), the life support running now, and under NEXT 24 H the events at or above their threshold, each in a circle with its chance: a new ventilator, vasopressor or CRRT, death, or discharge from the ICU. When a new life support or death is at its threshold the person icon turns red and pulses; discharge alone does not. A bed has no status word and no status colour.
3. **Sets how sensitive the board is, if she wants.** The gear opens **Settings**: "Flag beds at 50% · 25% · 10%" and a threshold per event (kept on the device). A lower line shows more events; the tiles stay where they are.
4. **Opens a bed** for the detail: a pop-up with the five predictions, the last 12 hours of vital signs (hourly medians, when the forecast job wrote them) and the last events the model read.
5. **Checks the machines on the Unit strain tab.** The line on top names what is short and the three highest-risk beds; below it there is one card per event (Deaths, Ventilator, Vasopressor, CRRT, Leave the ICU) with on now, free machines, the beds at the threshold ("Predicted new*") and the unit forecast with its range. The Deaths card is a unit count only and lists no bed.
6. **Sets the unit's machines if they are not set.** Settings, Capacity: the ventilators and CRRT machines on the unit (and, if she wants the staffing word, how many life-support patients tonight's staffing covers), Save capacity. A card whose flagged beds are more than the free machines reads SHORT; exactly as many, AT LIMIT. If the save fails the form says "Not saved" and why.
7. **Taps Ask** (bottom right), then "Which beds need attention first?" or "Summarise the next 24 hours" if she wants it in words; Nemotron answers from the forecast, and bed numbers in the answer open that bed. Staffing (nurses and respiratory therapists needed, 1:1 beds) is not drawn on the page; the backend works it out and the chat can report it.
8. **Decides**: asks for a second respiratory therapist for the night, tells the bed manager.

What the frontend must make true: "which beds?" is answered from the red person icons and the highest-risk beds on the line above Unit strain, and "do we have the machines?" from the cards, without hunting on a 1440 px screen or a phone.

## Attending physician: the bed they worry about (07:00 rounds)

1. **During rounds** opens bed 14 from the grid or from "Highest-risk beds".
2. **Reads the bed pop-up**: the bed number and name, the Now / Next 24 h switch, previous and next bed; then the five predictions as percentages (starts a ventilator, starts a vasopressor, starts CRRT, leaves the ICU, dies in hospital). A support already running reads as on now, not as a new start.
3. **Reads the last 12 hours**: the vital signs and the events the model read (rising lactate, a norepinephrine start).
4. **Asks the chat** (the chip in its header now reads "Bed 14"): "Why is this bed flagged?" Nemotron answers from that bed and the counts, and declines treatment questions.
5. **Updates the bed** if something changed (a code, a new infusion): "Update this bed". The last numbers stay on screen, marked "updating", and refresh in place.
6. **Decides with the team.** The board never recommends a treatment.

## Pharmacy, respiratory therapy, bed manager (07:15 to 07:30)

All three open the **Unit strain** tab. Pharmacy reads the Vasopressor card (on now, the beds that may start one, each with its percentage) and pre-mixes for the busy case. Respiratory therapy reads the Ventilator card: with the ventilator total set, it shows how many are free, a bar the length of the total, SHORT or AT LIMIT when it matters, and how many may free up if likely leavers go. The bed manager reads "Leave the ICU to ward or step-down": the beds likely to leave and the machines they would free. The page has no role picker; the board acts as the charge nurse.

## Midday: something changed (any role)

1. A nurse or physician thinks the morning forecast is out of date (a sick admission, a code).
2. Presses **Update the unit** (or **Update this bed**), or types "update the unit" or "update bed 12" in the chat. The chat never starts an update unless asked.
3. If the last update was too recent the board says so: "Updated 12 minutes ago. You can update again at 13:17."
4. Otherwise the last forecast stays on screen, marked "updating". A few minutes later the numbers refresh in place and "Last run" shows the new time.

What the frontend must make true: one obvious way to update, the reason when it cannot, the role (never a name) recorded with the run, and the board never blanks while it runs.

## Cognitive load

The full list is in `FRONTEND_SPEC.md` under "Cognitive load". In short: every bed reads now then next, NOW and NEXT 24 H are captioned on every bed, a Now / Next 24 h switch shows current sickness without the forecast, an event appears only at its threshold, and every unit count carries its range.

## Night shift

Opens Settings and picks the dark board for a dim unit. Same layout, same words, same icons.

## Judges (five-minute demo)

See the Bed board at 07:00, read the beds with a red person icon, open a bed, switch to Unit strain, ask the chat, press "Update the unit" and watch the numbers refresh, then open **How this forecast was made** at the foot of the page. The script is [`submission/DEMO_SCRIPT.md`](submission/DEMO_SCRIPT.md).

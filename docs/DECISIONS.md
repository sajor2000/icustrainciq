# Team decisions

> Copied from the backend repo [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin) `docs/DECISIONS.md`; file paths below refer to that repo. That copy wins if they differ.

Decisions the team made out loud, with the reason and who acts. Newest first. If a doc disagrees with a decided row, this file wins until the doc is fixed.

## Saturday Nov 14, morning: model, dashboard, chat, auditability

Source: team discussion on Saturday morning. Summarized here; no recording or transcript is kept in the repo.

### How the model scores risk (shared understanding)

- **Tokens.** Every CLIF event becomes a token: `DOMAIN//concept//bin`. Numbers are not predicted as continuous values; each is binned (`B0`, `B1`, ...), so a height or a lab result is one token such as `VITAL//height//B3`. A time token marks each gap between events (for example a 2-hour gap before the next vitals), and a clock token marks every 4 hours. Events at the same time (a CBC and a BMP drawn together) sit at the same timestamp.
- **The model** is a decoder like an LLM, but its vocabulary is patient events (about 1,200 tokens) instead of words. Its last hidden state gives a probability for every possible next event.
- **Monte Carlo scoring (what the board uses).** From a patient's history, sample many futures (100 by default). A risk is the share of futures in which the event happens: 20 of 100 futures end in death means p = 0.20. More futures give a better-calibrated probability. This is `icutwin-gen-score` and the `_mc_score` columns.
- **Representation scoring (research, not on the board).** A small head reads the hidden state and predicts each outcome directly (`icutwin-rep-score`). It covers Vaishvik's derived labels too.
- The BBJ lab uses a different Monte Carlo variant; we do not use it.

### Decisions

| # | Decision | Status | Why | Who acts |
|---|---|---|---|---|
| D1 | **Death** means in-hospital, all-cause death: the `HOSP//discharge_category//expired` token. | Decided | Same thing whether coded as inpatient death or discharge "expired". | done in config |
| D2 | **Monte Carlo is the scoring method** for every number on the board; representation scoring stays research. | Decided | Sampled futures give counts and ranges for the unit; that is the product. | done |
| D3 | **ICU-only.** The cohort is patients in the ICU, and the prediction time is **24 h after ICU arrival** (not 24 h after the first hospital event). | Decided | The PRD is an ICU product; a day of ICU data per patient. | Vaishvik: the winnower supports "24 h after the stay starts" or "at ICU arrival", not "24 h after ICU arrival"; add that cut (small change in `icutwin/scoring/winnower.py` + `winnowing.yaml`), then rerun winnow. |
| D3a | **Morning rounds at 07:00.** The forecast is ready for 07:00 morning rounds and covers every patient in the ICU at least 24 h at that time; "next 24 h" means 07:00 today to 07:00 tomorrow, and Day 2 and Day 3 run 07:00 to 07:00. | Decided | Rounds are when the ICU team plans the day and staffing. | `t7-forecast.fz` runs before 07:00 (lane 2 schedules it); board labels follow the 07:00 day |
| D9 | **Two triggers for the forecast, both through Fuzzball.** A `dispatcher` service in `t7-twin` (CPU) starts `t7-forecast.fz` at 06:30 daily, ready for 07:00 rounds, and when a nurse or physician presses "Rerun forecast" on the board or types "rerun the forecast" in the chat. Fuzzball 4.3 has no cron, so the service uses the workflow token Fuzzball injects (start/list/stop as team7) and refreshes it daily. Guards: no run while a forecast, burst or build is active (two GPUs); one run per 20 min; the log keeps time, role and workflow id only. | Decided | The board is where the ICU team works; Fuzzball stays the only way work reaches the GPUs. | Lane 2: confirm the cluster web UI address (`FB_UI_URL` in `t7-twin.fz`) so the service can download the CLI; lane 4: board button and chat |
| D4 | **Command-center dashboard** for the ICU team: the charge nurse plans tomorrow (staffing: another nurse, another respiratory therapist), physicians look at the unit and at one room. Unit strain by team stays the main view; add a **per-room drill-down** that shows that patient's sampled futures. | Decided | "What staffing do we need to deliver better care tomorrow?" plus "what is going to happen to room 1?" | Lane 4 (board), lane 3 (per-room data) |
| D5 | **Chat widget on a base model.** A local NVIDIA Nemotron 3 Nano answers plain-English questions about the unit and about a room ("we are worried about intubation in room 1: is that likely?") for doctors, nurses, pharmacists and respiratory therapists. The pitch has both: a model we trained and a base model as an agent. | Decided | Interpretable answers; shows both halves of the NVIDIA story. | Lane 4 |
| D6 | **Privacy line for D4 and D5.** Room-level futures and room-level chat use **only the stage ward** (the openly licensed MIMIC-IV Demo patients, excluded from training). Real MIMIC-IV stays counts-only off the restricted volume: the board and Nemotron never see its rows. | Decided here to make D4 and D5 safe; confirm with the team | Credentialed data never reaches a screen, a slide or the chat; the demo patients are open data. | Lane 3: write a per-room file for the stage ward only; lane 4: read it |
| D7 | **Auditability and traceability:** each risk must trace back to what drove it. | Open | The model is a black box; a probability of death needs reasons a clinician can check. | Lane 3 + Vaishvik, proposal below |
| D8 | **Which of the 14 tasks are shown.** The 14 are Vaishvik's 3 outcome tokens plus 11 derived labels (pressor start, CRRT start, hyperkalemia, anemia, hyponatremia, hypotension and others in `winnowing.yaml`). The board shows the team outcomes (vasopressor, ventilator, NIPPV, high-flow, ICU transfer, death, ward or step-down). | Open: decide at 9:00 whether any label joins the board | Keep the board to what a team prepares for. | Team vote |

### Proposal for D7 (auditability), for the team to accept or change

1. **Show the evidence in the futures.** For a room's risk, list how many of the 100 futures contain the event and, in those futures, the events that most often came just before it (for example rising lactate, then norepinephrine, then intubation). That is a count over sampled futures, not a claim about cause.
2. **Show the recent past.** Next to the risk, list the room's last few hours of events that the model read.
3. **Keep a run record.** Every forecast records the model, config, data snapshot, random seed and time, so any number can be reproduced.
4. **Chat cites its numbers.** Nemotron quotes the counts or futures it used and says when the forecast cannot answer.
5. **Say what it is not.** These are not causal explanations, there are no SHAP values for a generative model here, and the model is not validated prospectively.

Stage-ward rooms only for 1, 2 and 4 (D6).

# Lookahead in one page

*CIQ x NVIDIA Local AI Hackathon, team7. For judges from NVIDIA, CIQ and VAST. Decision support only: not a medical device, not prospectively validated. The board shows staffing and machine needs, not treatments.*

**Category and aim.** Healthcare data science, novel methods (GEM), run locally. The aim is privacy and low investment: a small ICU or smaller hospital on two desk-size machines it owns, with patient data staying on site.

**What it does.** At 07:00 rounds, each ICU patient who has been in the ICU at least 24 hours gets up to five predictions for the next 24 hours: leaves the ICU, starts a ventilator, a vasopressor or CRRT (kidney dialysis), dies. Six small classifiers feed the five (ward plus step-down is "leaves the ICU"). Patients are added up into unit counts with a likely range (8 in 10).

**The model.** The team calls it GEM (the repo says Gemma4 and Nemotron). We trained it from scratch on MIMIC-IV-Ext-CLIF patient timelines, written as sequences of events (a lab, a drug start, a transfer) over our own vocabulary of about 1,200 tokens. No pretrained weights from Google or NVIDIA, no fine-tuning. We borrowed the layer pattern of NVIDIA Nemotron 3.5 Bolt E4B, not a copy: at size m (about 35M parameters), 16 layers, every sixth one full attention, the rest sliding-window. The plan was 3 epochs; the model we use is an early checkpoint, about 60% of a run, because the runs were stopped.

**From chart to prediction.**
1. The patient's last 4,096 events before the cut become a list.
2. GEM reads the list once. It does not write out the next 24 hours. It keeps a summary of the patient so far: the hidden state.
3. A probe, a small classifier, reads that summary and gives a chance for each question. Each was trained on past stays, using what really happened in the next 24 hours.
4. Patients are added up.

We first tried about 100 sampled futures per patient and dropped it for one pass.

**Results.** Held-out AUROC is 0.77 to 0.93 across the six classifiers, on retrospective MIMIC-IV, one dataset. Which checkpoint was scored is not stated. Backtest against persistence and GB10 run times: Not ready yet.

**Fuzzball 4.3 on two Lenovo ThinkStation PGX (NVIDIA GB10).**
*Ran:* data copied in through the team-only object cache onto a persistent volume; a two-node training run, stopped early; packaging of a checkpoint with a passing load test.
*Built to run, not yet run:* a forecast workflow (one GPU, then CPU); a service workflow holding Nemotron 3 Nano (chat) on the other GPU, the board on port 8080 and a dispatcher that starts the forecast for 07:00 rounds and on "Update the unit". The dispatcher's use of Fuzzball's injected token (4.3 has no built-in cron) is design to confirm on the cluster.

**Privacy.** Real MIMIC-IV stays counts-only by default; real-ward views are allowed locally under the team's data agreement. Rooms shown by default are the open MIMIC-IV Demo ward.

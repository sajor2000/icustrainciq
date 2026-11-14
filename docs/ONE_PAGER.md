# Lookahead in one page

*CIQ x NVIDIA Local AI Hackathon, team7. For judges from NVIDIA, CIQ and VAST. Decision support only; research prototype on retrospective data.*

**Category and angle.** Healthcare data science, novel methods (GEM), run locally. Privacy and low investment: a small ICU or smaller hospital runs it on two desk-size machines it owns, patient data stays on site, no large cloud or data-science spend.

**What it does.** For 07:00 morning rounds, every patient who has been in the ICU at least 24 hours gets five predictions for the next 24 hours: leaves the ICU, starts a ventilator (IMV), starts a vasopressor, starts CRRT, dies in hospital. The board adds patients up into unit counts with a likely range (8 in 10 outcomes) and shows chances as natural frequencies, for example "3 in 10".

**The model: native, not fine-tuned.** The team calls it GEM (the repo says Gemma4 and Nemotron). We trained it from scratch, from random weights, on MIMIC-IV-Ext-CLIF patient timelines written as sequences of events (a lab bin, a drug start, a transfer, a clock tick) over our own vocabulary of about 1,200 tokens. It uses no pretrained weights from Google or NVIDIA and is not fine-tuned. We copied only the layer layout of NVIDIA Nemotron 3.5 Bolt E4B (Gemma4 text): five sliding-window layers, then one full-attention layer; grouped-query attention; shared key/value layers; per-layer input embeddings; logit softcapping. Sizes in the config: s (12.3M parameters at a vocabulary of 1,200), m (about 35M), l (about 70M). Training uses m.

**From chart to prediction.** (1) The patient's history up to the cut becomes a list of event tokens. (2) GEM reads the list once. It does not write out the next 24 hours; it forms an internal summary of the patient, the last layer's hidden state at the last event (`extractor.py`). (3) One small logistic probe per question turns that summary into a chance of the event in the next 24 hours; each was fit on past stays, using what really happened in the 24 hours after the cut (`rep_based.py`). (4) Patients are added up into unit counts with a range. We first built a version that generated many possible futures and counted outcomes; we dropped it (D2) because one pass is faster and answers directly.

**How we used Fuzzball 4.3, on two Lenovo ThinkStation PGX (NVIDIA GB10, one GPU each).**
- *Data in:* a tar goes to the team-only object cache (`fb://group/`), then a workflow copies it onto the persistent volume `mimic_clif`.
- *Tokenize:* a CPU job; its log and QC report leave through object-cache egress.
- *Train:* a 2-node `multinode` job, one GPU per node, `torchrun`. A second 2-node job extracts hidden states on both GPUs and fits the probes.
- *Forecast:* `t7-forecast.fz` runs extract (one GPU), then score and aggregate on CPU.
- *Always on:* `t7-twin.fz` holds three services: Nemotron 3 Nano on the other GPU (chat), the board on port 8080 (https endpoint, group scope), and a dispatcher.
- *Clock and rerun:* Fuzzball 4.3 has no cron and no workflow parameters. The dispatcher starts the 07:00 run with the token Fuzzball injects. "Update the unit" posts to the dispatcher, which fills a copy of the Fuzzfile and runs `workflow start`: one run at a time, 20 minutes apart.

**Privacy.** Real MIMIC-IV stays counts-only on restricted volumes. Rooms on the board are the open MIMIC-IV Demo stage ward (decision D6), which never trained the model.

**Results.** Accuracy, backtest and run times: Not ready yet. No `results/bench.jsonl` exists and nothing has been timed on the GB10s.

Repos: sajor2000/icustrainciq (board, backend, docs); vaishvikc/ICU-Twin (tokenizer, model, scoring).

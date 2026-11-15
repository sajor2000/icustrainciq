# The model we trained, and how it makes five predictions

Read this to explain the model to a judge in two minutes. Every fact comes from the team's code (github.com/vaishvikc/ICU-Twin, branch `t7/fb-job5-launch`); the file is named after each claim.

## The short version

We trained our own model to read an ICU chart the way a language model reads text: one event at a time, always guessing the next one. To predict, we don't ask it to write out the future. We read what it is "thinking" about the patient (the hidden state of its last layer, 384 numbers) and give that to six small classifiers. They return five chances for the next 24 hours.

## 1. What the model reads

A CLIF chart becomes a list of events, one token per event, from a fixed vocabulary of **1,231 tokens** (`vocab.yaml` in the model folder). A lab or vital sign value goes into one of ten bins:

| Chart | Tokens |
|---|---|
| 08:00, MAP 62, lactate 7.4, norepinephrine 0.12 | `CLCK//08` · `VITAL//map//B2` · `LAB_RES//lactate//B9` · `MED_CON//norepinephrine//B4` |

A general language model would split the same line into about 14 word pieces; we use 4 tokens.

## 2. How we trained it

| | |
|---|---|
| Task | Guess the next event, plus the time until it (next-token loss, and a time-to-next-token loss at weight 0.25; `icutwin/config/decoder.yaml`) |
| Data | MIMIC-IV in CLIF, split into train, tuning and held-out patients; the demo cohort removed from every split (job 2), checked again before training (job 3) |
| Size | 16 layers, hidden size 384, 6 attention heads, 4,096-event context, **36,232,032 parameters** (job 3.1 load test) |
| Design | The layer pattern of NVIDIA Nemotron 3.5 Bolt E4B (Gemma 4 text): five sliding-window layers then one full-attention layer, shared key/value layers, logit softcapping. Our vocabulary and our sizes; trained from scratch, no pretrained weights |
| Hardware | Both NVIDIA GB10s at once: PyTorch DDP across the two Lenovo machines, as a Fuzzball `multinode` job (job 3) |

Nobody told the model about ventilators or death. It learned the order of ICU events. To guess the next event well, it has to keep track of how sick the patient is and where things are heading.

## 3. The hidden layer, in plain words

As the model reads the chart, each of its 16 layers rewrites its picture of the patient. At the last event it has read, the **last layer's hidden state** is a list of 384 numbers: the model's compressed summary of everything so far, the summary it would use to guess what comes next.

`icutwin/scoring/extractor.py` takes exactly that: one forward pass per patient, `hidden_states[-1]` at the last real token. For training the classifiers, and on the board, the chart is cut **24 hours after ICU arrival** (the winnower's cut, `icutwin/scoring/winnower.py`), so each patient becomes one vector of 384 numbers.

This is called a **linear probe**: a simple classifier trained on top of a frozen model's hidden layer, to see what the model already knows (Alain and Bengio, *Understanding intermediate layers using linear classifier probes*, 2016, [arXiv:1610.01644](https://arxiv.org/abs/1610.01644)). The model's weights do not change.

## 4. From 384 numbers to five predictions

Six probes, one per event (`examples/probe_tasks.yaml`), each a logistic regression: the 384 numbers are standardized, then an L2-regularized logistic regression is fitted with its strength chosen by cross-validated AUROC (`icutwin/scoring/rep_based.py`, estimator `logistic-CV-z`). Each was fitted once (job 4) on past patients, labeled by what really happened in the 24 hours after the cut.

| Probe | Becomes the prediction | Held-out AUROC (95% range) |
|---|---|---|
| ventilator (`RESP//device_category//imv`) | Starts a ventilator | 0.780 (0.747–0.812) |
| vasopressor start (`LABEL//pressor_init`) | Starts a vasopressor | 0.771 (0.739–0.802) |
| CRRT start (`LABEL//crrt_init`) | Starts CRRT | 0.881 (0.850–0.910) |
| to a ward (`ADT//TRANSFER_IN//ward`) | Leaves the ICU | 0.799 (0.790–0.808) |
| to step-down (`ADT//TRANSFER_IN//stepdown`) | Leaves the ICU | 0.885 (0.872–0.898) |
| death (`HOSP//discharge_category//expired`) | Dies | 0.930 (0.912–0.946) |

**Six probes, five predictions:** "leaves the ICU" combines ward and step-down. A patient for whom the event already happened before the cut (already on a ventilator, for example) gets no probability for starting it. AUROC: 0.5 is a coin toss, 1.0 is perfect. Held-out means patients the model and the probes never saw.

## 5. From patients to the unit

`app/aggregate.py` adds the patients' chances into unit counts: the expected number of new ventilators, vasopressors and CRRT starts, departures and deaths, each with an 80% range from the exact Poisson-binomial distribution (patients treated as independent). The board sets them against the machines the unit has.

NVIDIA Nemotron 3.5 Bolt E4B (4-bit, on the llama.cpp server) answers questions about these numbers by calling read-only tools. It does not predict anything.

## 6. Why this design

- **One pass per patient.** Our first design generated about 100 possible futures per patient and counted them. Reading the hidden state once is far cheaper and fits on one GB10 beside the chat model.
- **New predictions are cheap.** A new event needs a new probe, not a new model.
- **Small enough to own.** 36M parameters train from scratch on two desk-side GPUs inside the hospital.

## What to say in one breath

"We trained a small model from scratch to read ICU charts event by event. Its last layer holds a 384-number summary of each patient. Six simple classifiers on that summary give five chances for the next 24 hours, from 0.77 to 0.93 AUROC on patients it never saw, and it all runs on two machines in the building."

## Limits

One hospital's data (MIMIC-IV), retrospective, not prospectively validated. Research prototype, not a medical device; it recommends no treatment.

# Lookahead: the ICU board (frontend)

*The next 24 hours, in one place.* The command-center board for **Lookahead** (backend working name ICU-Twin), team7's project at the CIQ × NVIDIA Local AI Hackathon (Chicago, Nov 14–15, 2026).

**What Lookahead does.** For 07:00 morning rounds, it forecasts every patient who has been in the ICU at least 24 hours: a small transformer trained on local hardware (MIMIC-IV in CLIF format) reads each patient's history in one forward pass, a probe gives the probability of five events in the next 24 hours, and the patients are added up into a **strain panel**: how many patients are on life support now (IMV, vasopressor, CRRT, running at 07:00), how many more are expected, and one word that compares that with tonight's staffing or a typical day. Each bed shows what is running now, what may start, and one status. Pharmacy, respiratory therapy, the ICU team and the bed manager each read their own line first. NVIDIA Nemotron 3 Nano, running locally, answers questions from the counts. Everything runs on two Lenovo ThinkStation PGX (NVIDIA GB10) nodes through CIQ Fuzzball; patient data never leaves them.

**Why it matters: the rural ICU.** A small or rural hospital has one ICU, a few ventilators and CRRT machines, no data-science team and no cloud contract for patient data. When the unit runs short, the nearest help is a transfer hours away, so knowing at 07:00 what the next 24 hours will need is worth the most there. Lookahead is sized for that hospital: one 25-bed unit, two desk-size local machines, nothing in the cloud, and patient data that never leaves the building. The model is trained and run on local hardware; it is trained on MIMIC-IV in CLIF format, and a hospital with CLIF-format data can run the same pipeline on its own records.

**This repo** is the frontend: what the board must do, for whom, and how it should look. The backend (model, Fuzzball workflows, the board server `app/board.py`, the forecast dispatcher) is in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin).

## The board

Synthetic data in the mockup ([`mockups/command-center.html`](mockups/command-center.html)); the same page reads the live API when `app/board.py` serves it. Two tabs. **Bed board**: every bed reads now, then the next 24 hours (solid icons for the ventilator, vasopressor or CRRT running at 07:00, an arrow, outline icons for what may start with its chance, "3 in 10"), with one status per bed (Worsening, Watch, Not improving, Leaving, Steady) and a "Worry first" rail on top. **Unit strain**: patients on life support now, how many more are expected, one word against tonight's staffing or a typical day, and a card per support with the beds behind each count. A room opens its own page; "Update the unit" and "Update this room" start a forecast; "Ask" opens a chat panel beside the board. The cluster cards, bed figures and range bars come from Dema's (deetherese) design on the `alternative` branch.

| Bed board, 1440 px | Unit strain, 1440 px |
|---|---|
| ![Bed board](docs/screenshots/beds-desktop.png) | ![Unit strain](docs/screenshots/strain-desktop.png) |

| Night board | Wall screen, 1920 px |
|---|---|
| ![Night board](docs/screenshots/night.png) | ![Wall screen](docs/screenshots/wall-1920.png) |

| Room page | Chat docked beside the board |
|---|---|
| ![Room page](docs/screenshots/room-page.png) | ![Chat docked](docs/screenshots/chat-docked.png) |

| Phone, bed board | Phone, unit strain | Icons |
|---|---|---|
| ![Phone, bed board](docs/screenshots/beds-phone.png) | ![Phone, unit strain](docs/screenshots/strain-phone.png) | ![Icon family](docs/screenshots/icons.png) |

## How it runs

Nothing is hosted in the cloud. The real app runs on two local Lenovo PGX machines under Fuzzball; a laptop can run a demo copy with synthetic data. The team's guide, with every figure, the endpoint table and the run commands: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

![What runs where](docs/diagrams/hosting.png)

![Technical architecture](docs/diagrams/architecture.png)

![Update the unit, end to end](docs/diagrams/trigger.png)

More figures: [API map](docs/diagrams/api.png), [the 07:00 run](docs/diagrams/sequence.png), [setup and run states](docs/diagrams/lifecycle.png), [how the pieces connect](docs/diagrams/connection.png), [demo ward from CLIF-MIMIC](docs/diagrams/ward.png).

## The charge nurse's day

![Charge nurse journey](docs/diagrams/journey.png)

Every role's journey: [`docs/USER_JOURNEY.md`](docs/USER_JOURNEY.md).

## Run it locally

```bash
python3 -m http.server 8000   # from this repo, then open:
# http://localhost:8000/mockups/command-center.html   (#night, #room=20, #role=pharmacy, #fast, #synthetic)
```

## Start here

| Read | For |
|---|---|
| [`docs/NAMING_AND_WORDING.md`](docs/NAMING_AND_WORDING.md) | product name candidates and the words to use on the board (plain language, human factors) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | the team's guide: what runs where, tech stack, architecture and API figures, how the board starts a Fuzzball job, how to run it locally and on the cluster |
| [`docs/USER_JOURNEY.md`](docs/USER_JOURNEY.md) | the 07:00 morning: charge nurse, physician, pharmacy, respiratory therapy, bed manager, midday rerun, night shift, judges |
| [`docs/INTEGRATION.md`](docs/INTEGRATION.md) | how the board talks to the cluster: the five-operation interface, model output end to end, the chat path, request rules, what the Fuzzball team must provide |
| [`docs/FRONTEND_PLAN.md`](docs/FRONTEND_PLAN.md) | the build plan: decisions, milestones M0 to freeze, `rooms.json` contract, tasks by lane, checks, risks |
| [`docs/FRONTEND_SPEC.md`](docs/FRONTEND_SPEC.md) | screens, data contract (`forecast.json`, `rooms.json`, `/api/runs`, `/api/rerun`, `/api/capacity`, `/api/ask`), states, rules |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | team decisions (ICU-only cohort, 07:00 rounds, probe scoring, five predictions, per-room views on the stage ward only, auditability, the two triggers) |
| [`mockups/command-center.html`](mockups/command-center.html) | the reviewed mockup: open it in a browser (synthetic data, works offline; `#night`, `#room=20` and `#role=pharmacy` deep links) |
| [`DESIGN.md`](DESIGN.md), [`PRODUCT.md`](PRODUCT.md) | the visual system and product context the Impeccable skill reads |
| [`examples/forecast.json`](examples/forecast.json), [`examples/rooms.json`](examples/rooms.json) | a synthetic forecast and stage-ward rooms in the exact shape the board receives |

## Working on the design with Impeccable

This repo is set up for the [Impeccable](https://impeccable.style) design skill: `PRODUCT.md`, `DESIGN.md`, `.impeccable/design.json` and the mockup's direction contract in `.impeccable/surfaces/`. In Claude Code run `/impeccable critique mockups/command-center.html`, `/impeccable polish ...` or `/impeccable shape <new screen>`; it loads this context automatically. The 2026-11-14 Lookahead build passed `impeccable detect` with 0 anti-patterns.

## Rules

- Synthetic or open demo data only in this repo. No patient data, credentials, internal IP addresses or personal paths.
- Every number shows its range (8 in 10 likely outcomes); no percentages on the board; status is never shown by colour alone; decision support, never a treatment recommendation.

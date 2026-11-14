# Lookahead: the ICU board (frontend)

*The next 24 hours, in one place.* The command-center board for **Lookahead** (backend working name ICU-Twin), team7's project at the CIQ × NVIDIA Local AI Hackathon (Chicago, Nov 14–15, 2026).

**What Lookahead does.** For 07:00 morning rounds, it forecasts every patient who has been in the ICU at least 24 hours: a small transformer trained on the unit's own CLIF data reads each patient's history in one forward pass, a probe gives the probability of five events in the next 24 hours, and the patients are added up into a **strain panel**: how many patients are on life support now (IMV, vasopressor, CRRT, running at 07:00), how many more are expected, and one word that compares that with tonight's staffing or a typical day. Each room shows a level and a few tags. Pharmacy, respiratory therapy, the ICU team and the bed manager each read their own line first. NVIDIA Nemotron 3 Nano, running locally, answers questions from the counts. Everything runs on two Lenovo ThinkStation PGX (NVIDIA GB10) nodes through CIQ Fuzzball; patient data never leaves them.

**This repo** is the frontend: what the board must do, for whom, and how it should look. The backend (model, Fuzzball workflows, the board server `app/board.py`, the forecast dispatcher) is in [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin).

## The board

Synthetic data in the mockup ([`mockups/command-center.html`](mockups/command-center.html)); the same page reads the live API when `app/board.py` serves it. All 25 rooms on one screen, each with its room number, a level word (Low, Medium, High, or "On life support") on a white, pale amber or pale red tile, and tags: V, P, C for supports running, OUT for a likely discharge. On the right: the strain panel ("10 patients on life support now · 6 more expected (4 to 9)", with IMV, vasopressor and CRRT lines and a yardstick word), "Check first: rooms 6, 7, 21", and a folded form to set tonight's capacity. A room opens its own page ("Room 12: next 24 hours"); "Update the unit" and "Update this room" start a forecast; "Ask about this forecast" is a chat widget that opens on demand.

| Day board, 1440 px | Night board, 1440 px |
|---|---|
| ![Day board](docs/screenshots/board-day-1440.png) | ![Night board](docs/screenshots/board-night-1440.png) |

| Room page | Phone, pharmacy |
|---|---|
| ![Room page](docs/screenshots/board-room-open-1440.png) | ![Phone, pharmacy](docs/screenshots/board-phone-pharmacy-390.png) |

| Ask about this forecast (chat widget open) |
|---|
| ![Chat widget](docs/screenshots/board-chat-open-1440.png) |

## How it runs

![Where ICU-Twin runs](docs/diagrams/hosting.png)

![How the pieces connect](docs/diagrams/connection.png)

Fuzzball runs the real forecast on the team's two GB10 nodes and serves the live board; this laptop runs an offline demo; Vercel can host a public preview with synthetic numbers. Patient rows stay in the team7 volumes. Steps for the team, the data boundary and the hosting plan: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

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
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | architecture, data boundary, how the team runs it on Fuzzball, hosting plan (local demo, Fuzzball, Vercel), diagrams |
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

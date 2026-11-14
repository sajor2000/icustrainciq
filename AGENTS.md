# Guide for coding agents: Lookahead

Read `HANDOFF.md` first, then `README.md`, `docs/ARCHITECTURE.md` (what runs where), `docs/FRONTEND_SPEC.md` (board contract, screens, states) and `docs/USER_JOURNEY.md`. Decisions: `docs/DECISIONS.md`. Backend: `backend/README.md`. Model training: github.com/vaishvikc/ICU-Twin.

- **Design work:** use the Impeccable skill for any UI change; it reads `PRODUCT.md`, `DESIGN.md` and `.impeccable/`. Stay in the world `DESIGN.md` describes (ink is now, blue is forecast, one drawn icon family); Operate mode: the task beats expression.
- **Board constraints:** one static HTML file, CSS and vanilla JavaScript, no build step, no third-party scripts, works offline. It is served by `backend/app/board.py`; after changing `mockups/command-center.html`, copy it to `backend/app/static/index.html`. Keep the API in `docs/FRONTEND_SPEC.md` and `backend/docs/CONTRACT.md` in step.
- **Backend:** `uv` only. `cd backend && uv run --extra dev --extra model pytest -q` and `ruff check app tests` must pass.
- **Fuzzball:** check syntax against https://docs.ciq.com/fuzzball/4.3, not memory. Never start, stop or delete anything on the cluster without the team's go-ahead. Only the dispatcher starts forecast runs.
- **Data:** never commit patient data, ids, model weights or probes. Real MIMIC-IV rows live only in `backend/data/local/` (git-ignored) and on Fuzzball volumes; the repo is public. Print counts only. Names on the board are invented.
- **Copy:** plain clinical words, no hedging or disclaimers on the board; status words, never colour alone; chances as percentages; no treatment recommendations.
- **Diagrams:** the diagram-design skill; every figure is editable HTML plus a PNG in `docs/diagrams/` and shows where each part runs.
- **Check before done:** open the board at 1440 px, 1920 px and 390 px, day and night, both tabs and both Now / Next 24 h; no console errors.

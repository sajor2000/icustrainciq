# Guide for coding agents: ICU strain board (frontend)

Read `README.md`, then `docs/FRONTEND_SPEC.md` (contract, screens, states, rules) and `docs/USER_JOURNEY.md` (who uses it at 07:00 and why). Decisions: `docs/DECISIONS.md`. Backend: github.com/vaishvikc/ICU-Twin.

- **Design work:** use the Impeccable skill for any UI change; it reads `PRODUCT.md`, `DESIGN.md` and `.impeccable/`. Stay in the picture-board world (`DESIGN.md`: ink is now, blue is forecast, one drawn icon family); Operate mode: the task beats expression.
- **Build constraints:** static HTML, CSS and vanilla JavaScript, no build step, works offline; it is served by `app/board.py` in the backend repo. Keep the API in `docs/FRONTEND_SPEC.md` unchanged.
- **Data:** synthetic or open MIMIC-IV Demo only. Never add real patient data, names, credentials, internal IP addresses or personal paths. Real MIMIC-IV reaches the board as counts only.
- **Honesty:** every number has its 80% range; label synthetic data, drafted text "(mock)", missing runs "pending run"; status words, never colour alone; no treatment recommendations.
- **Check before done:** open `mockups/command-center.html` (and any page you change) at 1440 px and 390 px, day and night; no console errors.

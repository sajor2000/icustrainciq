# Guide for coding agents

Read this if you are a coding agent about to change this repo.

Start with `HANDOFF.md`, then `docs/ARCHITECTURE.md` (what runs where) and `backend/docs/RUNBOOK.md` (how it runs on the cluster). Board contract: `docs/FRONTEND_SPEC.md`. Decisions: `docs/DECISIONS.md`. Model training: github.com/vaishvikc/ICU-Twin; what this repo changed against it, and how to port it: `docs/ICU_TWIN_DELTA.md`.

| Area | Rule |
|---|---|
| Name | The product is ICU Lookahead (D24). Code, workflow, header and file names keep `lookahead` |
| Data | Never commit patient data, ids, model weights or probes. Never open `backend/data/`. MIMIC-IV rows live only there (git-ignored) and on Fuzzball volumes; the repo is public. Print counts only. Names on the board are generated |
| Backend | `uv` only. `cd backend && uv run --extra dev --extra model pytest -q` and `ruff check app tests` must pass |
| Fuzzball | Check syntax against https://docs.ciq.com/fuzzball/4.3, not memory. Never start, stop or delete anything on the cluster without the team's go-ahead. Only the dispatcher starts forecast runs. Edit templates in `backend/fuzzball/`, then render `ready/` with `scripts/make_ready.sh`; do not edit `ready/` by hand |
| Board | One static HTML file, CSS and vanilla JavaScript, no build step, no third-party scripts, works offline. After changing `mockups/command-center.html`, copy it to `backend/app/static/index.html`. Keep `docs/FRONTEND_SPEC.md` and `backend/docs/CONTRACT.md` in step with the API |
| Design | `DESIGN.md` is the one source for colour, type, radius and icons. Use the Impeccable skill for UI changes (Operate mode). No second palette, no web font |
| Copy | Plain clinical words. No hedging or disclaimers on the board. Status words, never colour alone. Chances as percentages. No treatment recommendations |
| Diagrams | Edit `docs/diagrams/make_figures.py`, never the HTML. Every diagram carries the same hosting zone, one caption line and the same colour key; at most 9 boxes. Each must pass the diagram-design skill's `verify_geometry.py` and `self_check.py --offline`. Export a PNG beside the HTML and a night copy to `docs/site/night/` |
| Results | Numbers in `docs/RESULTS.md` come from job 4. The chart reads that table; do not type a number into a figure |
| Project page | `docs/index.html` is the GitHub Pages site, served from `/docs` on `main`; it uses the same tokens |
| Before done | Open the board at 1440 px, 1920 px and 390 px, day and night, both tabs and both Now and Next 24 h. No console errors |

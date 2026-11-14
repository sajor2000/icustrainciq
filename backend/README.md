# Lookahead backend

Everything the Lookahead board needs at run time, copied from the ICU-Twin repo
(branch `t7/integrate-lookahead`). Model training stays in ICU-Twin.

| Folder | What it is |
|---|---|
| `app/board.py` | Board server: serves the page and `/api/forecast`, `/api/rooms`, `/api/runs`, `/api/capacity`, `/api/rerun`, `/api/ask` |
| `app/dispatcher.py` | Starts forecast runs on Fuzzball: 07:00 daily (with retry and catch-up), unit or one room on request |
| `app/chat_agent.py` | "Ask about this forecast" agent (Nemotron 3 Nano via vLLM, tool calling) |
| `app/rooms.py`, `app/aggregate.py` | Build `rooms.json` (per room) and `forecast.json` (unit counts with ranges) |
| `app/clif_now.py` | Life support running at the 07:00 cut, read from raw CLIF tables |
| `app/static/index.html` | The page the board serves (copy of `mockups/command-center.html`) |
| `icutwin/` | Tokenizer, model definition and probe scoring used to score patients |
| `fuzzball/` | `t7-smoke`, `t7-fit`, `t7-forecast`, `t7-twin` workflows (Fuzzball 4.3) |
| `clif_demo/` | Open MIMIC-IV Demo in CLIF format (the default stage ward) |
| `docs/` | `CONTRACT.md` (JSON shapes), `LIVE_DEMO.md` (runbook), `CHAT_AGENT.md` |

## Run locally

```
uv run --extra dev --extra model pytest -q
uv run python app/board.py --forecast ../examples/forecast.json --static ../mockups/command-center.html --port 8080
```

Open http://localhost:8080. Every POST needs `Content-Type: application/json` and `X-Lookahead: 1`.

Real patient data, model weights and probes are never stored in this repo.

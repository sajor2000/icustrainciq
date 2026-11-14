# Frontend plan: from mockup to the live board

Goal: by **15:00 Saturday** the live board on the cluster does what the mockup does, on real forecast counts, and by **11:00 Sunday** (feature freeze) it handles every state in [`FRONTEND_SPEC.md`](FRONTEND_SPEC.md) and passes the checks below. Journeys it must serve: [`USER_JOURNEY.md`](USER_JOURNEY.md). Owner: lane 4 (bed board), with lane 3 (data) and lane 2 (Fuzzball).

## Decisions

| # | Decision | Why |
|---|---|---|
| F1 | **One static page**: `index.html` with inline CSS and vanilla JS, no build step, no framework, no CDN. | Runs offline on hospital-owned hardware; nothing to install in the `python:3.12-slim` board image. |
| F2 | **This repo is the source; the backend vendors a copy.** Each milestone, lane 4 copies `web/index.html` into the backend as `app/static/index.html` by a small PR to [vaishvikc/ICU-Twin](https://github.com/vaishvikc/ICU-Twin). `app/board.py` serves that file at `/` and keeps its JSON API. | The board service reads code from `/store/code` (the backend repo); no runtime download, so it works with the cluster offline. |
| F3 | **The page fetches JSON**; the server never renders HTML. `GET /api/forecast`, `GET /api/runs`, `POST /api/ask`, `POST /api/rerun` (contract in the spec), plus `GET /api/rooms` for the stage ward (F5). | One page for live and mock: with `?mock=1` it reads `examples/*.json` instead, so design work never needs the cluster. |
| F4 | **The mockup is the visual contract.** Build from `mockups/command-center.html` and `DESIGN.md`; any visual change goes through the Impeccable skill (`/impeccable critique`, `/impeccable polish`). | It passed Impeccable's finish review; the team voted the whiteboard world. |
| F5 | **Room views read a separate `rooms.json`, stage ward only.** Real MIMIC-IV never produces this file. | `DECISIONS.md` D6: per-room views and room chat on open demo patients only. |

## Milestones

| When (Saturday unless noted) | Milestone | Done when |
|---|---|---|
| 10:45 | **M0 mock page**: `web/index.html` built from the mockup, reading `examples/forecast.json` with `?mock=1` | the page matches the mockup at 1440 px and 390 px, day and night, no console errors |
| 13:00 | **M1 live counts**: reads `/api/forecast` and `/api/runs`; Ask the board posts to `/api/ask`; Rerun posts to `/api/rerun` | against `t7-twin` on the cluster (smoke-seeded model): counts render, chat answers or says Nemotron is not up, rerun starts a `t7-forecast-*` or shows the reason |
| 15:00 | **M2 rooms**: room drawer reads `/api/rooms` (stage ward) | clicking a room shows its risks per horizon, the 100-futures chart, preceding events and last 12 h, from data, not from the mock generator |
| 17:00 | **M3 states**: every state in the spec's table | each state forced in mock mode and checked by screenshot |
| Sunday 10:00 | **M4 polish**: `/impeccable critique web/index.html`, fix, `/impeccable polish` | Impeccable verdict ship; detector clean or advisories documented |
| Sunday 11:00 | **Freeze**: final copy vendored into the backend, tagged | the demo runs from backend `main` |

## Contract for `rooms.json` (lane 3 writes, stage ward only)

```json
{
  "made_at": "2026-11-14T06:52:00",
  "source": "MIMIC-IV Demo (open), excluded from training",
  "rooms": [
    {
      "room": 7,
      "age_band": "50-59",
      "on_now": ["vasopressor"],
      "risk": {"ventilator": {"24h": 0.07, "48h": 0.11, "72h": 0.13, "stay": 0.13}},
      "futures": {"ventilator": {"n": 100, "hit_hours": [3.5, 11.0, 20.2], "ends_hours": [72, 61, 72]}},
      "preceding": {"ventilator": [{"event": "Lactate above 4, rising", "in": 9, "of": 12}]},
      "recent": [{"hours_ago": 1, "event": "Lactate 3.1 (up from 2.2)"}]
    }
  ]
}
```

Rules: no identifiers (no hospitalization or subject IDs, no dates of birth, no names); `age_band` not age; at most the 100 futures per event; the room number is a display slot, not a bed in a real hospital. Lane 3 adds a CPU step to `t7-forecast.fz` that writes it only for the stage-ward cohort; `app/board.py` serves it at `/api/rooms`.

## Tasks

- [ ] **Lane 4:** M0 to M4 above; vendor PRs to the backend at M1, M2 and freeze.
- [ ] **Lane 4:** `app/board.py` (backend) serves `app/static/index.html` at `/` and `GET /api/rooms` from `/store/rooms.json`; keep the existing API.
- [ ] **Lane 3:** write `rooms.json` for the stage ward in `t7-forecast.fz`; add `examples/rooms.json` here (synthetic) for mock mode.
- [ ] **Lane 2:** confirm the cluster web UI address for the dispatcher (`FB_UI_URL` in `t7-twin.fz`) so Rerun works; tell lane 4 the board's endpoint URL (`fuzzball workflow endpoints list`).
- [ ] **Lane 5:** take the 07:00 journeys into the demo script (charge nurse scan, room 7 drill-down, rerun from chat).

## Checks before each vendor PR

1. Desktop 1440 px and phone 390 px, day and night, room drawer open: screenshots, no console errors.
2. Tile ink at least 4.5:1 on every room (the page computes it; spot-check two rooms per board).
3. Every number shows its 80% range; status words beside colour; SYNTHETIC on mock data; "(mock)" on drafted text; "pending run" where no run produced the number.
4. Nothing from real MIMIC-IV appears per room; questions are never logged.
5. `impeccable detect --json web/index.html` clean, or advisories listed in the PR.

## Risks

| Risk | Fallback |
|---|---|
| Cluster or `t7-twin` not up when M1 is due | keep building in mock mode; the demo can run the page with `?mock=1` |
| `rooms.json` not ready by 15:00 | room drawer runs on the mock generator, labelled SYNTHETIC |
| Nemotron slow or down | the chat says so; counts and rerun still work |
| Dispatcher cannot download the CLI | Rerun shows the reason; the forecast still runs at 06:30 if started by hand or by the agent through MCP |

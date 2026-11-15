# Final Nemotron workflow alignment

Local branch handoff, 2026-11-14: `t7/ui-nemotron-chatbot`, based on current-app
commit `bc4c44df2ae6b7f26cf42ce21e119598d68b0d89`. Changes are isolated in a separate
worktree. Whiskey receives the app/backend branch after local synthetic checks;
this record does not claim a cluster deployment or a completed private-data run.

This integration follows the current Lookahead app in `icustrainciq`, including its
copied backend and reviewed picture-board UI. Its source workspace remains
unchanged. Local code snapshots and synthetic tests are the verification evidence;
this document does not claim a cluster deployment or private-data transfer.

## Contracts retained from the supplied diagrams

The four supplied one-page diagrams (`api.pdf`, `hosting.pdf`, `trigger.pdf`,
`architecture.pdf`) were visually reviewed. They establish:

- The browser talks to the same-origin Python board on port 8080. It does not
  call Nemotron, the dispatcher or Fuzzball directly.
- Read routes remain `/api/forecast`, `/api/rooms`, `/api/capacity`, `/api/runs`.
  Writes remain `/api/ask`, `/api/rerun`, `/api/capacity`; existing request and
  response fields remain compatible. The atomic `/api/context` read is additive.
- Every write uses JSON and `X-Lookahead: 1`; a supplied Origin must match the
  request host. The deployed board enables proxy handling for its HTTPS endpoint.
  Role is advisory attribution, not a login or a separate agent.
- Nemotron is an internal OpenAI-compatible service on port 8000. The dispatcher
  is internal on port 9000, applies its guards, and renders a forecast workflow.
- Probe fitting is a one-time training preparation step. Updates apply saved
  probes after a forecaster forward pass; they do not fit new probes or sample
  patient futures. Nemotron has one GPU and forecast extraction uses the other.
- The browser receives approved clinical projections, not raw source tables,
  source identifiers, model weights, credentials or cluster administration tools.

## Current Claude Code behavior included

The source app has moved beyond the diagrams' older demo-only wording:

1. **Final cohort:** a private file selects 25 real MIMIC hospitalizations and a
   deterministic room mapping. The same mapping feeds Now, forecasting and chat.
2. **Per-patient time:** each stay keeps its event order and elapsed durations.
   Its cut is ICU arrival plus 24 hours plus the selected replay offset. Display
   times use a shared demo day, not comparisons between shifted MIMIC dates.
   A stay that ended before its cut is not presented as a current ICU patient.
3. **CLIF-native Now:** current respiratory support, pressors and CRRT use the
   source CLIF definitions at the cut. Model tokens are not silently substituted
   for missing stop signals.
4. **Forecast pending:** while trained weights/probes are unavailable, real
   observed data can be shown and all five future estimates remain unavailable.
   No zero probability or fabricated prediction stands in for the missing model.
5. **Ready forecasts:** winnowing, one forward pass, last-hidden-state logistic
   probes and exact Poisson-binomial unit aggregation produce the five outcomes.
6. **Current UI:** the approved static frontend is snapshotted for packaging.
   Its Now / Next 24 h controls, Leaving status and percentage convention remain.
   Data-transport changes preserve unknowns and prevent a missing forecast from
   becoming a reassuring Low or Steady status.

## Final deployment names and storage

| Workload | Role |
|---|---|
| `t7-lookahead-prepare` | One CPU-only preparation of the private selected cohort and initial honest pending-model context |
| `t7-lookahead-chat` | Always-on Python board, internal dispatcher and local Nemotron |
| `t7-lookahead-forecast-unit-<time>` | Refresh the bounded selected cohort and publish a coherent room/unit snapshot |
| `t7-lookahead-forecast-roomN-<time>` | Room-triggered refresh of that same bounded cohort, preserving common snapshot identity |

The approved context is published as one atomically replaced JSON envelope with
shared `snapshot_id` and `cohort_id`. Existing API routes expose its projections.
Chat pins one envelope per answer and retrieves only the needed room/unit fields;
it does not scan CLIF or rerun the clinical forecaster for every question.

Real room projections, selected CLIF data, tokens, the private ID file and context
belong on restricted persistent `demo-context` storage. `twin-store` holds code,
model and probes. Nemotron mounts only its verified persistent weights. This is
the intentional storage change from the older diagrams' demo-room files in
`twin-store`.

The model directory remains
`/models/nemotron-3-nano-fp8/9bee19446c0dfd01f356e10979d225b2a6621944`.
The final archive contains source, locked dependency specifications and deployment
definitions only. It contains no clinical extract, roster, context or weights.

The actual-app port retains its renderer, dispatcher guards/auto-stop, fictional
names, unit label and capacity controls. Its GPU allocation follows the existing
Fuzzball review and compute plan: forecast extraction requests GPU1, 8 cores and
48 GB without whole-node exclusivity. Board+dispatcher add 3 cores and 6 GB;
that node peaks at 11 cores/54 GB. Nemotron retains the demo's separate exclusive
node. Placement and peak memory still require the deferred cluster rehearsal.

## Source fingerprints

| Diagram | SHA-256 |
|---|---|
| api.pdf | `d9778204cccd3e90f80ea10062d95bed9552b8b6879d6ef04d19501076850148` |
| hosting.pdf | `27d677d0d853ae6964a9c04a626d581cddbb294adffefe19235c7d15fcdb2f66` |
| trigger.pdf | `222fbfea0a5b4298312dd8d6ce59d822275829f7c3f4323a6d4dcc6d4dfb27b0` |
| architecture.pdf | `711ac8b5e6fbadd15f446afca032f96c21f9f9828ad71b9607501444ce5147fa` |

The current app's D14, D17, D18 and final-cohort implementation guide behavior
where the older diagrams differ. The operator still must verify the private
cohort, volume provisioning, GPU startup and actual model tool calls after the
cluster freeze is lifted.

## Pinned frontend integration

The final bounded refresh uses the current Claude picture-board HTML at source
SHA-256 `0c7302fceeed17d9b7b4a89c0460f7a66672dba2d5f31631b63e870620ae45ff`.
The reviewed integrated frontend is
`c6f121ca4bb53259d815da81ac06617d48f69f4554d320590b50a4a208eece1c`.
The pinned source CSS and HTML shell are byte-for-byte preserved. Its threshold
presets, machine-total capacity controls, revised support cards, risk figures,
percentage format and pending-model opening on Now remain included.

Only JavaScript integration semantics change: a refresh consumes one matching
context envelope; unknown observations retain their unknown state; pending
future estimates remain unavailable; ended patients retain empty, explicit
room slots. Free-machine values are not inferred when support observations are
incomplete. Existing legacy API shapes and POST headers remain compatible.

Verification uses synthetic HTTP contexts and headless rendered-DOM assertions.
It does not establish visual acceptance at every viewport, model inference on
the target GPU, private-cohort correctness or a cluster deployment. The original
Claude checkout is unchanged; later frontend edits are outside this pinned
refresh.

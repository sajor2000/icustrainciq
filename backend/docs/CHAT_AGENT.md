# Shared ICU chat

Lookahead is one assistant for the whole ICU team. The default view is **Whole ICU team**; an optional focus changes ordering and suggested questions. It does not select a different model, patient population, prediction set or permission level. Role labels are advisory attribution, not authentication.

## Prediction contract

The clinical pipeline is:

1. Winnowing defines each patient's prediction cut and the history available before it.
2. The existing ICU-Twin event decoder makes one forward pass.
3. Task-specific logistic probes read its last hidden state to produce the five displayed probabilities: ICU discharge to ward/step-down, IMV start, vasopressor start, CRRT start and in-hospital death.
4. Exact Poisson-binomial aggregation produces unit expected counts and p10/p50/p90 ranges.

Monte Carlo and sampled patient futures are not the board/chat prediction path. Nemotron selects evidence tools and explains the method; it does not create clinical probabilities.

## Answers and tools

`POST /api/ask` accepts `question`, optional `role`, `room` and `seen_made_at`. It returns an answer, publication time when available, and safe tool-name metadata. Clinical answers are rendered from returned evidence in `app/evidence.py`; arbitrary model prose is not a clinical fact source.

| Tool | Evidence |
|---|---|
| `get_unit_forecast(prediction?)` | Five forecast rows, or the selected outcome for a focused question; counts and 80% ranges |
| `get_life_support()` | Observed support and forecast new starts, explicitly separated; unavailable fields remain unknown |
| `get_capacity()` | Entered capacity and free ventilators; missing values are not set |
| `get_room(room)` | Approved room evidence and its source; current support and five probabilities. For a real MIMIC-IV ward: refused ("counts only") unless the board runs with `--real-ward` or `--require-real-data`, and then only for a room the user asked about (the open room or a room number in the question), without clock fields |
| `explain_method(topic)` | Fixed definitions, including the winnowing/last-hidden-state probe pipeline |
| `list_runs()` | Operational status, kept separate from clinical evidence |
| `request_forecast_run(role, scope, room?)` | Explicit update through the configured dispatcher; model arguments cannot supply missing request attribution |

All tool arguments use closed schemas. Boolean, fractional and string room numbers are rejected. Unknown tool names are recorded only as a fixed marker. Oversized results return a valid JSON error rather than a truncated document. An answer without retrieved evidence does not display a model-generated clinical claim.

The system prompt is `SYSTEM_PROMPT` in `app/chat_agent.py`. It distinguishes observed support, future starts, missingness and causal claims. Role emphasis is optional. Client requests keep `chat_template_kwargs.enable_thinking=false`; changing reasoning mode requires actual model evaluation, not stronger-sounding prompt language.

The current app may attach a validated invented display name with `fictional: true`. Chat carries only that bounded display label; names never enter logs. Real identifiers remain excluded.

## Reliability and response UX

- Each question pins its forecast, room and capacity file contents before model calls. A publication during the answer cannot replace its source timestamp or numerical evidence. This is per-request file consistency, not a claim of atomic multi-file/cohort publication.
- A combined room/unit answer requires matching nonempty `snapshot_id` and `cohort_id` in both source documents. Missing or different identities return a specific comparison-unavailable answer; the chat does not infer common membership from room numbers.
- Four tool rounds, at most eight tool calls, 6000 characters per result and a shared 90-second request budget bound the loop. Dispatcher adapters receive the remaining timeout through the `Dispatcher` protocol.
- A later model failure preserves already retrieved evidence. If tools are unsupported or the model is unavailable before evidence retrieval, the board can render an explicitly labelled unit forecast directly; it does not call another unconstrained model path.
- An uncertain update response is labelled unknown and is not dispatched again within that question. Cross-request idempotency and publication verification remain separate dispatcher concerns.
- Replies show a loading state, preserve readable lines, and display publication time separately. Changing optional focus preserves the conversation. The answer heading is neutral; room and unit scope come from the evidence text, not the open page.
- Publication time is not clinical observation freshness. Current support cannot be inferred from a forecast probability or historical-ever flag. New starts are not added to current load to claim future occupancy or staffing shortage.

## Data and verification limits

Real-MIMIC room context reaches the local model only in real-ward mode and only for the room asked about (docs/DECISIONS.md D19); otherwise a real ward is counts-only. External coding agents receive code, synthetic fixtures and aggregate verification only. This patch does not read clinical rows or establish that real room and unit files share a validated roster, cut or immutable publication manifest. That producer contract and its local real-data acceptance remain prerequisites for grounded real-MIMIC comparisons.

Logs contain approved role labels, allowlisted tool names, timing and operational metadata. They do not contain questions, answers, clinical tool bodies or arbitrary model tool-name text. Application logging tests do not establish model-server or proxy logging configuration.

All changes and tests in this patch are local. Fuzzball execution and configuration are frozen at the user's request. No model inference, clinical calibration or real-MIMIC acceptance is claimed by the synthetic software tests.

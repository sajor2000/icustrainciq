# Nemotron chatbot handoff for Whiskey

Branch: `t7/ui-nemotron-chatbot`, based on the current app at `bc4c44d`.
This branch integrates the chatbot into this app's `backend/` and preserves the
latest threshold controls, machine capacity cards, percentages and fictional
display names. The active Claude checkout and shared Fuzzball cluster were left
alone. Start here for chatbot work; the broader app guide is [HANDOFF.md](HANDOFF.md).

## What is implemented

- A private fixed roster selects 25 hospitalizations for Now, forecasts and chat.
  Stable room slots and one atomic JSON publication carry the same `snapshot_id`
  and `cohort_id`. Every chat answer pins one publication.
- Current life support comes from CLIF at each patient's own replay cut. Missing
  observations stay unknown. Ended stays have no current patient or invented risk.
- Missing trained weights or saved probes leave observed Now available and all
  five forecasts pending. A room shows percentages or `No estimate`; unit
  forecasts show counts and 80% ranges.
- Nemotron selects bounded JSON tools. Clinical facts in the reply are rendered
  from approved evidence; unsupported model prose is not a source of numbers.
  The loop caps tool calls, response size and elapsed time. If the model fails,
  available evidence can still be shown.
- One shared chat works for the ICU team. An optional role changes emphasis;
  there is no persona framework. An update requires the user's explicit request.
  Existing browser routes and dispatcher safeguards remain in place.
- Forecasting is winnowing, one forward pass, last hidden state, saved logistic
  probes and exact Poisson-binomial unit counts. Nemotron does not produce the
  clinical predictions. There is no Monte Carlo path in these demo workflows.

## Where to work

| Concern | Files |
|---|---|
| System prompt, JSON tools, bounded model loop | [chat_agent.py](backend/app/chat_agent.py) |
| Answer wording and evidence formatting | [evidence.py](backend/app/evidence.py) |
| HTTP routes, source guard, deterministic fallback | [board.py](backend/app/board.py) |
| Selected-cohort publication and validation | [demo_context.py](backend/app/demo_context.py), [run_cohort.py](backend/scripts/run_cohort.py) |
| Current CLIF state, room and unit projections | [clif_now.py](backend/app/clif_now.py), [rooms.py](backend/app/rooms.py), [aggregate.py](backend/app/aggregate.py) |
| Browser widget | [command-center.html](mockups/command-center.html), identical served copy [index.html](backend/app/static/index.html) |
| Deployment, architecture and operator steps | [LOOKAHEAD_DEMO.md](backend/docs/LOOKAHEAD_DEMO.md), [workflow alignment](backend/docs/CLAUDE_WORKFLOW_ALIGNMENT.md) |

## Run and test locally

```bash
git fetch origin
git switch --track origin/t7/ui-nemotron-chatbot
cd backend
uv sync --extra dev --extra model
uv run --extra dev --extra model pytest -q
uv run ruff check app tests
```

Use a separate worktree if another branch is already in use. The repository's
synthetic examples can start the board without a model or clinical extract:

```bash
uv run python app/board.py --forecast ../examples/forecast.json \
  --static ../mockups/command-center.html --host 127.0.0.1 --port 8080
```

For the approved private runtime, the board uses `--context` and
`--require-real-data`. Preparation and forecasting use the same private roster;
the exact CLI and persistent volume paths are in the deployment guide. Do not
place real data, IDs, tokens, context, weights or probes in Git or a code archive.

## What remains before the live demo

1. When the team lifts the cluster freeze, verify the restricted persistent
   context volume, approved selected-25 extract, private roster and dependencies.
   Prepare the honest Now/pending snapshot once.
2. Start the pinned Nemotron container using the previously downloaded persistent
   model snapshot. Verify actual tool parsing, latency and the context budget.
   Local HTTP tests use a scripted model and do not establish GPU acceptance.
3. Once trained forecaster weights and saved probes are available, run the
   selected-cohort forecast. Check that room and unit replies use that exact
   publication, then test an explicit refresh and recovery from a failed run.

Whiskey can immediately refine question routing and concise response wording in
the two chat modules above. Keep the same evidence boundary and extend the
existing public HTTP tests for any behavior change. Do not add a new agent
framework, role platform or a second prediction pipeline for this single-user
demo.

## Validation

- Full app backend suite: **362 passed**, with two existing tokenizer deprecation
  warnings. Fixtures are synthetic or the repository's open MIMIC-IV Demo;
  private selected-patient files were not read.
- `ruff check app tests` and changed scripts/scoring files passed; whitespace
  checks passed. Both frontend copies are byte-identical.
- **24 visual states passed:** 1440/1920/390 px, day/night, both tabs and
  Now/Next. No layout blockers or JavaScript errors; the browser requested a
  missing favicon, which does not affect app behavior.
- New Fuzzfiles render to YAML and pass offline shell checks. The code-only
  archive has an independently checked file/hash manifest and standalone server
  startup check.

### Standards review

No blocking standards or major maintainability defects. Two optional smells:
context validation/publication share a large module, and some forecast dictionary
structures repeat. Both are reasonable demo tradeoffs; no refactor is required
for this handoff.

### Spec review

No blocking spec findings or handoff-blocking scope creep. Shared publication
identity, unknown/pending/ended handling and the five-probe forecast path match
the requested behavior.

Review totals: Standards, two optional observations and zero blockers; Spec,
zero findings. The private 25-patient runtime and actual Nemotron inference
remain unverified while the cluster is frozen.

# Claude: finish Impeccable setup repair

**Completed.** Claude refreshed both sidecars. The coordinator verified zero
doctor findings in both checkouts, fixed contradictory percentage/color prose
in the app's DESIGN.md, and removed an approximate new preview example. The
application code and both served-page copies are unchanged. Do not repeat this
repair; continue chatbot work from [CHATBOT_HANDOFF.md](CHATBOT_HANDOFF.md).

Requested after the Nemotron chatbot handoff. Work in this isolated
checkout on `t7/ui-nemotron-chatbot`, starting from `64a3399`. The app integration
is already pushed. [CHATBOT_HANDOFF.md](CHATBOT_HANDOFF.md) has the full technical
handoff, 362 passing backend tests and 24 passing UI states.

## Bounded task

Repair the two Impeccable setup findings without changing the current design or
application behavior. `buildPath: "code"` has already been added, preserving the
existing detector settings, in this checkout and the earlier integration checkout
at `../ICU-Twin.t7-ui-agent-grounding`.

Refresh only `.impeccable/design.json` in each checkout against its own existing
`DESIGN.md`, using Impeccable's sidecar-only refresh instructions. Preserve each
`DESIGN.md` byte for byte. Do not just advance `generatedAt`: inspect and repair
stale extension metadata, component examples and narrative. Preserve provenance
and avoid duplicating primitive tokens into the sidecar.

The current app sidecar still says chances are `N in 10`, `never percentages`,
and `Don't show a percentage anywhere`. Those contradict the current app and
the user's explicit preference. Match the current design: whole percentages,
`<5%`, and `No estimate` for missing probabilities. Unit forecasts retain counts
and their 80% ranges. The older sidecar also has obsolete Tight Amber contrast
metadata; compare it against that checkout's normative color token.

## Padding review

The prior hook reported `cramped-padding` for the `.when` segmented-control
wrapper. Its buttons are at least 44px tall and the labels have visible space.
The exact same HTML was reviewed at 390, 1440 and 1920px in both themes. A
file-scoped exception was recorded only in the older integration checkout.
Keep the current design intact. Review an actual spacing defect if you find one;
do not expand this maintenance task into a redesign or add broad suppressions.

## Verification and report

1. Read the installed Impeccable skill and its `reference/document.md` sidecar
   section. This is a sidecar-only refresh; no DESIGN.md replacement is needed.
2. Validate JSON and run `impeccable doctor --json --target` for each named page:
   `mockups/command-center.html` here and `app/static/index.html` in the older
   checkout. Resolve the two named setup findings.
3. Confirm `DESIGN.md`, both current app HTML copies, and application Python
   remain unchanged. Run whitespace checks for your exact changed files.
4. Write a concise report to `/private/tmp/lookahead-claude-setup-result.json`
   with changed files, findings before/after and any remaining blocker. Stop.
   The coordinating Codex session will review and publish the app-branch repair.

## Boundaries

You are not alone in these repositories. Preserve other agents' work. Own only
the two `.impeccable/design.json` files for this task; do not edit runtime code,
DESIGN.md, PRODUCT.md, hooks, permissions, credentials, or unrelated files.
Do not commit, push, merge, rebase or switch branches.

Fuzzball is frozen: no MCP, CLI, network, workflow, volume or GPU operations.
Do not read clinical data, ID lists, `backend/data/`, `clif_demo`, tokens, scores,
weights, probes or any clinical output. This handoff contains code and design
metadata only. Do not edit or restart the user's original Claude session.

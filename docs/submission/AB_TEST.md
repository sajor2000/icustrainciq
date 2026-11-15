# One-pager: A or B

Two versions of the same one-page handout. Same facts, different form. Pick one as a team; both print on one US Letter page.

| | Version A | Version B |
|---|---|---|
| Files | [`one-sheet.html`](one-sheet.html) → [`one-sheet.pdf`](one-sheet.pdf), [`one-sheet.png`](one-sheet.png) | [`one-sheet-b.tex`](one-sheet-b.tex) → [`one-sheet-b.pdf`](one-sheet-b.pdf), [`one-sheet-b.png`](one-sheet-b.png) |
| Look | The board's own look: sans type, cards with the board's icons, two board screenshots, dark architecture band | Editorial: serif headings, a table of the five predictions with 95% ranges, a boxed model explainer, a TikZ pipeline |
| Strength | Shows the product; fastest to scan | Says more about the model and the hidden layer; reads like a short paper |
| Weakness | Less room for the model's detail | No screenshot of the board |
| Rebuild | `uv run --with playwright python docs/submission/make_shots.py export` | `cd docs/submission && tectonic one-sheet-b.tex` (uses fonts on J.C.'s Mac: TeX Gyre Pagella and Arial) |

Both cover, in order: the problem, what we built, why it matters (for ICU doctors and for privacy), the five predictions with held-out AUROC, the model we trained (it speaks EHR, not English; we read its last hidden layer; six small probes), how it runs on CIQ Fuzzball (jobs 1 to 4 train, job 5 runs the board and the Nemotron chat, VAST-backed volumes), and the team.

**Vote:** A, B, or A with one part of B (say which).

Facts come from the team's code (`t7/fb-job5-launch`); see [`../HOW_WE_USED_CIQ.md`](../HOW_WE_USED_CIQ.md) and [`../MODEL_EXPLAINED.md`](../MODEL_EXPLAINED.md). VAST storage is as the team reported it; the workflow files name only the volumes.

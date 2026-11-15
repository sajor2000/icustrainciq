# ICU Horizon logo

The wordmark is the team's design from `docs/brand/icu-horizon-logo.svg` on ICU-Twin branch `t7/demo-icu-horizon-submission` (commit `fe421bb`): "ICU" light, "HORIZON" bold, the O drawn as a rising gold sun on a horizon line, and a heartbeat spike cut through the sun.

## What was fixed

The look is unchanged: the arch, the line, the heartbeat, the colours and every proportion are scaled from the original SVG. Only how it is drawn changed.

| Problem in the original | Fix here |
|---|---|
| Letters were live `<text>` in "Inter, Helvetica, Arial", so the logo changed with each machine's fonts | Letters are outlined as paths (from Arial), so every copy looks the same |
| Each word was forced to a width with `textLength` + `lengthAdjust="spacingAndGlyphs"`, which squashed the letters and left uneven gaps | Each glyph keeps its own width; the gaps around the sun and after "ICU" are the original's |

## Files

| File | Use |
|---|---|
| `icu-horizon-logo-light.svg` / `.png` | Light backgrounds: one-pagers, slides, README |
| `icu-horizon-logo-dark.svg` / `.png` | Dark backgrounds (the PNG has the `#111827` background baked in) |
| `icu-horizon-logo-inline.svg` | Drop-in for the board header: uses `currentColor` and `var(--ink-2)`, so it follows the page's light and night themes; ids `lg-sun`, `lg-cut` as in the current header |
| `icu-horizon-mark-light.svg` / `.png`, `-dark` | The team's mark (sun and heartbeat) unchanged, light and dark: app icon, favicon |
| `make_logo.py` | Rebuilds every file above: `uvx --from fonttools python docs/brand/make_logo.py docs/brand` |

Colours: ink `#0F172A`, "ICU" `#64748B` (the original's values), sun gradient `#FFCB52` to `#F6A313`. Dark version: `#F6F7F9` and `#A3ADBD`.

## Putting it in the board app (ICU-Twin)

Not applied there; the team decides. In `app/static/index.html`, the header logo is the `<svg class="logo" …>` inside `<h1>` (one line, near line 555 on `t7/demo-icu-horizon-submission`). Replace that whole `<svg>…</svg>` with the contents of `icu-horizon-logo-inline.svg`; keep the `<span class="sr">ICU Horizon</span>` after it. The existing `.unit h1 .logo` rule sizes it by height, so no CSS change is needed. Also copy `icu-horizon-logo-light.svg` and `icu-horizon-mark-light.svg` over `docs/brand/icu-horizon-logo.svg` and `docs/brand/icu-horizon-mark.svg` on that branch.

"""ICU Horizon logo, fixed. Same design as the team's docs/brand/icu-horizon-logo.svg (gold gradient sun
dome as the O, heartbeat cut through it, ICU light, HORIZON bold, horizon line), with: letters outlined
(no font dependency), true glyph widths (no textLength stretching), even letter spacing, and the sun sized
as the O so the word reads HORIZON."""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from pathlib import Path
import sys

OUT = Path(sys.argv[1])
REG = TTFont("/System/Library/Fonts/Supplemental/Arial.ttf")
BOLD = TTFont("/System/Library/Fonts/Supplemental/Arial Bold.ttf")
SIZE = 100.0

def run(font, text, x, base, track):
    s = SIZE / font["head"].unitsPerEm
    cmap, gs, hmtx = font.getBestCmap(), font.getGlyphSet(), font["hmtx"]
    out = []
    for i, ch in enumerate(text):
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, base)))
        out.append(pen.getCommands())
        x += hmtx[g][0] * s + (track if i < len(text) - 1 else 0)
    return " ".join(out), x

def build(theme):
    """Proportions taken from the team's original SVG (font-size 30, cap ~21.5): dome 42 wide x 28.6 tall above
    the line, line 6.8 under the baseline, stroke 2.6, cut 8.2, gaps 5.5 around the sun and 16 after ICU."""
    ink, sub = {"light": ("#0F172A", "#64748B"), "dark": ("#F6F7F9", "#A3ADBD")}[theme]
    s = SIZE / BOLD["head"].unitsPerEm
    cap = BOLD["OS/2"].sCapHeight * s
    k = cap / 21.5                         # original units -> ours
    track = 2.2 * k                        # letter gap inside HORIZON
    dome_w, dome_h = 42 * k, 28.6 * k
    base = 10 + (dome_h - 6.8 * k)         # keep the dome top inside the canvas
    line_y = base + 6.8 * k
    x = 6
    icu, x = run(REG, "ICU", x, base, 1.5 * k)
    x += 16 * k
    h, x = run(BOLD, "H", x, base, 0)
    x += 5.5 * k
    sun_l, sun_r = x, x + dome_w; sun_cx = x + dome_w / 2
    x = sun_r + 5.5 * k
    rizon, x = run(BOLD, "RIZON", x, base, track)
    W = x + 6
    dome = f"M{sun_l:.1f} {line_y:.1f}a{dome_w/2:.1f} {dome_h:.1f} 0 0 1 {dome_w:.1f} 0Z"
    c = sun_cx
    pulse = (f"M6 {line_y:.1f}H{c - 7.5*k:.1f}l{2.3*k:.1f} {2.8*k:.1f}L{c:.1f} {line_y - 17.7*k:.1f}"
             f"l{4.6*k:.1f} {24*k:.1f}l{2.5*k:.1f} {-6.3*k:.1f}H{W-6:.1f}")
    H = line_y + 6.3 * k + 10
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" role="img" aria-label="ICU Horizon">
<!-- ICU Horizon wordmark: the team's design, letters outlined from Arial. Built by docs/brand/make_logo.py -->
<defs><linearGradient id="ih-sun-{theme}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFCB52"/><stop offset="1" stop-color="#F6A313"/></linearGradient>
<mask id="ih-cut-{theme}" maskUnits="userSpaceOnUse" x="0" y="0" width="{W:.0f}" height="{H:.0f}"><rect width="{W:.0f}" height="{H:.0f}" fill="#fff"/><path d="{pulse}" fill="none" stroke="#000" stroke-width="{8.2*k:.1f}" stroke-linecap="round" stroke-linejoin="round"/></mask></defs>
<path d="{icu}" fill="{sub}"/>
<path d="{h} {rizon}" fill="{ink}"/>
<path d="{dome}" fill="url(#ih-sun-{theme})" mask="url(#ih-cut-{theme})"/>
<path d="{pulse}" fill="none" stroke="{ink}" stroke-width="{2.6*k:.1f}" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''
    (OUT / f"icu-horizon-logo-{theme}.svg").write_text(svg)
    if theme == "light":   # the board's inline header logo: follows the page's light/night colours
        inline = (svg.replace(f'fill="{sub}"', 'fill="var(--ink-2)"').replace(f'fill="{ink}"', 'fill="currentColor"')
                     .replace(f'stroke="{ink}"', 'stroke="currentColor"').replace('role="img" aria-label="ICU Horizon"', 'class="logo" aria-hidden="true"')
                     .replace(f'width="{W:.0f}" height="{H:.0f}" ', '', 1).replace("ih-sun-light", "lg-sun").replace("ih-cut-light", "lg-cut"))
        (OUT / "icu-horizon-logo-inline.svg").write_text(inline)
    # mark: the team's original mark geometry
    mark = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 72" width="120" height="72" role="img" aria-label="ICU Horizon">
<defs><linearGradient id="ih-msun-{theme}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFCB52"/><stop offset="1" stop-color="#F6A313"/></linearGradient><mask id="ih-mcut-{theme}" maskUnits="userSpaceOnUse" x="0" y="0" width="120" height="72"><rect width="120" height="72" fill="#fff"/><path d="M6 58H51l3 3.500L60 31l6.500 34 3.500-7H114" fill="none" stroke="#000" stroke-width="9.500" stroke-linecap="round" stroke-linejoin="round"/></mask></defs>
<path d="M28 58a32 32 0 0 1 64 0Z" fill="url(#ih-msun-{theme})" mask="url(#ih-mcut-{theme})"/>
<path d="M6 58H51l3 3.500L60 31l6.500 34 3.500-7H114" fill="none" stroke="{ink}" stroke-width="3.500" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
'''
    (OUT / f"icu-horizon-mark-{theme}.svg").write_text(mark)
    print(theme, f"{W:.0f}x{H:.0f}")

for t in ("light", "dark"):
    build(t)

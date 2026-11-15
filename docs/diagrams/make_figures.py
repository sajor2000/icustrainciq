"""Write the ICU Lookahead figures (HTML with inline SVG) in the board's design system.

    python3 docs/diagrams/make_figures.py            # writes docs/diagrams/*.html
    python3 docs/diagrams/make_figures.py --night <dir>   # night-board copies, for the project page's dark theme

Seven diagrams (stack, flow, architecture, workflow, api, trigger, data-boundary) and one chart
(results-auroc, drawn from the held-out table in docs/RESULTS.md; no number is typed here).
Every diagram carries the same hosting zone (ZONE) and the same colour key on its caption line.

Design source: DESIGN.md (section "Diagrams"). Colours, type sizes, radii and the
icon family below are the board's tokens; do not add a colour or a font here.
After writing, check and export each figure with the diagram-design skill:
verify_geometry.py, self_check.py --offline, export_png.py.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---- tokens (DESIGN.md front matter; the same values as mockups/command-center.html :root)
BOARD, BOARD2, SURFACE = "#F3F5F9", "#E8ECF2", "#FFFFFF"
INK, INK2, LINE = "#111827", "#4A5567", "#7A8597"
BLUE, LV_MEDIUM, ON_HIGH = "#1E5BB8", "#D2E2F8", "#FFFFFF"
OK, AMBER, AMBER_BG, AMBER_EDGE = "#18794E", "#8A4B08", "#FCE8C3", "#C27A14"
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
FONT_ATTR = FONT.replace('"', "'")

# ---- icon family, copied from the sprite in mockups/command-center.html (24 grid, 1.75 stroke)
ICONS = {
    "vent": '<path d="M6.5 5.5V3h11v2.5M12 3v9l-2 1.8M12 12l2 1.8"/><path d="M9.6 14.2V9.6c0-1.6-1.9-2-3-.5C4.5 12 3 15.2 3 18.1c0 1.8 1.1 2.9 2.9 2.9 2.2 0 3.7-1.1 3.7-3.2v-3.6z"/><path d="M14.4 14.2V9.6c0-1.6 1.9-2 3-.5 2.1 2.9 3.6 6.1 3.6 9 0 1.8-1.1 2.9-2.9 2.9-2.2 0-3.7-1.1-3.7-3.2v-3.6z"/>',
    "pump": '<g transform="rotate(45 12 12)"><path d="M9 1.5h6M12 1.5v4M8 5.5h8M12 15.5v2.7"/><rect x="9.2" y="5.5" width="5.6" height="10" rx="1"/><path d="M9.2 10.2h2.3"/></g><path d="M4.2 17.6c1.1 1.3 1.8 2.1 1.8 3a1.8 1.8 0 0 1-3.6 0c0-.9.7-1.7 1.8-3z"/>',
    "crrt": '<rect x="8" y="2.5" width="8" height="3.4" rx="1.2"/><rect x="8" y="18.1" width="8" height="3.4" rx="1.2"/><path d="M9.5 5.9v12.2M14.5 5.9v12.2M12 8.5v7"/><path d="M9.5 16H6.5a3 3 0 0 1-3-3V9.5M1.7 11.3 3.5 9.5l1.8 1.8"/><path d="M14.5 8h3a3 3 0 0 1 3 3v3.5M18.7 12.7l1.8 1.8 1.8-1.8"/>',
    "leave": '<path d="M2.5 9.5v10M2.5 16.5H18v3"/><path d="M8.5 16.5v-3.2h6.3a3.2 3.2 0 0 1 3.2 3.2"/><circle cx="5.6" cy="13.6" r="1.5"/><path d="M12.5 6h9M18.5 3l3 3-3 3"/>',
    "person": '<circle cx="12" cy="7.2" r="3.9"/><path d="M4.5 21v-1.4c0-3.5 3.2-5.9 7.5-5.9s7.5 2.4 7.5 5.9V21z"/>',
    "chat": '<path d="M4 5.5h16v10.5H10.5L6 19.8V16H4Z"/><path d="M8 9.5h8M8 12.5h5"/>',
    "beds": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
}

# ---- node kinds: fill, border, title colour, secondary colour (DESIGN.md "Diagrams")
def kinds():
    return {
        "card":     (SURFACE,   LINE, INK,     INK2),     # structure: service, page, step
        "store":    (BOARD2,    LINE, INK,     INK2),     # data store: Fuzzball volume
        "model":    (BLUE,      BLUE, ON_HIGH, ON_HIGH),  # our patient model (one per figure)
        "forecast": (LV_MEDIUM, BLUE, INK,     INK),      # what our model produces
        "nvidia":   (INK,       INK,  BOARD,   BOARD),    # NVIDIA model, used as is
    }


# the night board's values for the same tokens (DESIGN.md, night- prefix)
NIGHT = dict(BOARD="#0E131B", BOARD2="#1C2533", SURFACE="#151C28", INK="#E6E9EF", INK2="#A3ADBD", LINE="#667286",
             BLUE="#8DBBFF", LV_MEDIUM="#1B2E50", ON_HIGH="#0B1220", OK="#6CC59B", AMBER="#F0B466",
             AMBER_BG="#3B2D12", AMBER_EDGE="#C58A2F")
OUT = HERE

# the hosting zone, worded the same on every diagram
ZONE = "2 × Lenovo ThinkStation PGX (NVIDIA GB10) · CIQ Fuzzball 4.3 · patient data stays inside"
# the colour key, the same on every diagram's caption line
# (node kind, words, width of the words in px at 13px)
KEY = (("model", "Our model", 62), ("forecast", "Its forecast", 72), ("nvidia", "NVIDIA model", 84), ("store", "Fuzzball volume", 100))


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def caps_w(s, size=12):
    """Width of a tracked 700 label, generous."""
    return int(len(s) * size * 0.72) + 4


class Fig:
    def __init__(self, slug, w, h, title, desc, eyebrow, heading, big=False):
        self.slug, self.w, self.h = slug, w, h
        self.title, self.desc, self.eyebrow, self.heading = title, desc, eyebrow, heading
        self.t_title, self.t_sub = (18, 14) if big else (16, 13)
        self.zones, self.lines, self.labels, self.nodes, self.foot = [], [], [], [], []

    # -- text
    def text(self, x, y, s, size, weight=400, fill=None, anchor="start", caps=False):
        fill = fill or INK
        ls = ' letter-spacing="0.05em"' if caps else ""
        s = s.upper() if caps else s
        return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" '
                f'font-family="{FONT_ATTR}" text-anchor="{anchor}"{ls}>{esc(s)}</text>')

    # -- containers
    def zone(self, x, y, w, h, label=None, label_dx=20):
        """The hosting boundary. label_dx moves the label along the top edge, clear of a crossing arrow."""
        label = label or ZONE
        lw = int(len(label) * 12 * 0.61) + 20
        self.zones.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="none" stroke="{INK}" '
            f'stroke-width="1.5" stroke-dasharray="6 5"/>'
            f'<rect x="{x + label_dx}" y="{y - 8}" width="{lw}" height="16" fill="{BOARD}"/>'
            + self.text(x + label_dx + 8, y + 4, label, 12, 700, INK, caps=True))

    # -- connectors: orthogonal, corners rounded at r=8
    def arrow(self, pts, color=None, dashed=False, label=None, at=None, side="above"):
        color = color or INK
        d = f"M {pts[0][0]},{pts[0][1]}"
        r = 8
        for i in range(1, len(pts)):
            x, y = pts[i]
            px, py = pts[i - 1]
            if i < len(pts) - 1:
                nx, ny = pts[i + 1]
                ux, uy = (x > px) - (x < px), (y > py) - (y < py)
                vx, vy = (nx > x) - (nx < x), (ny > y) - (ny < y)
                d += f" L {x - ux * r},{y - uy * r} Q {x},{y} {x + vx * r},{y + vy * r}"
            else:
                d += f" L {x},{y}"
        mk = {INK: "ink", BLUE: "blue", INK2: "ink2"}[color]
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        self.lines.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.5"{dash} '
                          f'marker-end="url(#{self.slug}-arrow-{mk})"/>')
        if label:
            cx, cy = at
            w = caps_w(label) + 8
            if side == "above":
                bx, by = cx - w // 2, cy - 8 - 16
            elif side == "below":
                bx, by = cx - w // 2, cy + 8
            elif side == "right":
                bx, by = cx + 8, cy - 8
            else:
                bx, by = cx - 8 - w, cy - 8
            self.labels.append(
                f'<rect x="{bx}" y="{by}" width="{w}" height="16" rx="2" fill="{BOARD}"/>'
                + self.text(bx + w / 2, by + 12, label, 12, 700, BLUE if color == BLUE else INK2, "middle", caps=True))

    # -- nodes
    def icon(self, name, x, y, color, size=22):
        s = size / 24
        return (f'<g transform="translate({x} {y}) scale({s:.4f})" fill="none" stroke="{color}" stroke-width="1.75" '
                f'stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</g>')

    def chip(self, x, y, word, state):
        """The board's status chip: border, fill and a word."""
        fill, edge, ink = {"done": (SURFACE, OK, OK), "todo": (AMBER_BG, AMBER_EDGE, AMBER),
                           "ready": (SURFACE, LINE, INK2)}[state]
        w = caps_w(word) + 12
        return (f'<rect x="{x}" y="{y}" width="{w}" height="22" rx="5" fill="{fill}" stroke="{edge}" stroke-width="1.5"/>'
                + self.text(x + w / 2, y + 15, word, 12, 800, ink, "middle", caps=True))

    def node(self, x, y, w, h, kind, tag, title, subs=(), icon=None, icons=None, chip=None, rows=None):
        fill, edge, c1, c2 = kinds()[kind]
        o = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{edge}" stroke-width="1"/>']
        ty = y + 28
        if chip:
            o.append(self.chip(x + 16, y + 12, tag, chip))
            ty = y + 30
        elif icons:
            for i, n in enumerate(icons):
                o.append(self.icon(n, x + 16 + i * 30, y + 11, c1 if kind != "forecast" else BLUE))
        elif tag:
            o.append(self.text(x + 16, ty, tag, 12, 700, c2, caps=True))
        if icon:
            o.append(self.icon(icon, x + w - 38, y + 12, c1))
        ty += self.t_title + 8
        o.append(self.text(x + 16, ty, title, self.t_title, 700, c1))
        for s in subs:
            ty += self.t_sub + 7
            o.append(self.text(x + 16, ty, s, self.t_sub, 400, c2))
        if rows:
            ry = y + 68
            for left, right, strong in rows:
                o.append(f'<rect x="{x + 12}" y="{ry}" width="{w - 24}" height="32" rx="8" fill="{BOARD if not strong else BOARD2}" '
                         f'stroke="{LINE if not strong else INK}" stroke-width="{1.5 if strong else 0.5}"/>')
                o.append(self.text(x + 24, ry + 21, left, 13, 700, INK))
                o.append(self.text(x + w - 24, ry + 21, right, 13, 400, INK2, "end"))
                ry += 36
        self.nodes.append("".join(o))

    def caption(self, s, y=None, key=True):
        """One caption line; on diagrams the same colour key sits at its right end."""
        y = y or self.h - 20
        self.foot.append(self.text(16, y, s, 14, 400, INK2))
        if not key:
            return
        x = self.w - 16 - sum(w + 38 for _, _, w in KEY) + 18
        for kind, words, w in KEY:
            fill, edge, _, _ = kinds()[kind]
            self.foot.append(f'<rect x="{x}" y="{y - 12}" width="14" height="14" rx="3" fill="{fill}" '
                             f'stroke="{edge}" stroke-width="1"/>')
            self.foot.append(self.text(x + 20, y, words, 13, 400, INK2))
            x += w + 38

    def raw(self, layer, s):
        getattr(self, layer).append(s)

    # -- output
    def html(self):
        s = self.slug
        markers = "".join(
            f'<marker id="{s}-arrow-{n}" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
            f'<polygon points="0 0, 8 3, 0 6" fill="{c}"/></marker>'
            for n, c in (("ink", INK), ("blue", BLUE), ("ink2", INK2)))
        body = "\n      ".join(self.zones + self.lines + self.labels + self.nodes + self.foot)
        return f"""<!DOCTYPE html>
<!-- Design source: DESIGN.md (section "Diagrams"). Written by docs/diagrams/make_figures.py; edit there, then export the PNG. -->
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ICU Lookahead · {esc(self.title)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: {FONT}; background: {BOARD}; color: {INK}; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 3rem 1.5rem; }}
    .frame {{ max-width: {self.w + 40}px; width: 100%; min-width: 0; }}
    .eyebrow {{ font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: {INK2}; margin-bottom: 0.5rem; }}
    h1 {{ font-size: 1.375rem; font-weight: 700; line-height: 1.15; margin-bottom: 1.5rem; }}
    .diagram-container {{ width: 100%; overflow-x: auto; }}
    svg {{ width: 100%; min-width: {self.w}px; display: block; }}
    @media print {{ .diagram-container {{ overflow: visible; }} svg {{ min-width: 0; }} }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">{esc(self.eyebrow)}</p>
    <h1>{esc(self.heading)}</h1>
    <div class="diagram-container">
    <svg viewBox="0 0 {self.w} {self.h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{s}-title {s}-desc">
      <title id="{s}-title">{esc(self.title)}</title>
      <desc id="{s}-desc">{esc(self.desc)}</desc>
      <defs>{markers}</defs>
      <rect width="100%" height="100%" fill="{BOARD}"/>
      {body}
    </svg>
    </div>
  </div>
</body>
</html>
"""

    def write(self):
        (OUT / f"{self.slug}.html").write_text(self.html(), encoding="utf-8")


# =============================================================== hero 1: the stack
def stack():
    f = Fig("stack", 1200, 576, "How we used the hackathon stack",
            "A clinician's browser reaches two Lenovo ThinkStation PGX machines run by CIQ Fuzzball 4.3. Fuzzball services serve the board, start forecast jobs and serve NVIDIA Nemotron 3 Nano on vLLM for the chat on one GPU. A Fuzzball job runs the patient model the team trained on the other GPU. Three Fuzzball volumes hold the patient data, the model and the results.",
            "ICU Lookahead · the hackathon stack", "Two Lenovo machines, CIQ Fuzzball, one NVIDIA model and one of our own", big=True)
    f.zone(264, 48, 920, 456)
    f.node(16, 112, 208, 104, "card", "Clinician", "Browser", ["the board page"], icon="person")
    f.node(304, 112, 376, 104, "card", "Fuzzball services · CPU", "Board server + dispatcher",
           ["serve the board, start forecast jobs"])
    f.node(768, 112, 376, 104, "nvidia", "Fuzzball service · GPU 1", "Nemotron 3 Nano on vLLM",
           ["NVIDIA model, used as is, for the chat"], icon="chat")
    f.node(304, 312, 376, 104, "store", "Fuzzball volumes", "Patient data · model · results",
           ["mimic_clif · twin-store · hfcache"])
    f.node(768, 312, 376, 104, "model", "Fuzzball job · GPU 2", "Our patient model",
           ["trained on both GPUs, runs in minutes"])
    f.arrow([(224, 164), (304, 164)])
    f.arrow([(680, 164), (768, 164)], label="Chat", at=(724, 164))
    f.arrow([(584, 216), (584, 264), (956, 264), (956, 312)], label="Starts a job", at=(770, 264))
    f.arrow([(768, 364), (680, 364)], BLUE, label="Forecast", at=(724, 364))
    f.arrow([(400, 312), (400, 216)], BLUE, label="Reads", at=(400, 264), side="left")
    f.raw("foot", f.text(304, 468, "Patient data never leaves these two machines.", 18, 700, INK))
    f.caption("Fuzzball runs every part as a service, a job or a volume.", 548)
    f.write()


# =============================================================== hero 2: the 07:00 flow
def flow():
    f = Fig("flow", 1200, 328, "What happens at 07:00",
            "Chart data up to 07:00 goes to the team's patient model, which reads each patient once and keeps its last layer; five small classifiers turn that into five chances; the board shows them; the chat answers from the board. Update the unit starts the same run as a Fuzzball job.",
            "ICU Lookahead · the 07:00 run", "From the chart to the board, once each morning", big=True)
    f.zone(8, 40, 1184, 232)
    xs = [20, 256, 492, 728, 964]
    f.node(xs[0], 72, 216, 128, "card", "Each patient", "Chart data",
           ["labs · vitals · drugs", "machines, up to 07:00"], icon="person")
    f.node(xs[1], 72, 216, 128, "model", "Trained by us", "Our patient model",
           ["reads each chart once,", "keeps the last layer"])
    f.node(xs[2], 72, 216, 128, "forecast", None, "Five classifiers",
           ["ventilator, vasopressor", "CRRT, leaving, death"], icons=["vent", "pump", "crrt", "leave"])
    f.node(xs[3], 72, 216, 128, "card", "The board", "Now → Next 24 h",
           ["Bed board", "Unit strain"], icon="beds")
    f.node(xs[4], 72, 216, 128, "nvidia", "NVIDIA, used as is", "Chat",
           ["Nemotron 3 Nano answers", "from the board's numbers"], icon="chat")
    f.arrow([(236, 136), (256, 136)])
    f.arrow([(472, 136), (492, 136)], BLUE)
    f.arrow([(708, 136), (728, 136)], BLUE)
    f.arrow([(944, 136), (964, 136)])
    f.arrow([(836, 200), (836, 232), (364, 232), (364, 200)], INK2, dashed=True,
            label="Update the unit", at=(600, 232), side="below")
    f.caption("One Fuzzball job at 07:00, and again on Update the unit.", 304)
    f.write()


# =============================================================== detail: architecture
def architecture():
    f = Fig("architecture", 1280, 600, "Technical architecture",
            "The board page talks to one service, the board server, which holds the page, the API and the grounded chat agent. The board server asks Nemotron for chat answers and asks the dispatcher to start or report runs. The dispatcher starts the t7-forecast job, which runs the patient model with the probe fitted by job 4, reads the mimic_clif volume and writes forecast files to twin-store, where the board server reads them. Nemotron's weights are on hfcache. A fourth volume, demo-context, arrives with pull request 16.",
            "ICU Lookahead · architecture", "One door into the two machines; everything else stays inside")
    f.zone(288, 32, 976, 496)
    f.node(24, 232, 216, 96, "card", "Clinician's browser", "Board page", ["one HTML file, over HTTPS"], icon="person")
    f.node(328, 72, 240, 96, "nvidia", "GPU 1 · service", "Nemotron 3 Nano", ["NVIDIA, on vLLM, used as is"])
    f.node(328, 232, 240, 96, "card", "CPU · service", "Board server", ["page, API, grounded chat"])
    f.node(328, 392, 240, 96, "card", "CPU · service", "Dispatcher", ["07:00 clock, one run at once"])
    f.node(656, 72, 240, 96, "store", "Volume · read only", "hfcache", ["Nemotron weights"])
    f.node(656, 392, 240, 96, "model", "GPU 2 · job", "t7-forecast", ["our model + job 4's probe"])
    f.node(992, 72, 240, 96, "store", "Volume · restricted", "demo-context", ["the chat's ICU snapshot"])
    f.node(992, 232, 240, 96, "store", "Volume · written", "twin-store", ["code, probe, forecast files"])
    f.node(992, 392, 240, 96, "store", "Volume · read only", "mimic_clif", ["25-patient ward, our model"])
    f.arrow([(240, 280), (328, 280)])
    f.arrow([(448, 232), (448, 168)], label="Asks", at=(448, 200), side="right")
    f.arrow([(448, 328), (448, 392)], label="Run · status", at=(448, 360), side="right")
    f.arrow([(568, 440), (656, 440)], label="Starts", at=(612, 440))
    f.arrow([(656, 120), (568, 120)], label="Weights", at=(612, 120))
    f.arrow([(992, 280), (568, 280)], BLUE, label="Forecast files", at=(780, 280))
    f.arrow([(896, 420), (944, 420), (944, 304), (992, 304)], BLUE, label="Writes", at=(944, 362), side="left")
    f.arrow([(992, 460), (896, 460)], label="Reads", at=(944, 460), side="below")
    f.caption("The board server is the only door in. Ink is a call; blue is the forecast.", 572)
    f.write()


# =============================================================== detail: how to run it on the cluster
def workflow():
    f = Fig("workflow", 1280, 424, "How to run it on the cluster",
            "Three steps by hand: create the twin-store volume once, render the ready workflow files after each code change, and stage job 4's probe once per model after the code is published (scripts/launch.sh --code), because the probe's sidecar command imports the published code. Then one command, scripts/launch.sh --all, runs four Fuzzball workflows in order: t7-code, t7-ward, t7-forecast-unit and t7-twin, and prints the board's link. The team ran this path end to end on the cluster; every step but the per-change render is marked done.",
            "ICU Lookahead · how to run it", "Three steps by hand, then one command")
    xs = [24, 344, 664, 984]
    y1, y2, h = 40, 232, 112
    f.zone(8, 200, 1264, 168, label_dx=312)
    f.node(xs[0], y1, 272, h, "card", "Done · once", "Create twin-store",
           ["fuzzball volume create team7", "twin-store --size 20GB"], chip="done")
    f.node(xs[1], y1, 272, h, "card", "After each code change", "Render ready/",
           ["git push, then make_ready.sh", "at that commit"], chip="todo")
    f.node(xs[2], y1, 272, h, "card", "Done · once per model", "Stage job 4's probe",
           ["after launch.sh --code: to", "/store/train, with its sidecar"], chip="done")
    f.node(xs[3], y1, 272, h, "card", "Ran end to end", "scripts/launch.sh --all",
           ["runs the four workflows below,", "prints the board's link"], chip="done")
    f.node(xs[0], y2, 272, h, "card", "1 · CPU · done", "t7-code", ["publishes code and packages", "to twin-store"], chip="done")
    f.node(xs[1], y2, 272, h, "card", "2 · CPU · done", "t7-ward", ["stages the 25 rooms,", "checks the vocabulary"], chip="done")
    f.node(xs[2], y2, 272, h, "forecast", "3 · GPU 2 · done", "t7-forecast-unit", ["one pass per patient, then", "rooms.json and forecast.json"], chip="done")
    f.node(xs[3], y2, 272, h, "card", "4 · GPU 1 · done", "t7-twin", ["board, dispatcher, Nemotron;", "stays up"], chip="done")
    yc1, yc2 = y1 + h // 2, y2 + h // 2
    for a in range(3):
        f.arrow([(xs[a] + 272, yc1), (xs[a + 1], yc1)])
        f.arrow([(xs[a] + 272, yc2), (xs[a + 1], yc2)])
    f.arrow([(1120, y1 + h), (1120, 176), (160, 176), (160, y2)])
    f.caption("Green ran on the cluster with launch.sh. Amber is by hand; --restart reloads new code.", 400)
    f.write()


# =============================================================== detail: API map
def api():
    f = Fig("api", 1280, 620, "API map",
            "The board page makes four GET calls and three POST calls to the board server. Reads come from files on twin-store and from the dispatcher's status; writes go to the dispatcher to start a run, to Nemotron for a chat answer, and to twin-store for tonight's capacity.",
            "ICU Lookahead · API", "Four reads, three writes, one rule for every POST")
    f.zone(272, 24, 1000, 536)
    f.node(24, 120, 184, 352, "card", "Browser", "Board page", ["same origin only"], icon="person")
    f.node(304, 56, 528, 224, "card", "4 GETs · no headers needed", "Read", rows=[
        ("GET /api/forecast", "unit counts with 80% ranges", False),
        ("GET /api/rooms", "one entry per room", False),
        ("GET /api/capacity", "machine totals, free, staff on shift", False),
        ("GET /api/runs", "next 07:00, running update, last runs", False)])
    f.node(304, 320, 528, 224, "card", "3 POSTs · JSON body", "Write", rows=[
        ("Every POST", "JSON, X-Lookahead: 1, same origin; else 403", True),
        ("POST /api/rerun", "starts one forecast, unit or room", False),
        ("POST /api/ask", "a chat answer, from tool results", False),
        ("POST /api/capacity", "saves tonight's capacity", False)])
    f.node(1000, 56, 240, 88, "store", "Volume", "twin-store", ["forecast, rooms, capacity"])
    f.node(1000, 248, 240, 88, "card", "Inside only · :9000", "Dispatcher", ["starts and reports runs"])
    f.node(1000, 456, 240, 88, "nvidia", "Inside only · :8000", "Nemotron 3 Nano", ["through the chat agent"])
    f.arrow([(208, 168), (304, 168)], label="GET", at=(240, 168))
    f.arrow([(208, 432), (304, 432)], label="POST", at=(240, 432))
    f.arrow([(832, 100), (1000, 100)], label="Reads files", at=(916, 100))
    f.arrow([(832, 236), (916, 236), (916, 276), (1000, 276)], label="Status", at=(874, 236))
    f.arrow([(832, 356), (916, 356), (916, 308), (1000, 308)], label="Run", at=(874, 356), side="below")
    f.arrow([(832, 500), (1000, 500)], label="Chat", at=(916, 500))
    f.caption("GET / is the page. The dispatcher and Nemotron are inside the workflow; no caller check.", 592)
    f.write()


# =============================================================== detail: Update the unit (sequence)
def trigger():
    f = Fig("trigger", 1280, 624, "Update the unit, from click to refreshed board",
            "The board page posts a rerun to the board server, which passes it to the dispatcher. The dispatcher starts the forecast job through Fuzzball. The job writes rooms.json and forecast.json to twin-store. The page polls the run state, then asks for the forecast and the rooms; the board server reads both files, and the board is redrawn.",
            "ICU Lookahead · Update the unit", "One button, one POST, one Fuzzball job")
    xs = [136, 388, 640, 892, 1144]
    f.zone(272, 16, 992, 116, label_dx=12)
    heads = [("card", "Browser", "Board page", "Update the unit"),
             ("card", "CPU · service", "Board server", "checks the POST rule"),
             ("card", "CPU · service", "Dispatcher", "one run, 20 minutes apart"),
             ("model", "GPU 2 · job", "t7-forecast", "our model + job 4's probe"),
             ("store", "Volume", "twin-store", "rooms.json, forecast.json")]
    for x, (k, tag, t, s) in zip(xs, heads):
        f.raw("zones", f'<line x1="{x}" y1="120" x2="{x}" y2="552" stroke="{LINE}" stroke-width="1" stroke-dasharray="3 4"/>')
        f.node(x - 104, 32, 208, 88, k, tag, t, [s])
    msgs = [(0, 1, 176, "POST /api/rerun", INK), (1, 2, 224, "POST /run", INK),
            (2, 3, 272, "fuzzball workflow start", INK), (3, 4, 320, "writes both files", BLUE),
            (0, 1, 384, "GET /api/runs, every 30 s", INK),
            (0, 1, 432, "GET /api/forecast, GET /api/rooms", INK), (4, 1, 480, "reads both files", BLUE),
            (1, 0, 528, "board redrawn", BLUE)]
    for a, b, y, label, c in msgs:
        x1, x2 = xs[a], xs[b]
        f.lines.append(f'<path d="M {x1},{y} L {x2},{y}" fill="none" stroke="{c}" stroke-width="1.5" '
                       f'marker-end="url(#trigger-arrow-{"blue" if c == BLUE else "ink"})"/>')
        lx = min(x1, x2) + 126
        w = int(len(label) * 7.8) + 16
        f.labels.append(f'<rect x="{lx - w // 2}" y="{y - 26}" width="{w}" height="18" rx="2" fill="{BOARD}"/>'
                        + f.text(lx, y - 12, label, 13, 700, BLUE if c == BLUE else INK2, "middle"))
    f.caption("Fuzzball 4.3 workflows take no parameters: the dispatcher fills a copy of t7-forecast.fz.", 600)
    f.write()


# =============================================================== detail: where the patient data lives
def data_boundary():
    f = Fig("data-boundary", 1280, 584, "Where the patient data lives",
            "Patient rows are on the mimic_clif volume and in two restricted folders of twin-store, inside the two machines. The forecast job reads the rows and writes two files of counts and room entries. The board server serves those files to the clinician's browser and passes tool results to Nemotron. GitHub holds code only.",
            "ICU Lookahead · data boundary", "Rows stay on the volumes; only counts and room entries reach a screen")
    f.zone(296, 40, 968, 488)
    f.node(24, 88, 232, 96, "card", "Public", "GitHub", ["code at a pinned commit"])
    f.node(24, 264, 232, 96, "card", "Hospital network", "Clinician's browser", ["counts and room entries"], icon="person")
    f.node(336, 264, 240, 96, "card", "CPU · service", "Board server", ["serves three JSON files"])
    f.node(336, 408, 240, 96, "nvidia", "GPU 1 · service", "Nemotron 3 Nano", ["sees tool results only"])
    f.node(656, 88, 240, 96, "model", "GPU 2 · job", "t7-forecast", ["reads rows, writes counts"])
    f.node(656, 264, 240, 96, "forecast", "On twin-store", "The forecast files", ["counts, ranges, room entries"])
    f.node(976, 88, 240, 96, "store", "Restricted volume", "mimic_clif", ["patient rows, tokens, model"])
    f.node(976, 264, 240, 96, "store", "Restricted folders", "stage/ and train/", ["on twin-store: tokens, scores"])
    f.arrow([(256, 136), (656, 136)], label="Code only", at=(456, 136))
    f.arrow([(976, 136), (896, 136)], label="Rows", at=(936, 136))
    f.arrow([(776, 184), (776, 264)], BLUE, label="Counts", at=(776, 224), side="right")
    f.arrow([(656, 312), (576, 312)], BLUE, label="Files", at=(616, 312))
    f.arrow([(336, 312), (256, 312)])
    f.arrow([(456, 360), (456, 408)], label="Tool results", at=(456, 384), side="right")
    f.raw("foot", f.text(656, 444, "Patient rows never leave the volumes.", 18, 700, INK))
    f.raw("foot", f.text(656, 472, "Names on the tiles are generated. Logs print counts only.", 14, 400, INK2))
    f.caption("Real rooms need --real-ward and stay on these machines (D19).", 556)
    f.write()


# =============================================================== chart: held-out AUROC with 95% ranges
def results_rows():
    """(task, auroc, low, high) from the 'Held-out results' table of docs/RESULTS.md, in its order."""
    text = (HERE.parent / "RESULTS.md").read_text(encoding="utf-8")
    table = text.split("## Held-out results", 1)[1].split("\n## ", 1)[0]
    rows = re.findall(r"^\| ([^|]+?) \|[^|]*\|[^|]*\|[^|]*\| \*\*([0-9.]+)\*\* \(([0-9.]+)[–-]([0-9.]+)\)", table, re.M)
    if len(rows) != 6:
        raise SystemExit(f"expected 6 held-out rows in docs/RESULTS.md, found {len(rows)}")
    return [(t, float(a), float(lo), float(hi), a, lo, hi) for t, a, lo, hi in rows]


def results_auroc():
    rows = results_rows()
    f = Fig("results-auroc", 960, 424, "Held-out AUROC by task, with 95% ranges",
            "Held-out AUROC of the six classifier tasks, highest first: " +
            "; ".join(f"{t} {a} ({lo} to {hi})" for t, _, _, _, a, lo, hi in rows) + ".",
            "ICU Lookahead · model results", "Held-out AUROC by task, with 95% ranges")
    x0, x1, top, step = 208, 688, 76, 44
    px = lambda v: round(x0 + (v - 0.5) / 0.5 * (x1 - x0), 1)
    f.raw("foot", f.text(16, 36, "Held-out AUROC by task, with 95% range", 16, 700, INK))
    bottom = top + step * len(rows) - 12
    for i in range(6):                                    # 0.5 .. 1.0
        v = 0.5 + i / 10
        f.raw("zones", f'<line x1="{px(v)}" y1="{top - 16}" x2="{px(v)}" y2="{bottom}" stroke="{BOARD2}" stroke-width="1"/>')
        f.raw("foot", f.text(px(v), bottom + 20, f"{v:.1f}", 12, 400, INK2, "middle"))
    f.raw("foot", f.text(x0, bottom + 40, "0.5 is a coin toss", 12, 400, INK2))
    f.raw("foot", f.text(x1, bottom + 40, "1.0 is perfect", 12, 400, INK2, "end"))
    for i, (task, v, lo, hi, a, slo, shi) in enumerate(rows):
        y = top + i * step
        f.raw("foot", f.text(x0 - 16, y + 5, task, 14, 400, INK, "end"))
        f.raw("lines", f'<line x1="{px(lo)}" y1="{y}" x2="{px(hi)}" y2="{y}" stroke="{BLUE}" stroke-width="2" stroke-linecap="round"/>')
        for e in (lo, hi):
            f.raw("lines", f'<line x1="{px(e)}" y1="{y - 5}" x2="{px(e)}" y2="{y + 5}" stroke="{BLUE}" stroke-width="2" stroke-linecap="round"/>')
        f.raw("nodes", f'<circle cx="{px(v)}" cy="{y}" r="6" fill="{BLUE}" stroke="{BOARD}" stroke-width="2"/>')
        f.raw("foot", f.text(x1 + 32, y + 5, a, 14, 700, INK))
        f.raw("foot", f.text(x1 + 80, y + 5, f"({slo}–{shi})", 13, 400, INK2))
    f.caption("Dot: held-out AUROC. Bar: 95% bootstrap range, 10,000 samples. Source: the table in docs/RESULTS.md.", 404, key=False)
    f.write()


FIGURES = (stack, flow, architecture, workflow, api, trigger, data_boundary, results_auroc)

if __name__ == "__main__":
    if "--night" in sys.argv:
        OUT = Path(sys.argv[sys.argv.index("--night") + 1])
        OUT.mkdir(parents=True, exist_ok=True)
        globals().update(NIGHT)
    for fn in FIGURES:
        fn()
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.html"))), "in", OUT)

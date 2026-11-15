"""Write the ICU Horizon figures (HTML with inline SVG) in the board's design system.

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
BOARD, BOARD2, SURFACE = "#F6F7F9", "#EEF0F4", "#FFFFFF"   # the board page on t7/fb-job5-launch
INK, INK2, LINE = "#111827", "#5B6474", "#CDD3DC"
BLUE, LV_MEDIUM, ON_HIGH = "#2563EB", "#DBE7FE", "#FFFFFF"
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
        self.t_tag, self.t_label, self.t_zone, self.t_cap = 12, 12, 12, 14
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
        lw = int(len(label) * self.t_zone * 0.68) + 20
        self.zones.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="none" stroke="{INK}" '
            f'stroke-width="1.5" stroke-dasharray="6 5"/>'
            f'<rect x="{x + label_dx}" y="{y - self.t_zone // 2 - 2}" width="{lw}" height="{self.t_zone + 4}" fill="{BOARD}"/>'
            + self.text(x + label_dx + 8, y + self.t_zone // 2 - 2, label, self.t_zone, 700, INK, caps=True))

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
            w = caps_w(label, self.t_label) + 8
            if side == "above":
                bx, by = cx - w // 2, cy - 8 - 16
            elif side == "below":
                bx, by = cx - w // 2, cy + 8
            elif side == "right":
                bx, by = cx + 8, cy - 8
            else:
                bx, by = cx - 8 - w, cy - 8
            self.labels.append(
                f'<rect x="{bx}" y="{by - (self.t_label - 12)}" width="{w}" height="{self.t_label + 4}" rx="2" fill="{BOARD}"/>'
                + self.text(bx + w / 2, by + 12, label, self.t_label, 700, BLUE if color == BLUE else INK2, "middle", caps=True))

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
            ty = y + 14 + self.t_tag
            o.append(self.text(x + 16, ty, tag, self.t_tag, 700, c2, caps=True))
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
        self.foot.append(self.text(16, y, s, self.t_cap, 400, INK2))
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
  <title>ICU Horizon · {esc(self.title)}</title>
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
            "ICU Horizon · the hackathon stack", "Two Lenovo machines, CIQ Fuzzball, one NVIDIA model and one of our own", big=True)
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
            "ICU Horizon · the 07:00 run", "From the chart to the board, once each morning", big=True)
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


# =============================================================== detail: architecture (job 5 path)
def architecture():
    f = Fig("architecture", 1040, 596, "ICU Horizon architecture",
            "On two Lenovo ThinkStation PGX machines run by CIQ Fuzzball 4.3: jobs 1 to 4 train our model once on both GPUs from CLIF data that comes in through the object cache and save it with six probes to the mimic_clif volume. Job 5 loads the code, runs our model and probes on one GPU, and writes rooms.json and forecast.json to the twin-store volume. The board server reads them and serves the clinician's browser; it asks NVIDIA Nemotron 3 Nano on llama.cpp, whose weights are on hfcache, to answer chat questions. The volumes are on VAST storage.",
            "ICU Horizon · architecture", "Train once, then one workflow runs the board")
    f.zone(208, 32, 816, 504)
    c1, c2, c3, w, h = 232, 520, 808, 200, 104
    r1, r2, r3 = 64, 216, 368
    f.node(16, r2, 168, h, "card", "Hospital", "Clinician", ["the bed board,", "in a browser"], icon="person")
    f.node(c1, r1, w, h, "nvidia", "Service · 1 GPU", "Nemotron 3 Nano", ["NVIDIA chat model", "on llama.cpp"])
    f.node(c2, r1, w, h, "store", "VAST volume", "hfcache", ["Nemotron weights"])
    f.node(c1, r2, w, h, "card", "Service · CPU", "Board server", ["page, API, chat tools"])
    f.node(c2, r2, w, h, "forecast", "VAST volume", "twin-store", ["rooms.json,", "forecast.json"])
    f.node(c3, r2, w, h, "store", "VAST volume", "mimic_clif", ["patients in CLIF,", "model, six probes"])
    f.node(c1, r3, w, h, "card", "Fuzzball", "Object cache", ["the only way in or out"])
    f.node(c2, r3, w, h, "model", "Job 5 · 1 GPU", "Our model predicts", ["load, infer, score:", "one pass per patient"])
    f.node(c3, r3, w, h, "card", "Jobs 1–4 · 2 GPUs", "Train once", ["tokenize, train (DDP),", "fit six probes"])
    f.arrow([(184, 268), (c1, 268)])
    f.arrow([(332, r2), (332, r1 + h)], label="Chat", at=(332, 192), side="right")
    f.arrow([(c2, 116), (c1 + w, 116)], label="Weights", at=(476, 116))
    f.arrow([(c2, 268), (c1 + w, 268)], BLUE, label="Forecast", at=(476, 268))
    f.arrow([(620, r3), (620, r2 + h)], BLUE)
    f.arrow([(836, r2 + h), (836, 344), (680, 344), (680, r3)], label="Reads", at=(758, 344))
    f.arrow([(928, r3), (928, r2 + h)], label="Saves", at=(928, 344), side="right")
    f.arrow([(c1 + w, 420), (c2, 420)], label="Code in", at=(476, 420))
    f.arrow([(332, r3 + h), (332, 496), (928, 496), (928, r3 + h)], label="CLIF data in", at=(620, 496), side="below")
    f.caption("Inside the dashed line is CIQ Fuzzball. Blue carries the forecast.", 572)
    f.write()


# =============================================================== print: architecture for the one-page handouts
def architecture_print():
    f = Fig("architecture-print", 1200, 636, "ICU Horizon on CIQ Fuzzball, job by job",
            "Every CIQ Fuzzball 4.3 job and service on two Lenovo ThinkStation PGX workstations, each with one NVIDIA GB10 (20 Arm cores, about 128 GB memory, one GPU). Train once: job 1 copies health records in through the object cache (1 core), job 2 tokenizes them (20 cores, 110 GiB), job 3 trains the GEM, a generative event model, from scratch with PyTorch distributed data parallel on two nodes with one GB10 GPU each, job 3.1 packages and load-tests the checkpoint (2 cores), job 4 embeds patients on two GPUs and fits six probes on CPU; the GEM and probes are saved to the 200 GB mimic_clif VAST volume. Job 5: load checks inputs (2 cores, 8 GB, 7 s), infer runs the GEM and probes for 25 patients on one GPU (8 cores, 48 GB, 35 s), score adds up beds and the unit (4 cores, 16 GB, 33 s) and writes the forecast to the 20 GB twin-store volume. Services: the bed board (python 3.12, 2 cores, 4 GB, port 8080 behind an HTTPS endpoint) and the chat, NVIDIA Nemotron 3.5 Bolt E4B in 4-bit GGUF on llama.cpp (one GPU, 8 cores, 32 GB), with weights on the hfcache volume.",
            "ICU Horizon · Fuzzball jobs", "Every job, its hardware and its resources", big=True)
    f.t_title = 17
    f.zone(16, 40, 1168, 536, label="2 × Lenovo ThinkStation PGX · NVIDIA GB10: 20 Arm cores, 128 GB, 1 GPU each · CIQ Fuzzball 4.3")
    xs, w, h, ys = (40, 270, 500, 730, 960), 200, 128, (72, 248, 424)
    cx = [x + w // 2 for x in xs]
    r1, r2, r3 = ys
    f.node(xs[0], r1, w, h, "card", "Job 1 · CPU · Node A", "Move data", ["CLIF records in", "alpine image", "1 core · 2 GiB"])
    f.node(xs[1], r1, w, h, "card", "Job 2 · CPU", "Tokenize", ["events into tokens", "uv Python image", "20 cores · 110 GiB"])
    f.node(xs[2], r1, w, h, "model", "Training · A + B", "Train the GEM", ["Nemotron backbone,", "1 DDP rank per node", "20 cores, 110 GiB ea."])
    f.node(xs[3], r1, w, h, "card", "Job 3.1 · CPU · Node A", "Package", ["save checkpoint", "load test passes", "2 cores · 4 GiB"])
    f.node(xs[4], r1, w, h, "card", "Job 4 · 2 GPUs, CPU", "Fit probes", ["embed on 2 × GB10", "fit 6 probes on CPU", "20 cores · 90 GiB"])
    f.node(xs[0], r2, w, h, "card", "Fuzzball", "Object cache", ["code, data in", "logs, counts out", "never overwrites"])
    f.node(xs[1], r2, w, h, "store", "VAST volume · 200 GB", "mimic_clif", ["CLIF records,", "tokens, GEM, probes", "read-only in job 5"])
    f.node(xs[2], r2, w, h, "forecast", "VAST volume · 20 GB", "twin-store", ["staged ward,", "rooms.json,", "forecast.json"])
    f.node(xs[4], r2, w, h, "store", "VAST volume", "hfcache", ["Nemotron E4B", "4-bit GGUF weights", "pinned revision"])
    f.node(xs[0], r3, w, h, "card", "Job 5 · CPU · Node B", "Load", ["vocab gate, inputs", "2 cores · 8 GB", "ran 7 s"])
    f.node(xs[1], r3, w, h, "model", "Job 5 · 1 GPU", "Infer", ["GEM + probes, 25 pts", "8 cores · 48 GB", "ran 35 s"])
    f.node(xs[2], r3, w, h, "card", "Job 5 · CPU · Node A", "Score", ["beds, unit totals", "4 cores · 16 GB", "ran 33 s"])
    f.node(xs[3], r3, w, h, "card", "Service · CPU", "Bed board", ["python:3.12-slim", "port 8080 to HTTPS", "2 cores · 4 GB"])
    f.node(xs[4], r3, w, h, "nvidia", "Service · 1 GPU", "Nemotron chat", ["Bolt E4B, llama.cpp", "64k-token context", "8 cores · 32 GB"])
    m1, m3 = r1 + h // 2, r3 + h // 2
    for i in range(4):
        f.arrow([(xs[i] + w, m1), (xs[i + 1], m1)])
    f.arrow([(xs[0] + w, m3), (xs[1], m3)])
    f.arrow([(xs[1] + w, m3), (xs[2], m3)])
    f.arrow([(xs[3] + w, m3), (xs[4], m3)])
    f.arrow([(cx[0], r2), (cx[0], r1 + h)], label="Data in", at=(cx[0], 224), side="right")
    f.arrow([(cx[0], r2 + h), (cx[0], r3)], label="Code in", at=(cx[0], 400), side="right")
    f.arrow([(cx[2], r1 + h), (cx[2], 224), (420, 224), (420, r2)])
    f.arrow([(cx[1], r2 + h), (cx[1], r3)], label="GEM", at=(cx[1], 400), side="right")
    f.arrow([(cx[2], r3), (cx[2], r2 + h)], BLUE, label="Writes", at=(cx[2], 400), side="right")
    f.arrow([(xs[2] + w, 312), (cx[3], 312), (cx[3], r3)], BLUE, label="Forecast", at=(780, 312))
    f.arrow([(cx[4], r2 + h), (cx[4], r3)], label="Weights", at=(cx[4], 400), side="right")
    f.caption("Each box: one Fuzzball job or service, its image and its request.", 612)
    f.write()


# =============================================================== print: split architecture, training and the live app
def _print_fonts(f):
    """Type sized for a figure printed at about half its width on a Letter page."""
    f.t_title, f.t_sub, f.t_tag, f.t_label, f.t_zone, f.t_cap = 22, 18, 15, 15, 15, 17


def arch_train():
    f = Fig("arch-train", 1200, 380, "Training on CIQ Fuzzball, run once",
            "Run once on two Lenovo ThinkStation PGX workstations (node A, CIQ-CHI-SPARK13; node B, CIQ-CHI-SPARK14), each one NVIDIA GB10. Job 1 moves CLIF records in on node A (CPU). Job 2 tokenizes them into the custom 1,231-token vocabulary on node B (CPU). Job 3, the one training workflow, trains the GEM, an NVIDIA Nemotron E4B backbone, from scratch with PyTorch DDP across both nodes, one GPU each. Job 3.1 packages and load-tests the checkpoint on node A. Job 4 embeds patients on both GPUs and fits six linear probes. Tokens, the GEM and the probes are saved on the 200 GB mimic_clif VAST volume.",
            "ICU Horizon · training", "One training workflow, with data prep and probes around it", big=True)
    _print_fonts(f)
    f.zone(16, 40, 1168, 324, label="Run once · node A = SPARK13 · node B = SPARK14")
    xs, w, h, r1, r2 = (40, 270, 500, 730, 960), 200, 124, 72, 248
    cx = [x + w // 2 for x in xs]
    f.node(xs[0], r1, w, h, "card", "Job 1 · node A", "Move data", ["CPU · 1 core", "CLIF records in"])
    f.node(xs[1], r1, w, h, "card", "Job 2 · node B", "Tokenize", ["CPU · 20 cores", "1,231 tokens"])
    f.node(xs[2], r1, w, h, "model", "Job 3 · A + B", "Train the GEM", ["2 GPUs, DDP", "Nemotron E4B"])
    f.node(xs[3], r1, w, h, "card", "Job 3.1 · node A", "Package", ["CPU · 2 cores", "load test"])
    f.node(xs[4], r1, w, h, "card", "Job 4 · A + B", "Fit probes", ["2 GPUs + CPU", "6 linear probes"])
    f.node(xs[0], r2, w, 96, "card", "Fuzzball", "Object cache", ["data in"])
    f.node(xs[1], r2, 660, 96, "store", "VAST volume · 200 GB", "mimic_clif", ["records, tokens, the GEM checkpoint, six probes"])
    m1 = r1 + h // 2
    for i in range(4):
        f.arrow([(xs[i] + w, m1), (xs[i + 1], m1)])
    f.arrow([(cx[0], r2), (cx[0], r1 + h)], label="In", at=(cx[0], 222), side="right")
    f.arrow([(cx[1], r1 + h), (cx[1], r2)], label="Tokens", at=(cx[1], 222), side="right")
    f.arrow([(cx[2], r1 + h), (cx[2], r2)], BLUE, label="GEM", at=(cx[2], 222), side="right")
    f.arrow([(cx[4], r1 + h), (cx[4], 296), (930, 296)], label="Probes", at=(cx[4], 252), side="right")
    f.write()


def arch_live():
    f = Fig("arch-live", 1200, 412, "ICU Horizon live on CIQ Fuzzball",
            "The live app is one CIQ Fuzzball workflow, job 5 (t7-launch). Load checks inputs on node B (CPU, 7 s). Infer runs the GEM and its probes on node B's GPU (35 s). Score adds up beds and the unit on node A (CPU, 33 s) and writes rooms.json and forecast.json to the twin-store VAST volume. The bed board service on node A reads those files and serves the ICU team over HTTPS; its chat agent calls read-only tools on the same files and sends the tool results to the chat model, NVIDIA Nemotron 3.5 Bolt E4B on llama.cpp on node B's GPU, whose only volume is hfcache with its weights. Nemotron never reads patient records; it knows what is happening to a patient only from the GEM's forecast passed in as tool results.",
            "ICU Horizon · live app", "The live app: job 5 and two services", big=True)
    _print_fonts(f)
    f.zone(16, 40, 1168, 356, label="ICU Horizon live · job 5 (t7-launch) · node A = SPARK13 · node B = SPARK14")
    xs, w, h, r1, r2 = (40, 270, 500, 730, 960), 200, 124, 72, 256
    cx = [x + w // 2 for x in xs]
    f.node(xs[0], r1, w, h, "card", "Fuzzball", "Object cache", ["code in,", "counts out"])
    f.node(xs[1], r1, w, h, "store", "VAST · read only", "mimic_clif", ["GEM, probes,", "25 patients"])
    f.node(xs[2], r1, w, h, "forecast", "VAST · 20 GB", "twin-store", ["rooms.json,", "forecast.json"])
    f.node(xs[3], r1, w, h, "nvidia", "NVIDIA · GPU · B", "Nemotron chat", ["reads forecast", "via chat tools"])
    f.node(xs[4], r1, w, h, "store", "VAST volume", "hfcache", ["Nemotron E4B", "4-bit weights"])
    f.node(xs[0], r2, w, h, "card", "Job 5 · node B", "Load", ["CPU · 2 cores", "ran 7 s"])
    f.node(xs[1], r2, w, h, "model", "Job 5 · node B", "Infer", ["GPU · 8 cores", "ran 35 s"])
    f.node(xs[2], r2, w, h, "card", "Job 5 · node A", "Score", ["CPU · 4 cores", "ran 33 s"])
    f.node(xs[3], r2, w, h, "card", "Service · A · CPU", "Board + chat", ["reads twin-store,", "runs chat tools"])
    f.node(xs[4], r2, w, h, "card", "HTTPS", "ICU team", ["nurse, doctor", "in a browser"], icon="person")
    m2 = r2 + h // 2
    f.arrow([(xs[0] + w, m2), (xs[1], m2)])
    f.arrow([(xs[1] + w, m2), (xs[2], m2)])
    f.arrow([(xs[3] + w, m2), (xs[4], m2)])
    f.arrow([(xs[4], r1 + 62), (xs[3] + w, r1 + 62)])
    f.arrow([(cx[0], r1 + h), (cx[0], r2)], label="Code", at=(cx[0], 226), side="right")
    f.arrow([(cx[1], r1 + h), (cx[1], r2)], label="GEM", at=(cx[1], 226), side="right")
    f.arrow([(cx[2], r2), (cx[2], r1 + h)], BLUE, label="Writes", at=(cx[2], 226), side="right")
    f.arrow([(xs[2] + w, r1 + 40), (xs[3], r1 + 40)], BLUE, dashed=True)
    f.arrow([(xs[2] + w, r1 + h - 24), (715, r1 + h - 24), (715, 244), (770, 244), (770, r2)], BLUE)
    f.arrow([(870, r2), (870, r1 + h)], BLUE, label="Tool results", at=(870, 222), side="right")
    f.write()


# =============================================================== slides: EHR table -> vocabulary -> GEM -> predictions
def ehr_to_tokens():
    f = Fig("ehr-to-tokens", 1280, 320, "From EHR tables to predictions",
            "Left to right: charted EHR values from CLIF tables (time, heart rate, mean arterial pressure, PEEP on the ventilator, norepinephrine dose) become event tokens in a custom 1,231-token vocabulary, each value binned into one of ten bins. The GEM, an NVIDIA Nemotron E4B backbone trained from scratch with a next-token objective, reads a patient's tokens once; its last hidden state is 384 numbers. Six linear probes on that state give five 24-hour chances. Values are illustrative.",
            "ICU Horizon · the model", "From EHR tables to predictions", big=True)
    _print_fonts(f)
    y, h, g = 24, 236, 24
    ws = (214, 344, 198, 176, 222)
    xs = []; x = 20
    for w in ws:
        xs.append(x); x += w + g
    f.node(xs[0], y, ws[0], h, "card", "EHR · CLIF tables", "Charted values", ["08:00", "heart rate 118", "MAP 62 mmHg", "PEEP 10 cmH2O", "norepi 0.12"])
    f.node(xs[1], y, ws[1], h, "forecast", "1,231-token vocab", "Event tokens", ["CLCK//08", "VITAL//heart_rate//B8", "VITAL//map//B2", "RESP//peep_set//B6", "MED_CON//norepinephrine//B4"])
    f.node(xs[2], y, ws[2], h, "model", "From scratch", "GEM", ["Nemotron E4B", "backbone, 36M", "parameters,", "next-token loss"])
    f.node(xs[3], y, ws[3], h, "card", "One pass", "Hidden state", ["384 numbers", "per patient"])
    f.node(xs[4], y, ws[4], h, "card", "6 linear probes", "24-h chances", ["Ventilator", "Vasopressor", "CRRT", "To ward", "Death"])
    m = y + h // 2
    for i in range(4):
        f.arrow([(xs[i] + ws[i], m), (xs[i + 1], m)], BLUE if i in (1, 2) else None)
    f.caption("Each value becomes one token (ten bins per measure). Values are illustrative.", 300, key=False)
    f.write()


# =============================================================== slides: 16:9 figures with the presentation type ramp
def _slide_fonts(f):
    """Projected in a room: about 1.3x on a 1920-px slide, so names ~38px and details ~28px there."""
    f.t_title, f.t_sub, f.t_tag, f.t_label, f.t_zone, f.t_cap = 30, 22, 18, 18, 18, 20


def slide_ehr():
    f = Fig("slide-ehr", 1280, 336, "From EHR tables to five predictions",
            "Charted EHR values (heart rate, PEEP, norepinephrine) become tokens in a custom 1,231-token vocabulary; the GEM, an NVIDIA Nemotron E4B backbone trained from scratch, reads them once and its 384-number hidden state feeds six linear probes that give five 24-hour chances. Values are illustrative.",
            "ICU Horizon · the model", "From EHR tables to five predictions", big=True)
    _slide_fonts(f)
    ws = (212, 420, 236, 236); g = 40
    xs = []; x = 24
    for w in ws:
        xs.append(x); x += w + g
    y, h = 24, 248
    f.node(xs[0], y, ws[0], h, "card", "EHR table", "Charted", ["08:00", "HR 118", "PEEP 10", "norepi 0.12"])
    f.node(xs[1], y, ws[1], h, "forecast", "1,231-token vocab", "Event tokens", ["CLCK//08", "VITAL//heart_rate//B8", "RESP//peep_set//B6", "MED_CON//norepinephrine//B4"])
    f.node(xs[2], y, ws[2], h, "model", "From scratch", "GEM", ["Nemotron E4B", "backbone, 36M", "one pass gives", "384-d state"])
    f.node(xs[3], y, ws[3], h, "card", "6 linear probes", "24-h chances", ["Ventilator", "Vasopressor", "CRRT", "To ward", "Death"])
    m = y + h // 2
    for i in range(3):
        f.arrow([(xs[i] + ws[i], m), (xs[i + 1], m)], BLUE if i == 1 else None)
    f.caption("One value becomes one token; ten bins per measure. Values illustrative.", 316, key=False)
    f.write()


def slide_train():
    f = Fig("slide-train", 1280, 456, "Training on CIQ Fuzzball, run once",
            "Run once on two Lenovo ThinkStation PGX workstations, each one NVIDIA GB10. Job 1 moves CLIF records in on node A; job 2 tokenizes them into the 1,231-token vocabulary on node B; job 3 trains the GEM from scratch on both GPUs with PyTorch DDP; job 3.1 packages it on node A; job 4 fits six linear probes on both GPUs. Everything is saved on the 200 GB mimic_clif VAST volume.",
            "ICU Horizon · training", "Training: one workflow on both GPUs", big=True)
    _slide_fonts(f)
    f.zone(12, 32, 1256, 364, label="Run once · 2 × NVIDIA GB10 · CIQ Fuzzball 4.3")
    xs, w, h, r1, r2 = (36, 284, 532, 780, 1028), 216, 152, 64, 280
    cx = [x + w // 2 for x in xs]
    f.node(xs[0], r1, w, h, "card", "Job 1 · CPU", "Move data", ["CLIF records", "in · node A"])
    f.node(xs[1], r1, w, h, "card", "Job 2 · CPU", "Tokenize", ["1,231 tokens", "node B"])
    f.node(xs[2], r1, w, h, "model", "Job 3 · 2 GPUs", "Train GEM", ["DDP, nodes", "A + B"])
    f.node(xs[3], r1, w, h, "card", "Job 3.1 · CPU", "Package", ["load test", "node A"])
    f.node(xs[4], r1, w, h, "card", "Job 4 · 2 GPUs", "Fit probes", ["6 linear", "probes"])
    f.node(xs[1], r2, 712, 92, "store", "VAST volume · 200 GB", "mimic_clif", [])
    m1 = r1 + h // 2
    for i in range(4):
        f.arrow([(xs[i] + w, m1), (xs[i + 1], m1)])
    f.arrow([(cx[2], r1 + h), (cx[2], r2)], BLUE, label="GEM", at=(cx[2], 248), side="right")
    f.arrow([(cx[4], r1 + h), (cx[4], 326), (996, 326)], label="Probes", at=(cx[4], 248), side="right")
    f.caption("Each box is one Fuzzball job; node A = SPARK13, node B = SPARK14.", 436, key=False)
    f.write()


def slide_live():
    f = Fig("slide-live", 1280, 496, "ICU Horizon live: how the chat gets its context",
            "Job 5 runs the GEM on one GPU and writes the forecast to the twin-store VAST volume. The board's chat agent reads the forecast and passes it to NVIDIA Nemotron as tool results; Nemotron's only volume holds its weights. The ICU team uses the board in a browser. Everything runs on two hospital-owned NVIDIA GB10 computers under CIQ Fuzzball.",
            "ICU Horizon · live app", "Live: how the chat gets its context", big=True)
    _slide_fonts(f)
    f.zone(12, 32, 1256, 404, label="Private by design · 2 hospital-owned NVIDIA GB10 · CIQ Fuzzball")
    xs, w, h, r1, r2 = (36, 344, 652, 960), 260, 148, 64, 256
    cx = [x + w // 2 for x in xs]
    f.node(xs[0], r1, w, h, "model", "Job 5 · GPU", "GEM infers", ["one pass per", "patient, 35 s"])
    f.node(xs[1], r1, w, h, "forecast", "VAST volume", "twin-store", ["the forecast", "rooms, unit"])
    f.node(xs[2], r1, w, h, "card", "Service · CPU", "Board + chat", ["runs the", "chat's tools"])
    f.node(xs[3], r1, w, h, "card", "HTTPS", "ICU team", ["nurse, doctor", "at 7 am"], icon="person")
    f.node(xs[2], r2, w, h, "nvidia", "NVIDIA · GPU", "Nemotron", ["sees tool results", "only"])
    f.node(xs[3], r2, w, h, "store", "VAST volume", "hfcache", ["Nemotron", "weights"])
    m1, m2 = r1 + h // 2, r2 + h // 2
    f.arrow([(xs[0] + w, m1), (xs[1], m1)], BLUE)
    f.arrow([(xs[1] + w, m1), (xs[2], m1)], BLUE)
    f.arrow([(xs[2] + w, m1), (xs[3], m1)])
    f.arrow([(cx[2] - 40, r1 + h), (cx[2] - 40, r2)], BLUE, label="Tool results", at=(cx[2] - 40, 236), side="left")
    f.arrow([(xs[3], m2), (xs[2] + w, m2)])
    f.caption("Nemotron never reads patient records; it knows each patient only from the GEM's forecast.", 476, key=False)
    f.write()


# =============================================================== print: the model in four steps (Steps type)
def model_steps():
    steps = [("01", "Train from scratch", ["Nemotron backbone,", "1,231-token vocab"], False),
             ("02", "Read hidden layer", ["one pass per patient,", "384-d embedding"], True),
             ("03", "Six linear probes", ["logistic regressions,", "24-h probabilities"], False),
             ("04", "Chat explains", ["Nemotron E4B reads", "the forecast via tools"], False)]
    W, H = 1200, 268
    f = Fig("model-steps", W, H, "The GEM in four steps",
            "Four steps, left to right. One: train the GEM from scratch, an NVIDIA Nemotron backbone with a custom 1,231-token ICU vocabulary. Two, highlighted: one forward pass per patient; the last hidden layer is a 384-dimensional embedding. Three: six logistic-regression probes give 24-hour probabilities. Four: the NVIDIA Nemotron 3.5 Bolt E4B chat explains the forecast through read-only tools and predicts nothing.",
            "ICU Horizon · the model", "The GEM in four steps", big=True)
    f.t_cap = 18
    n, stage_w = len(steps), 280
    x0 = (W - n * stage_w) // 2
    rail_y, rail_h, r = 20, 52, 34
    for i, (num, title, desc, focal) in enumerate(steps):
        x = x0 + i * stage_w
        cx = x + stage_w // 2
        fill = LV_MEDIUM if focal else (BOARD2 if i % 2 else SURFACE)
        f.raw("zones", f'<rect x="{x}" y="{rail_y}" width="{stage_w}" height="{rail_h}" fill="{fill}" stroke="{LINE}" stroke-width="1"/>')
        if focal:
            f.raw("zones", f'<line x1="{x}" y1="{rail_y}" x2="{x + stage_w}" y2="{rail_y}" stroke="{BLUE}" stroke-width="2"/>'
                           f'<line x1="{x}" y1="{rail_y + rail_h}" x2="{x + stage_w}" y2="{rail_y + rail_h}" stroke="{BLUE}" stroke-width="2"/>')
        cy = rail_y + rail_h // 2
        mfill, mtext, mstroke = (BLUE, ON_HIGH, BLUE) if focal else (SURFACE, INK, INK)
        f.raw("nodes", f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{mfill}" stroke="{mstroke}" stroke-width="1.5"/>'
                       + f.text(cx, cy + 9, num, 26, 800, mtext, "middle"))
        f.raw("nodes", f.text(cx, 132, title, 25, 700, BLUE if focal else INK, "middle"))
        for k, line in enumerate(desc):
            f.raw("nodes", f.text(cx, 168 + k * 28, line, 21, 400, INK2, "middle"))
    f.caption("One pass feeds every prediction; a new outcome is a new probe, not a new model.", 254, key=False)
    f.write()


# =============================================================== detail: how to run it on the cluster
def workflow():
    f = Fig("workflow", 1280, 424, "How to run it on the cluster",
            "Three steps by hand: create the twin-store volume once, render the ready workflow files after each code change, and stage job 4's probe once per model after the code is published (scripts/launch.sh --code), because the probe's sidecar command imports the published code. Then one command, scripts/launch.sh --all, runs four Fuzzball workflows in order: t7-code, t7-ward, t7-forecast-unit and t7-twin, and prints the board's link. The team ran this path end to end on the cluster; every step but the per-change render is marked done.",
            "ICU Horizon · how to run it", "Three steps by hand, then one command")
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
            "ICU Horizon · API", "Four reads, three writes, one rule for every POST")
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
            "ICU Horizon · Update the unit", "One button, one POST, one Fuzzball job")
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
            "ICU Horizon · data boundary", "Rows stay on the volumes; only counts and room entries reach a screen")
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
            "ICU Horizon · model results", "Held-out AUROC by task, with 95% ranges")
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


FIGURES = (stack, flow, architecture, architecture_print, model_steps, arch_train, arch_live, ehr_to_tokens, slide_ehr, slide_train, slide_live, workflow, api, trigger, data_boundary, results_auroc)

if __name__ == "__main__":
    if "--night" in sys.argv:
        OUT = Path(sys.argv[sys.argv.index("--night") + 1])
        OUT.mkdir(parents=True, exist_ok=True)
        globals().update(NIGHT)
    for fn in FIGURES:
        fn()
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.html"))), "in", OUT)

#!/usr/bin/env python3
# ruff: noqa: E501  (usage lines read better unwrapped)
"""Fill the tokens of a Fuzzfile template (fuzzball/*.fz) and refuse a half-filled one.

Fuzzball 4.3 Fuzzfiles have no parameters, so every workflow here is a template with
@TOKEN@ placeholders. The dispatcher fills them for each forecast run; this is the
same code (app/dispatcher.py `render_template`) for a person starting one by hand.
It only writes text: it starts nothing and talks to no cluster.

  python scripts/render_fz.py fuzzball/t7-forecast.fz --scope unit -o /tmp/t7-forecast.fz
  python scripts/render_fz.py fuzzball/t7-forecast.fz --scope room --room 12 --hours 4.5 -o /tmp/f.fz
  python scripts/render_fz.py fuzzball/t7-fit.fz -o /tmp/t7-fit.fz              # open demo ward
  python scripts/render_fz.py fuzzball/t7-ward.fz --cohort -o /tmp/t7-ward.fz   # the final cohort, where it
      # is on the cluster: --real-ward --clif-dir /data/dashboard_data --ward-ids .../dashboard_patients_unit25.parquet
      # --names .../name.parquet (each can still be given on its own)
  python scripts/render_fz.py fuzzball/t7-code.fz --code-ref <40 hex> --code-sha256 <64 hex> -o /tmp/t7-code.fz
  scripts/make_ready.sh [commit]                        # all of the above for the final cohort -> fuzzball/ready/
  python scripts/render_fz.py --check fuzzball/*.fz    # which tokens each template has

Exit 1, and nothing written, when a token would be left unfilled (the message names
it) or a path holds characters that are unsafe inside a job script.
Then: fuzzball workflow validate <out> && fuzzball workflow start <out> --name <t7-...>
"""

import argparse
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import dispatcher  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("template", type=pathlib.Path, nargs="+")
    ap.add_argument("-o", "--out", type=pathlib.Path, help="default: stdout")
    ap.add_argument("--check", action="store_true", help="list each file's tokens")
    ap.add_argument("--scope", choices=dispatcher.SCOPES, default="unit")
    ap.add_argument("--room", type=int, default=0)
    ap.add_argument("--hours", type=float, default=0, help="demo-clock hours")
    ap.add_argument(
        "--cohort", action="store_true", help="the final cohort on mimic_clif"
    )
    ap.add_argument("--real-ward", action="store_true")
    ap.add_argument("--clif-dir", default=dispatcher.DEFAULT_CLIF_DIR)
    ap.add_argument("--ward-ids", default="")
    ap.add_argument("--names", default="")
    ap.add_argument("--code-ref", default="")
    ap.add_argument("--code-sha256", default="")
    a = ap.parse_args(argv)
    if a.cohort:
        a.real_ward = True
        if a.clif_dir == dispatcher.DEFAULT_CLIF_DIR:
            a.clif_dir = dispatcher.COHORT_CLIF_DIR
        a.ward_ids = a.ward_ids or dispatcher.COHORT_WARD_IDS
        a.names = a.names or dispatcher.COHORT_NAMES
    if a.check:
        for f in a.template:
            print(f"{f.name}: {' '.join(dispatcher.unfilled(f.read_text())) or '-'}")
        return 0
    if len(a.template) != 1:
        ap.error("one template at a time (several only with --check)")
    if a.scope == "room" and a.room not in dispatcher.ROOMS:
        ap.error("--scope room needs --room 1..25")
    try:
        text = dispatcher.render_template(
            a.template[0].read_text(),
            scope=a.scope,
            room=a.room,
            hours=a.hours,
            real_ward=a.real_ward,
            clif_dir=a.clif_dir,
            ward_ids=a.ward_ids,
            names=a.names,
            code_ref=a.code_ref,
            code_sha256=a.code_sha256,
        )
    except ValueError as e:
        print(f"{a.template[0].name}: {e}", file=sys.stderr)
        return 1
    if a.out:
        a.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

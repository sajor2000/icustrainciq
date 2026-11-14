#!/usr/bin/env python3
"""A given ward (the final demo cohort) end to end on a laptop: no GPU, no cluster.

  uv run --extra model python scripts/run_cohort.py data/local/unit25 \\
      --ward-ids data/local/unit25/dashboard_patients_unit25.parquet --real-ward

Steps: ward map (app/stage_ward.py --ward-ids) -> tokenize the CLIF folder ->
winnow at the cut -> what is running at the cut from raw CLIF (app/clif_now.py) ->
age and sex -> rooms.json and forecast.json in --out (default data/local/out),
working files in --work (default data/local/work). Both are under backend/data/,
which git ignores: a real ward never leaves the machine.

No model yet (no --model / --probes, or the folders lack weights or no probe
file): "forecast_state": "pending-model". The Now side is real (on now, age,
sex, last 12 h); every prediction and expected count is null (docs/CONTRACT.md).
With --model <mdl dir> --probes <probe-<model>.joblib> the same run extracts
features and applies the saved probes (icutwin-extract, rep_based.apply_probes).

The cut (docs/CONTRACT.md "Shared demo day"): each stay is cut on its own clock,
first ICU arrival + --cut-after-arrival-hours (24, D3) + --demo-clock-hours. The
files then show every room on one shared day: the cut is the last 07:00 in --tz
plus the demo clock, and nothing in them carries a date of the source data.
  --names <names file> | --names fake   made-up names on the room tiles
  --cut-table 0,24,48,72   print, per demo clock, how many rooms remain and how
                           many are on IMV / vasopressor / CRRT; writes no JSON

Prints counts only: never a row, an id, a date of the data or free text.
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import sys
import zoneinfo

import polars as pl
import yaml

BACKEND = pathlib.Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:  # run as a script from any folder
    sys.path.insert(0, str(BACKEND))

from app import aggregate, clif_now, fake_names, rooms, stage_ward, ward_check  # noqa: E402

HOSP = "hospitalization_id"
BASE_HOURS = 24  # D3: the cut is 24 h after ICU arrival
SOURCE_YEAR = re.compile(r"(?<!\d)2[1-9]\d{2}(?!\d)")  # MIMIC's shifted years


def tokenize(clif_dir: pathlib.Path, work: pathlib.Path, tz: str) -> pathlib.Path:
    """icutwin-tokenize pipeline on the folder -> <work>/tokenized_output"""
    from icutwin.tokenizer import assembly
    from icutwin.tokenizer.helpers import ClifData

    out = work / "tokenized_output"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    site = work / "site.yaml"
    site.write_text(
        yaml.safe_dump(
            {
                "clif_path": str(clif_dir.resolve()),
                "timezone": tz,
                "filetype": "parquet",
            }
        )
    )
    clif = ClifData(site)
    assembly.collate(clif, out)
    assembly.split(clif, out)
    qc = assembly.tokenize(clif, out)
    print(  # counts only
        json.dumps(
            {
                "tokenized_stays": sum(
                    qc["split"].get(s, 0) for s in ("train", "tuning", "held_out")
                ),
                "short_stays_removed": qc["short_stays_removed"],
                "missing_tables": qc["missing_tables"],
            }
        )
    )
    return out


def shared_cut(now: dt.datetime, tz: str, demo_clock_hours: float) -> dt.datetime:
    """the board's cut for every room: the last 07:00 at or before `now` in the ward
    time zone, plus the demo clock"""
    local = now.astimezone(zoneinfo.ZoneInfo(tz))
    seven = local.replace(hour=aggregate.CUT_HOUR, minute=0, second=0, microsecond=0)
    if seven > local:
        seven -= dt.timedelta(days=1)
    return seven + dt.timedelta(hours=float(demo_clock_hours))


def present_at_cut(clif_dir: pathlib.Path, cuts: dict) -> dict[str, bool]:
    """per stay, on its own clock: is its cut after ICU arrival, inside an ICU stay
    of clif_adt (in <= cut < out) and before hospital discharge? A stay that left
    the ICU, died or was discharged before the cut is not present."""
    if not cuts:
        return {}
    c = clif_now._cuts_frame(cuts).lazy()
    adt = clif_now._read(
        clif_dir,
        "adt",
        [HOSP, "in_dttm", "out_dttm", "location_category"],
        ["in_dttm", "out_dttm"],
    ).filter(pl.col("location_category").str.to_lowercase() == "icu")
    in_icu = set(
        adt.join(c, on=HOSP)
        .filter(pl.col("in_dttm") < pl.col("cut"))
        .filter(pl.col("out_dttm").is_null() | (pl.col("out_dttm") > pl.col("cut")))
        .select(HOSP)
        .unique()
        .collect()[HOSP]
    )
    hosp = clif_now._read(
        clif_dir, "hospitalization", [HOSP, "discharge_dttm"], ["discharge_dttm"]
    )
    gone = set(
        hosp.join(c, on=HOSP)
        .filter(pl.col("discharge_dttm") <= pl.col("cut"))
        .select(HOSP)
        .collect()[HOSP]
    )
    return {str(k): (str(k) in in_icu and str(k) not in gone) for k in cuts}


def token_checks(root: pathlib.Path, ids: list[str], cuts: dict, tz: str) -> dict:
    """per-stay checks of what the model and the room page read, as counts: every
    past token is strictly before the stay's cut (nothing from the future), the
    past is in time order, and the tokenizer's cut is the CLIF cut (they can
    differ by the hour of a daylight-saving change inside the first day)."""
    leak = unordered = clock = 0
    for f in sorted(root.glob("*_for_inference.parquet")):
        split = f.name.removesuffix("_for_inference.parquet")
        df = pl.read_parquet(f, columns=[HOSP, "s_elapsed_past", "cut_s"]).filter(
            pl.col(HOSP).is_in(ids)
        )
        if not df.height:
            continue
        first = (
            pl.scan_parquet(root / f"tokens_{split}.parquet")
            .group_by(HOSP)
            .agg(first=pl.col("event_time").min())
            .collect()
        )
        df = df.join(first, on=HOSP, how="left").with_columns(
            token_cut=(pl.col("first") + pl.duration(seconds=pl.col("cut_s")))
            .dt.replace_time_zone(tz, ambiguous="earliest", non_existent="null")
            .dt.convert_time_zone("UTC")
        )
        for sid, secs, cut_s, token_cut in df.select(
            HOSP, "s_elapsed_past", "cut_s", "token_cut"
        ).iter_rows():
            leak += any(s >= cut_s for s in secs)
            unordered += any(b < a for a, b in zip(secs, secs[1:]))
            want = clif_now._utc_dt(cuts[sid])
            clock += token_cut is None or abs((token_cut - want).total_seconds()) > 60
    return {"future_tokens": leak, "unordered": unordered, "cut_clock_differs": clock}


def state_at(
    root: pathlib.Path,
    clif_dir: pathlib.Path,
    room_of: dict[str, int],
    offset_hours: float,
    tz: str,
    on_now_from_clif: bool,
) -> tuple[pl.DataFrame, dict | None, dict]:
    """winnow the ward at ICU arrival + 24 h + offset; return the label rows of the
    rooms present at that cut, what runs at it (raw CLIF) and the check counts"""
    from icutwin.common import logger
    from icutwin.scoring import winnower

    logger.setLevel("WARNING")  # the per-split outcome rates are small cells here
    winnower.winnow(root, None, offset_hours or None)
    ids = list(room_of)
    df = aggregate.pending_scores(root, ids)
    kept = df[HOSP].to_list()
    cuts = clif_now.stay_cuts(clif_dir, kept, offset_hours)
    here = present_at_cut(clif_dir, cuts)
    absent = [i for i in kept if not here[i]]
    df = df.filter(~pl.col(HOSP).is_in(absent))
    kept = df[HOSP].to_list()
    checks = token_checks(root, kept, cuts, tz)
    if checks["future_tokens"] or checks["unordered"]:
        raise SystemExit(f"timeline check failed: {json.dumps(checks)}")
    clif = (
        clif_now.running_at_cut(clif_dir, {i: cuts[i] for i in kept})
        if on_now_from_clif
        else None
    )
    checks |= {
        "ward": len(ids),
        "present": len(kept),
        "ended_before_cut": len(ids) - len(kept),
        "not_in_icu_at_cut_by_adt": len(absent),
    }
    return df, clif, checks


def cut_row(hours: float, df: pl.DataFrame, clif: dict | None, checks: dict) -> dict:
    """one line of the cut table: counts as the board would show them"""
    on = aggregate.patient_table(df, clif=clif)["on"] if df.height else {}
    n = lambda k: int(on[k].sum()) if df.height else 0  # noqa: E731
    return {
        "demo_clock_hours": hours,
        "rooms_present": checks["present"],
        "dropped": checks["ended_before_cut"],
        "imv": n("imv"),
        "vasopressor": n("vasopressor"),
        "crrt": n("crrt"),
        "any_life_support": int(aggregate._on_any(on).sum()) if df.height else 0,
        "imv_unknown_in_clif": sum(v["imv"] is None for v in (clif or {}).values()),
    }


def score(root, df, model, probes, ids):
    """(score table, forecast_state, model name): the saved probes on fresh features
    when the model and the probes are there, else the pending table"""
    why = None
    if not (model and probes):
        why = "no --model / --probes"
    else:
        from icutwin.scoring import rep_based

        if rep_based.weights_digest(model) is None:
            why = "no model weights in --model"
        elif not pathlib.Path(probes).is_file():
            why = "no probe file at --probes"
    if why:
        print(f"forecast pending: {why}")
        return df, aggregate.PENDING, "pending"
    from icutwin.scoring import extractor

    extractor.extract(root, model)
    out = rep_based.apply_probes(root, model, probes, ids)
    scored = pl.read_parquet(out).filter(pl.col(HOSP).is_in(ids))
    return scored, aggregate.READY, pathlib.Path(model).name


def _strings(x):
    """every string in a JSON document, keys included"""
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def source_years(doc) -> int:
    """strings of a JSON document that hold a year of 2100 or later (MIMIC shifts
    every date there): a count, 0 for a clean file. Numbers are not dates."""
    return sum(bool(SOURCE_YEAR.search(s)) for s in _strings(doc))


def check_no_source_dates(docs: dict[str, dict], ids: list[str]) -> None:
    """refuse to write a file that carries a date of the source data or a stay id"""
    for name, doc in docs.items():
        if source_years(doc):
            raise SystemExit(f"{name}: a year of 2100 or later; not written")
        text = json.dumps(doc)
        if any(i in text for i in ids if len(i) >= 5):
            raise SystemExit(f"{name}: a stay id; not written")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clif_dir", type=pathlib.Path, help="folder of clif_*.parquet")
    ap.add_argument("--ward-ids", type=pathlib.Path, required=True)
    ap.add_argument(
        "--real-ward",
        action="store_true",
        help="the ids are real MIMIC-IV stays: refused without it",
    )
    ap.add_argument("--out", type=pathlib.Path, default=BACKEND / "data/local/out")
    ap.add_argument("--work", type=pathlib.Path, default=BACKEND / "data/local/work")
    ap.add_argument("--model", type=pathlib.Path, help="mdl-<run>/ (else pending)")
    ap.add_argument(
        "--probes", type=pathlib.Path, help="probe-<model>.joblib (else pending)"
    )
    ap.add_argument(
        "--cut-after-arrival-hours",
        type=float,
        default=BASE_HOURS,
        help="each stay's 07:00 cut, in hours after its first ICU arrival "
        "(default 24, D3); the model was trained at 24",
    )
    ap.add_argument(
        "--demo-clock-hours",
        type=float,
        default=0,
        help="hours past the 07:00 cut: every stay moves by this on its own clock",
    )
    ap.add_argument("--cut-table", help="demo clocks, e.g. 0,24,48,72: counts only")
    ap.add_argument("--tz", default=aggregate.DEFAULT_TZ, help="ward time zone")
    ap.add_argument("--data-tz", default="US/Eastern", help="time zone of the CLIF")
    ap.add_argument(
        "--names",
        help="made-up names for the tiles: a names file beside the ward's data, or "
        "'fake' for the seeded generator (default: none)",
    )
    ap.add_argument("--unit-name", default=aggregate.UNIT_NAME)
    ap.add_argument("--capacity", type=pathlib.Path)
    ap.add_argument("--baseline", type=pathlib.Path)
    ap.add_argument("--seed", type=int, default=stage_ward.SEED)
    ap.add_argument(
        "--reuse-tokens",
        action="store_true",
        help="keep <work>/tokenized_output from an earlier run of the same folder",
    )
    a = ap.parse_args(argv)
    tables = ward_check.table_report(a.clif_dir)
    print(json.dumps({"tables": tables}))
    a.work.mkdir(parents=True, exist_ok=True)

    ward_csv = a.work / "stage_ward.csv"
    ward_rooms, info = stage_ward.ward_from_ids(
        a.clif_dir, a.ward_ids, a.real_ward, a.seed
    )
    ward_rooms.write_csv(ward_csv)
    room_of = aggregate.read_room_map(ward_csv)
    ward = aggregate.check_ward(room_of, a.real_ward)
    print(json.dumps({"ward_map": info}))

    root = a.work / "tokenized_output"
    if not (a.reuse_tokens and (root / "vocab.yaml").is_file()):
        root = tokenize(a.clif_dir, a.work, a.data_tz)
    base = a.cut_after_arrival_hours - BASE_HOURS
    on_clif = tables["on_now_from_clif"]

    if a.cut_table:
        for h in [float(x) for x in a.cut_table.split(",") if x.strip()]:
            df, clif, checks = state_at(
                root, a.clif_dir, room_of, base + h, a.data_tz, on_clif
            )
            print(json.dumps(cut_row(h, df, clif, checks)))
        return

    offset = base + a.demo_clock_hours
    df, clif, checks = state_at(root, a.clif_dir, room_of, offset, a.data_tz, on_clif)
    ids = df[HOSP].to_list()
    scored, state, model_name = score(root, df, a.model, a.probes, ids)
    pending = state == aggregate.PENDING

    now = aggregate.now_iso()
    cut = shared_cut(dt.datetime.fromisoformat(now), a.tz, a.demo_clock_hours)
    vocab = yaml.safe_load((root / "vocab.yaml").read_text())["lookup"]
    words = {int(i): w for w, i in vocab.items()}
    demo = rooms.demographics(a.clif_dir, ids)
    names, name_counts = fake_names.names_for(
        a.names, room_of, {s: d["sex"] for s, d in demo.items()}
    )
    entries = rooms.room_entries(
        scored,
        room_of,
        rooms.past_events(root, ids, words),
        cut,
        now,
        demo,
        clif,
        pending=pending,
        names=names,
    )
    source = "clif" if clif is not None else "tokens"
    rooms_doc = {
        "made_at": now,
        "ward": ward,
        "forecast_state": state,
        "rooms": entries,
        "on_now_source": source,
        "dropped": len(set(room_of.values()) - {r["room"] for r in entries}),
    }
    if any("name" in r for r in entries):
        rooms_doc["names"] = "fictional"
    forecast = aggregate.build_forecast(
        scored,
        model_name,
        beds=len(room_of),
        baseline=a.baseline,
        capacity=a.capacity,
        cut_time=cut.isoformat(timespec="seconds"),
        tz=a.tz,
        demo_clock_hours=a.demo_clock_hours,
        stage_csv=ward_csv,
        ward=ward,
        forecast_state=state,
        clif=clif,
        unit_name=a.unit_name,
    )
    forecast["made_at"] = now  # one run, one time in both files
    forecast["cut_after_arrival_hours"] = a.cut_after_arrival_hours
    check_no_source_dates(
        {"rooms.json": rooms_doc, "forecast.json": forecast}, list(room_of)
    )
    a.out.mkdir(parents=True, exist_ok=True)
    aggregate.write_json(a.out / "rooms.json", rooms_doc)
    aggregate.write_json(a.out / "forecast.json", forecast)  # last: the page watches it
    ls = forecast["life_support"]
    print(  # counts only
        json.dumps(
            {
                "forecast_state": state,
                "ward": ward["source"],
                "rooms_written": len(entries),
                "dropped": rooms_doc["dropped"],
                "on_now_source": source,
                **name_counts,
                "now_patients": ls["now_patients"],
                "now_by": ls["now_by"],
                "checks": checks,
                "out": [str(a.out / "rooms.json"), str(a.out / "forecast.json")],
            }
        )
    )


if __name__ == "__main__":
    main()

"""Is a ward's CLIF folder ready to stage? Counts and table names only.

Usage: python app/ward_check.py <CLIF folder> [--ward-ids <parquet|csv>] [--real-ward]
         [--expect-ids 25]

Job `load` of fuzzball/t7-ward.fz and scripts/run_cohort.py run it before anything is
tokenized. It checks that the folder holds the tables the tokenizer cannot do without
(clif_hospitalization, clif_patient, clif_adt), says which known tables are missing
(their tokens are skipped) and which extra tables are ignored (ecmo_mcs, input,
output, ...: no token is made from them, so ECMO stays out of the board), and, with
--ward-ids, that the id file has the expected number of stays and every one is in
clif_hospitalization. Without --real-ward ids outside the open demo are refused.
Prints one JSON line of counts; never a row, an id or a date. Exit 1 on a problem.
"""

import argparse
import json
import pathlib

import polars as pl

try:  # imported as app.ward_check (tests) or run as a script (the job)
    from app import fake_names, stage_ward
except ImportError:  # pragma: no cover
    import fake_names
    import stage_ward

HOSP = "hospitalization_id"
REQUIRED = ("hospitalization", "patient", "adt")  # no ward, no ICU arrival without
ON_NOW = ("respiratory_support", "medication_admin_continuous", "crrt_therapy")


def table_report(clif_dir: pathlib.Path) -> dict:
    """which clif_<table>.parquet files the tokenizer will read, which it lacks and
    which it leaves alone (table names only). A missing required table stops the
    run with its name."""
    from icutwin.tokenizer import assembly

    known = set(assembly.STEP_OF)
    clif_dir = pathlib.Path(clif_dir)
    if not clif_dir.is_dir():
        raise SystemExit(f"CLIF folder not found: {clif_dir.name}/")
    have = {f.stem.removeprefix("clif_") for f in clif_dir.glob("clif_*.parquet")}
    lost = [t for t in REQUIRED if t not in have]
    if lost:
        raise SystemExit(
            f"required CLIF table(s) not found in {clif_dir.name}/: "
            + ", ".join(f"clif_{t}.parquet" for t in lost)
        )
    return {
        "read": sorted(known & have),
        "missing_optional": sorted(known - have),
        "ignored": sorted(have - known),
        "on_now_from_clif": all(t in have for t in ON_NOW),
    }


def check(
    clif_dir: pathlib.Path,
    ward_ids: pathlib.Path | None = None,
    real_ward: bool = False,
    expect_ids: int | None = None,
    names: str | None = None,
) -> dict:
    """the folder's table report plus stay counts; refuses a wrong ward file"""
    clif_dir = pathlib.Path(clif_dir)
    out = {"tables": table_report(clif_dir)}
    out["hospitalizations"] = (
        pl.scan_parquet(clif_dir / "clif_hospitalization.parquet")
        .select(pl.col(HOSP).n_unique())
        .collect()
        .item()
    )
    if ward_ids:
        rooms, info = stage_ward.ward_from_ids(clif_dir, ward_ids, real_ward)
        if expect_ids is not None and rooms.height != expect_ids:
            raise SystemExit(
                f"{pathlib.Path(ward_ids).name} holds {rooms.height} stays, "
                f"expected {expect_ids}"
            )
        out["ward_ids"] = rooms.height
        out["ward"] = info["ward"]
        if names:  # the names file is readable, fictional and clean; counts only
            room_of = dict(zip(rooms[HOSP], rooms["room"]))
            out |= fake_names.names_for(names, room_of)[1]
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("clif_dir", type=pathlib.Path)
    ap.add_argument("--ward-ids", type=pathlib.Path)
    ap.add_argument("--real-ward", action="store_true")
    ap.add_argument(
        "--expect-ids", type=int, help="stays the id file must hold (with --ward-ids)"
    )
    ap.add_argument("--names", help="names file to check (with --ward-ids), or 'fake'")
    a = ap.parse_args(argv)
    if a.real_ward and not a.ward_ids:
        raise SystemExit("--real-ward needs --ward-ids")
    print(json.dumps(check(a.clif_dir, a.ward_ids, a.real_ward, a.expect_ids, a.names)))


if __name__ == "__main__":
    main()

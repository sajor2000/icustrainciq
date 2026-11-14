"""Pick the stage ward: 25 open MIMIC-IV Demo ICU stays, the same way every time.

Usage: python app/stage_ward.py clif_demo --out /rows/stage/stage_ward.csv
         [--seed 20261114] [--n 25]

Reads only the CLIF demo tables (clif_adt, clif_hospitalization, clif_vitals,
clif_labs, clif_medication_admin_continuous, clif_respiratory_support,
clif_crrt_therapy) and needs no GPU, no model and no network, so the selection
can be reproduced inside the cluster from the open data in the repo.

Rule (docs/LIVE_DEMO.md section 1, docs/DECISIONS.md D6, D10):
 1. a stay is eligible when it reaches ICU and is still in the ICU, and still in
    hospital, 24 h after the first ICU arrival (icutwin/config/winnowing.yaml);
 2. each eligible stay gets a sickness score 0 to 8 over the first 24 h in the ICU,
    one point each for: any vasopressor dose, invasive ventilation, CRRT,
    MAP < 65, lactate > 2, creatinine > 2, platelets < 100, and
    (SpO2 < 90 or FiO2 >= 0.6);
 3. keep the median band: scores between the 40th and 60th percentile of the
    eligible stays (the band widens by 5 points per side if it holds fewer than n);
 4. one stay per patient (lowest hospitalization id), then a seeded draw of n
    stays; room numbers 1 to n follow the draw.

Prints counts and a short digest of the chosen ids only. The csv (room,
hospitalization_id, score) goes to a cluster volume, never to git.

A given ward (the final demo cohort): `--ward-ids <parquet|csv> --real-ward`
  python app/stage_ward.py <CLIF folder> --ward-ids ids.parquet --real-ward --out ...
skips the selection: the ward is exactly the `hospitalization_id` values of that
file, and rooms 1..n follow a seeded shuffle of the sorted ids (stable, and not the
order of ids or of admission). The same csv is written (score left empty). Ids
outside the open demo are refused without --real-ward; the ids must be in the CLIF
folder's clif_hospitalization. Prints counts only (no digest for a real ward).
"""

import argparse
import hashlib
import pathlib

import numpy as np
import polars as pl

try:  # imported as app.stage_ward (tests) or run as a script (the job)
    from app import aggregate
except ImportError:  # pragma: no cover
    import aggregate

SEED = 20261114
N_ROOMS = 25
PRESSORS = (
    "angiotensin",
    "dopamine",
    "epinephrine",
    "norepinephrine",
    "phenylephrine",
    "vasopressin",
)
HOSP = "hospitalization_id"
POINTS = (
    "vasopressor",
    "imv",
    "crrt",
    "map_lt_65",
    "lactate_gt_2",
    "creatinine_gt_2",
    "platelets_lt_100",
    "hypoxia",
)


def _read(demo_dir: pathlib.Path, table: str, cols: list[str]) -> pl.LazyFrame:
    return pl.scan_parquet(demo_dir / f"clif_{table}.parquet").select(cols)


def eligible_stays(demo_dir: pathlib.Path) -> pl.DataFrame:
    """stays still in the ICU (and hospital) at the cut: ids, arrival, cut"""
    icu = (
        _read(demo_dir, "adt", [HOSP, "in_dttm", "out_dttm", "location_category"])
        .filter(pl.col("location_category") == "icu")
        .sort(HOSP, "in_dttm")
        .group_by(HOSP)
        .agg(arrival=pl.col("in_dttm").first(), icu_out=pl.col("out_dttm").first())
    )
    hosp = _read(demo_dir, "hospitalization", [HOSP, "patient_id", "discharge_dttm"])
    day = pl.duration(hours=24)
    return (
        icu.join(hosp, on=HOSP)
        .with_columns(cut=pl.col("arrival") + day)
        .with_columns(left=pl.coalesce("icu_out", "discharge_dttm"))
        .filter(
            (pl.col("left") >= pl.col("cut"))
            & (pl.col("discharge_dttm") > pl.col("cut"))
        )
        .select(HOSP, "patient_id", "arrival", "cut")
        .collect()
        .sort(HOSP)
    )


def _flag(lf: pl.LazyFrame, stays: pl.DataFrame, time: str, hit: pl.Expr, name: str):
    """stays with at least one row inside [arrival, cut) where `hit` holds"""
    win = stays.lazy().select(HOSP, "arrival", "cut")
    return (
        lf.join(win, on=HOSP)
        .filter((pl.col(time) >= pl.col("arrival")) & (pl.col(time) < pl.col("cut")))
        .filter(hit.fill_null(False))
        .select(HOSP)
        .unique()
        .with_columns(pl.lit(1).alias(name))
    )


def score_stays(demo_dir: pathlib.Path, stays: pl.DataFrame) -> pl.DataFrame:
    """add the eight 0/1 points and `score` (their sum) to the eligible stays"""
    d = demo_dir
    vit = _read(d, "vitals", [HOSP, "recorded_dttm", "vital_category", "vital_value"])
    labs = _read(
        d,
        "labs",
        [
            HOSP,
            "lab_collect_dttm",
            "lab_result_dttm",
            "lab_category",
            "lab_value_numeric",
        ],
    )
    labs = labs.with_columns(t=pl.coalesce("lab_collect_dttm", "lab_result_dttm"))
    meds = _read(
        d,
        "medication_admin_continuous",
        [HOSP, "admin_dttm", "med_category", "med_dose"],
    )
    resp = _read(
        d, "respiratory_support", [HOSP, "recorded_dttm", "device_category", "fio2_set"]
    )
    crrt = _read(d, "crrt_therapy", [HOSP, "recorded_dttm"])
    lab = lambda cat, op: (
        (pl.col("lab_category") == cat) & op(pl.col("lab_value_numeric"))
    )  # noqa: E731
    flags = [
        _flag(
            meds,
            stays,
            "admin_dttm",
            pl.col("med_category").is_in(PRESSORS) & (pl.col("med_dose") > 0),
            "vasopressor",
        ),
        _flag(
            resp,
            stays,
            "recorded_dttm",
            pl.col("device_category").str.to_lowercase() == "imv",
            "imv",
        ),
        _flag(crrt, stays, "recorded_dttm", pl.lit(True), "crrt"),
        _flag(
            vit,
            stays,
            "recorded_dttm",
            (pl.col("vital_category") == "map") & (pl.col("vital_value") < 65),
            "map_lt_65",
        ),
        _flag(labs, stays, "t", lab("lactate", lambda v: v > 2), "lactate_gt_2"),
        _flag(labs, stays, "t", lab("creatinine", lambda v: v > 2), "creatinine_gt_2"),
        _flag(
            labs,
            stays,
            "t",
            lab("platelet_count", lambda v: v < 100),
            "platelets_lt_100",
        ),
    ]
    spo2 = _flag(
        vit,
        stays,
        "recorded_dttm",
        (pl.col("vital_category") == "spo2") & (pl.col("vital_value") < 90),
        "hyp_a",
    )
    fio2 = _flag(resp, stays, "recorded_dttm", pl.col("fio2_set") >= 0.6, "hyp_b")
    out = stays.lazy()
    for f in [*flags, spo2, fio2]:
        out = out.join(f, on=HOSP, how="left")
    out = out.with_columns(
        *(pl.col(p).fill_null(0) for p in POINTS[:-1]),
        hypoxia=(
            (pl.col("hyp_a").fill_null(0) + pl.col("hyp_b").fill_null(0)) > 0
        ).cast(pl.Int32),
    ).drop("hyp_a", "hyp_b")
    return out.with_columns(score=pl.sum_horizontal(*POINTS)).collect().sort(HOSP)


def select_rooms(scored: pl.DataFrame, n: int = N_ROOMS, seed: int = SEED):
    """the median band, one stay per patient, a seeded draw -> (rooms, info)"""
    s = scored["score"].to_numpy()
    width = 10  # percentile points either side of the median: p40 to p60
    while True:
        lo = float(np.percentile(s, 50 - width, method="lower"))
        hi = float(np.percentile(s, 50 + width, method="higher"))
        band = scored.filter(pl.col("score").is_between(lo, hi))
        one = band.sort(HOSP).unique(
            subset="patient_id", keep="first", maintain_order=True
        )
        if one.height >= n or width >= 50:
            break
        width += 5
    if one.height < n:
        raise SystemExit(f"only {one.height} eligible patients, need {n}")
    order = np.random.default_rng(seed).permutation(one.height)[:n]
    rooms = one[order.tolist()].with_columns(room=pl.Series(range(1, n + 1)))
    info = {
        "eligible_stays": scored.height,
        "eligible_patients": scored["patient_id"].n_unique(),
        "band_percentiles": [50 - width, 50 + width],
        "band_scores": [lo, hi],
        "band_stays": band.height,
        "band_patients": one.height,
        "selected": rooms.height,
        "score_counts": dict(
            sorted(
                (int(k), int(v)) for k, v in rooms["score"].value_counts().iter_rows()
            )
        ),
    }
    return rooms.select("room", HOSP, "score"), info


def digest(rooms: pl.DataFrame) -> str:
    """12 hex digits of the sorted ids, to compare two lists without showing them"""
    ids = "\n".join(sorted(rooms[HOSP].to_list())).encode()
    return hashlib.sha256(ids).hexdigest()[:12]


def read_ward_ids(path: pathlib.Path) -> list[str]:
    """the `hospitalization_id` column of a parquet or csv file, as sorted unique
    strings; refuses a file without that column or with no ids"""
    path = pathlib.Path(path)
    if not path.is_file():
        raise SystemExit(f"--ward-ids: {path.name} not found")
    if path.suffix.lower() == ".parquet":
        if HOSP not in pl.read_parquet_schema(path):
            raise SystemExit(f"--ward-ids: {path.name} has no {HOSP} column")
        col = pl.read_parquet(path, columns=[HOSP])[HOSP]
    else:
        df = pl.read_csv(path, schema_overrides={HOSP: pl.String})
        if HOSP not in df.columns:
            raise SystemExit(f"--ward-ids: {path.name} has no {HOSP} column")
        col = df[HOSP]
    ids = sorted(set(col.cast(pl.String).drop_nulls().to_list()))
    if not ids:
        raise SystemExit(f"--ward-ids: {path.name} holds no ids")
    return ids


def rooms_from_ids(ids: list[str], seed: int = SEED) -> pl.DataFrame:
    """a given ward -> the stage-ward csv frame (room, hospitalization_id, score).
    Rooms 1..n follow a seeded permutation of the sorted ids: the same map on every
    run, and a room number says nothing about the id or the admission time."""
    ids = sorted(set(ids))
    order = np.random.default_rng(seed).permutation(len(ids))
    return pl.DataFrame(
        {
            "room": range(1, len(ids) + 1),
            HOSP: [ids[i] for i in order],
            "score": [None] * len(ids),
        },
        schema={"room": pl.Int64, HOSP: pl.String, "score": pl.Int64},
    )


def ward_from_ids(
    clif_dir: pathlib.Path,
    ward_ids: pathlib.Path,
    real_ward: bool = False,
    seed: int = SEED,
) -> tuple[pl.DataFrame, dict]:
    """the room map for a given list of stays, and counts for the log. Without
    `real_ward` every id must be in the open demo (aggregate.check_ward refuses,
    counts only); every id must be in `clif_dir`/clif_hospitalization.parquet."""
    ids = read_ward_ids(ward_ids)
    rooms = rooms_from_ids(ids, seed)
    ward = aggregate.check_ward(dict(zip(rooms[HOSP], rooms["room"])), real_ward)
    hosp = pathlib.Path(clif_dir) / "clif_hospitalization.parquet"
    if not hosp.is_file():
        raise SystemExit(f"required table {hosp.name} not found in {hosp.parent.name}/")
    known = set(pl.read_parquet(hosp, columns=[HOSP])[HOSP].cast(pl.String))
    missing = sum(i not in known for i in ids)
    if missing:
        raise SystemExit(
            f"{missing} of {len(ids)} ward ids are not in "
            f"{hosp.parent.name}/{hosp.name}: wrong CLIF folder for this ward"
        )
    info = {"selected": rooms.height, "ward": ward["source"], "seed": seed}
    if not real_ward:  # a digest of real ids is not printed
        info["ids_digest"] = digest(rooms)
    return rooms, info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "demo_dir", type=pathlib.Path, help="folder of the clif_demo tables"
    )
    ap.add_argument(
        "--out", type=pathlib.Path, required=True, help="csv on a cluster volume"
    )
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n", type=int, default=N_ROOMS)
    ap.add_argument(
        "--ward-ids",
        type=pathlib.Path,
        help="parquet or csv with a hospitalization_id column: the ward is exactly "
        "these stays (no selection); rooms follow a seeded shuffle",
    )
    ap.add_argument(
        "--real-ward",
        action="store_true",
        help="with --ward-ids: the ids are real MIMIC-IV stays (outside the open "
        "demo); refused without this flag. The csv stays on local or cluster storage",
    )
    a = ap.parse_args()
    if a.real_ward and not a.ward_ids:
        raise SystemExit("--real-ward needs --ward-ids (the selection is open-demo)")
    if a.ward_ids:
        rooms, info = ward_from_ids(a.demo_dir, a.ward_ids, a.real_ward, a.seed)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        rooms.write_csv(a.out)
        print(info)  # counts only
        return
    scored = score_stays(a.demo_dir, eligible_stays(a.demo_dir))
    rooms, info = select_rooms(scored, a.n, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    rooms.write_csv(a.out)
    print({**info, "seed": a.seed, "ids_digest": digest(rooms)})  # counts only


if __name__ == "__main__":
    main()

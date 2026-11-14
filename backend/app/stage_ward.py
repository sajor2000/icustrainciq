"""Pick the stage ward: 25 open MIMIC-IV Demo ICU stays, the same way every time.

Usage: python app/stage_ward.py clif_demo --out /rows/stage/stage_ward.csv
         [--seed 20261114] [--n 25]

Reads only the CLIF demo tables (clif_adt, clif_hospitalization, clif_vitals,
clif_labs, clif_medication_admin_continuous, clif_respiratory_support,
clif_crrt_therapy) and needs no GPU, no model and no network, so the selection
can be reproduced inside the cluster from the open data in the repo.

Rule (docs/LIVE_DEMO.md section 1, docs/DECISIONS.md D6, D10):
 1. a stay is eligible when it reaches ICU and is still in the ICU, and still in
    hospital, 24 h after the first ICU arrival (the cut of examples/winnow_24h.yaml);
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
"""

import argparse
import hashlib
import pathlib

import numpy as np
import polars as pl

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
    a = ap.parse_args()
    scored = score_stays(a.demo_dir, eligible_stays(a.demo_dir))
    rooms, info = select_rooms(scored, a.n, a.seed)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    rooms.write_csv(a.out)
    print({**info, "seed": a.seed, "ids_digest": digest(rooms)})  # counts only


if __name__ == "__main__":
    main()

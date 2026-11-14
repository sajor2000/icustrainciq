"""What is running at the 07:00 cut, read from raw CLIF (CLIF 2.1) instead of tokens.

The tokenized `LABEL//imv_at_cut`, `pressor_at_cut`, `crrt_at_cut` flags drop CLIF's
stop signals (a vasopressor stop is only a dose 0 or nothing; CRRT has none), so
`--clif-now <clif dir>` replaces them for the "on now" tags, `life_support.now` and
the new-start exclusion (docs/CONTRACT.md `on_now_source`). Stdlib + polars only.

Rules, per stay, looking back from its cut:
  imv          last non-null device_category row at or before the cut, within 24 h:
               IMV -> True, any other device -> False, none -> None (unknown)
  vasopressor  per pressor, the last row in the 24 h up to the cut: `stop` -> not
               running; start / dose_change / going -> running when the dose is > 0
               (a null dose carries the last non-null dose since the last stop; none
               at all counts as running, the charted action says it was). True when
               any pressor runs; no pressor rows in 24 h -> False
  crrt         a crrt_therapy row in the 6 h up to the cut with blood_flow_rate > 0,
               or a null rate with a mode -> True; else False

Times: CLIF datetimes are UTC; a naive `cut` is read as UTC. The stage ward's cut is
per stay in the data's own timeline (first ICU arrival + 24 h + the demo clock, as
the winnower sets it, `stay_cuts`), not the site's wall-clock 07:00.
"""

import datetime as dt
import pathlib

import polars as pl

HOSP = "hospitalization_id"
PRESSORS = (
    "angiotensin",
    "dopamine",
    "epinephrine",
    "norepinephrine",
    "phenylephrine",
    "vasopressin",
)  # same list as aggregate.PRESSORS / app/stage_ward.py
LOOKBACK = dt.timedelta(hours=24)
CRRT_LOOKBACK = dt.timedelta(hours=6)
SUPPORTS = ("imv", "vasopressor", "crrt")
RUNNING_ACTIONS = ("start", "dose_change", "going")


def _utc(c: str) -> pl.Expr:
    """a CLIF datetime column as UTC (naive columns are taken as UTC)"""
    return pl.col(c).cast(pl.Datetime("us", "UTC"), strict=False).alias(c)


def _utc_dt(x: dt.datetime) -> dt.datetime:
    return (
        x.replace(tzinfo=dt.timezone.utc)
        if x.tzinfo is None
        else x.astimezone(dt.timezone.utc)
    )


def _cuts_frame(stays: dict) -> pl.DataFrame:
    return pl.DataFrame(
        {HOSP: [str(k) for k in stays], "cut": [_utc_dt(v) for v in stays.values()]},
        schema={HOSP: pl.String, "cut": pl.Datetime("us", "UTC")},
    )


def _read(clif: pathlib.Path, table: str, cols: list[str], times: list[str]):
    f = pathlib.Path(clif) / f"clif_{table}.parquet"
    lf = pl.scan_parquet(f).select(cols)
    return lf.with_columns(pl.col(HOSP).cast(pl.String), *(_utc(t) for t in times))


def _window(lf: pl.LazyFrame, cuts: pl.LazyFrame, time: str, span: dt.timedelta):
    """rows in (cut - span, cut]"""
    return (
        lf.join(cuts, on=HOSP)
        .filter(pl.col(time) <= pl.col("cut"))
        .filter(pl.col(time) > pl.col("cut") - span)
    )


def _imv(clif, cuts: pl.LazyFrame) -> dict[str, bool]:
    r = _read(
        clif,
        "respiratory_support",
        [HOSP, "recorded_dttm", "device_category"],
        ["recorded_dttm"],
    ).filter(pl.col("device_category").is_not_null())
    last = (
        _window(r, cuts, "recorded_dttm", LOOKBACK)
        .sort(HOSP, "recorded_dttm", maintain_order=True)
        .group_by(HOSP)
        .agg(pl.col("device_category").last())
        .collect()
    )
    return {
        h: str(d).strip().lower() == "imv"
        for h, d in zip(last[HOSP], last["device_category"])
    }


def _pressor(clif, cuts: pl.LazyFrame) -> dict[str, bool]:
    m = _read(
        clif,
        "medication_admin_continuous",
        [HOSP, "admin_dttm", "med_category", "mar_action_category", "med_dose"],
        ["admin_dttm"],
    ).filter(pl.col("med_category").str.to_lowercase().is_in(PRESSORS))
    rows = (
        _window(m, cuts, "admin_dttm", LOOKBACK)
        .with_columns(
            pl.col("med_category").str.to_lowercase(),
            stop=pl.col("mar_action_category").str.to_lowercase() == "stop",
        )
        .sort(HOSP, "med_category", "admin_dttm", maintain_order=True)
        .with_columns(  # a stop closes the infusion: later nulls do not reach past it
            seg=pl.col("stop")
            .cum_sum()
            .shift(1, fill_value=0)
            .over(HOSP, "med_category")
        )
        .with_columns(
            dose=pl.col("med_dose").forward_fill().over(HOSP, "med_category", "seg")
        )
        .group_by(HOSP, "med_category")
        .agg(
            pl.col("stop").last().alias("stopped"),
            pl.col("mar_action_category").str.to_lowercase().last().alias("act"),
            pl.col("dose").last().alias("dose"),
        )
        .with_columns(
            running=(~pl.col("stopped"))
            & pl.col("act").is_in(RUNNING_ACTIONS)
            & (pl.col("dose").is_null() | (pl.col("dose") > 0))
        )
        .group_by(HOSP)
        .agg(pl.col("running").any())
        .collect()
    )
    return dict(zip(rows[HOSP], rows["running"]))


def _crrt(clif, cuts: pl.LazyFrame) -> dict[str, bool]:
    c = _read(
        clif,
        "crrt_therapy",
        [HOSP, "recorded_dttm", "crrt_mode_category", "blood_flow_rate"],
        ["recorded_dttm"],
    )
    rows = (
        _window(c, cuts, "recorded_dttm", CRRT_LOOKBACK)
        .filter(
            (pl.col("blood_flow_rate") > 0)
            | (
                pl.col("blood_flow_rate").is_null()
                & pl.col("crrt_mode_category").is_not_null()
            )
        )
        .select(HOSP)
        .unique()
        .collect()
    )
    return {h: True for h in rows[HOSP]}


def running_at_cut(clif_dir, stays: dict) -> dict[str, dict]:
    """{id: {"imv": bool|None, "vasopressor": bool|None, "crrt": bool|None}} for
    each id in `stays` ({hospitalization_id: cut datetime}); see the module doc.
    Vasopressor and CRRT are always a bool (no rows means not running); IMV is None
    when the stay has no device record in the 24 h before its cut."""
    if not stays:
        return {}
    cuts = _cuts_frame(stays).lazy()
    imv, pressor, crrt = (
        _imv(clif_dir, cuts),
        _pressor(clif_dir, cuts),
        _crrt(clif_dir, cuts),
    )
    return {
        str(k): {
            "imv": imv.get(str(k)),
            "vasopressor": bool(pressor.get(str(k), False)),
            "crrt": bool(crrt.get(str(k), False)),
        }
        for k in stays
    }


def stay_cuts(
    clif_dir, ids: list[str], demo_clock_hours: float = 0
) -> dict[str, dt.datetime]:
    """each stay's cut in the data's timeline: first ICU arrival (clif_adt) + 24 h +
    the demo clock, as icutwin-winnow places it. Refuses ids with no ICU arrival or
    not in clif_hospitalization (counts only, never ids)."""
    clif = pathlib.Path(clif_dir)
    hosp = set(
        pl.read_parquet(clif / "clif_hospitalization.parquet", columns=[HOSP])[HOSP]
        .cast(pl.String)
        .to_list()
    )
    missing = sum(i not in hosp for i in ids)
    if missing:
        raise SystemExit(
            f"{missing} of {len(ids)} stays are not in {clif.name}/"
            "clif_hospitalization.parquet: wrong --clif-now folder"
        )
    adt = (
        _read(clif, "adt", [HOSP, "in_dttm", "location_category"], ["in_dttm"])
        .filter(pl.col("location_category").str.to_lowercase() == "icu")
        .filter(pl.col(HOSP).is_in(ids))
        .group_by(HOSP)
        .agg(pl.col("in_dttm").min())
        .collect()
    )
    arrival = dict(zip(adt[HOSP], adt["in_dttm"]))
    if len(arrival) < len(set(ids)):
        raise SystemExit(
            f"{len(set(ids)) - len(arrival)} of {len(set(ids))} stays have no ICU "
            f"arrival in {clif.name}/clif_adt.parquet"
        )
    shift = dt.timedelta(hours=24 + float(demo_clock_hours))
    return {i: arrival[i] + shift for i in ids}


VITALS = ("heart_rate", "map", "spo2", "respiratory_rate")  # the room view's four
VITALS_HOURS = 12


def vitals_before_cut(clif_dir, stays: dict) -> dict[str, dict]:
    """{id: {vital: [{"h": 1..12, "v": value}]}} for the room view: the hourly median
    of each of VITALS in the 12 h up to each stay's cut, most recent first. `h` is
    hours before the cut, rounded up and at least 1 (as rooms.json `past_12h`), so
    no date of the source data is written. Hours with no reading are left out; a
    stay with none is not in the result. {} when the folder has no vitals table."""
    f = pathlib.Path(clif_dir) / "clif_vitals.parquet"
    if not stays or not f.exists():
        return {}
    cols = [HOSP, "recorded_dttm", "vital_category", "vital_value"]
    lf = _read(clif_dir, "vitals", cols, ["recorded_dttm"]).filter(
        pl.col("vital_category").is_in(VITALS) & pl.col("vital_value").is_not_null()
    )
    span = dt.timedelta(hours=VITALS_HOURS)
    ago = (pl.col("cut") - pl.col("recorded_dttm")).dt.total_seconds()
    rows = (
        _window(lf, _cuts_frame(stays).lazy(), "recorded_dttm", span)
        .with_columns(
            (ago / 3600).ceil().clip(1, VITALS_HOURS).cast(pl.Int32).alias("h")
        )
        .group_by(HOSP, "vital_category", "h")
        .agg(pl.col("vital_value").median().alias("v"))
        .sort(HOSP, "vital_category", "h")
        .collect()
    )
    out: dict[str, dict] = {}
    for sid, cat, hh, v in rows.iter_rows():
        series = out.setdefault(sid, {}).setdefault(cat, [])
        series.append({"h": int(hh), "v": round(float(v), 1)})
    return out


def vitals_for_stays(clif_dir, ids: list[str], demo_clock_hours: float = 0) -> dict:
    """vitals_before_cut at each stay's own cut (`stay_cuts`)"""
    ids = list(dict.fromkeys(ids))
    return vitals_before_cut(clif_dir, stay_cuts(clif_dir, ids, demo_clock_hours))


def running_for_stays(clif_dir, ids: list[str], demo_clock_hours: float = 0) -> dict:
    """running_at_cut at each stay's own cut (`stay_cuts`)"""
    ids = list(dict.fromkeys(ids))
    return running_at_cut(clif_dir, stay_cuts(clif_dir, ids, demo_clock_hours))

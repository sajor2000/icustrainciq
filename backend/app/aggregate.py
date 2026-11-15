"""Per-stay outcome probabilities (icutwin-gen-score) -> unit counts, 80% range.

Usage: python app/aggregate.py <tokenized_output> <forecast.json>
         [--beds 25] [--seed 7] [--score rep|mc] [--baseline <training folder>]
         [--capacity capacity.json] [--demo-clock-hours H] [--cut-time ISO]
         [--tz America/Chicago] [--stage-csv stage_ward.csv] [--real-ward]

The Lookahead forecast.json (life support now and expected new, yardstick, check_first)
is described in docs/CONTRACT.md; flags in docs/LIVE_DEMO.md "Forecast CLI".
The stage ward is the open MIMIC-IV Demo: a --stage-csv with a stay id that is not in
clif_demo/clif_hospitalization.parquet is refused unless --real-ward is given (real
MIMIC-IV, local only; forecast.json then says so in its "ward" block).
Unit counts are exact Poisson-binomial (p10 / p50 / p90 = smallest count whose
cumulative probability reaches 10 / 50 / 90%).

--score rep (default, the board): reads scores-rep-based-*.parquet from
icutwin-rep-score: one probe probability per stay per task for the next 24 h;
five predictions in RESOURCES_REP (D8).
--score mc: the earlier Monte Carlo path (scores-generative-*.parquet), kept
for reference.

Reads scores-generative-*.parquet, takes `--beds` held-out stays as the unit, and treats
each stay's MC score as an independent event probability. The unit count for an outcome
is then a sum of Bernoulli draws (Poisson-binomial); 10,000 draws give p10/p50/p90.
Each resource names the team that prepares for it: pharmacy, respiratory therapy,
the bed manager, or the ICU team (nurses and physicians, who review every row).
A resource with several tokens (e.g. any vasopressor, any dose bin) uses the
largest per-token probability, a lower bound on "any of them".
For the bed manager, net ICU beds = arrivals (ICU transfer-in) minus departures
(transfer to ward or step-down, or death), simulated draw by draw. It assumes the unit
is the ICU's current patients and treats leaving and dying as exclusive.
Shards from the burst workflow (scores-generative-<model>-shard<i>of<n>.parquet) are
joined back into one table first.
Writes counts only: no stay ids, rows or timelines leave this script.
"""

import argparse
import datetime as dt
import fnmatch
import json
import math
import os
import pathlib
import re
import zoneinfo

import numpy as np
import polars as pl

try:  # imported as app.aggregate (tests) or run as a script (the job)
    from app import capacity as capacity_mod
    from app import clif_now as clif_now_mod
except ImportError:  # pragma: no cover
    import capacity as capacity_mod
    import clif_now as clif_now_mod

PRESSORS = [
    "angiotensin",
    "dopamine",
    "epinephrine",
    "norepinephrine",
    "phenylephrine",
    "vasopressin",
]  # same list as LABEL//pressor_init
RESOURCES = {  # bed-board name -> (team that preps, score.target_tokens patterns)
    "vasopressor": ("pharmacy", ["MED_CON//" + d + "//*" for d in PRESSORS]),
    "ventilator": ("respiratory therapy", ["RESP//device_category//imv"]),
    "nippv": ("respiratory therapy", ["RESP//device_category//nippv"]),
    "high_flow_nc": ("respiratory therapy", ["RESP//device_category//high_flow_nc"]),
    "icu_admission": ("ICU team", ["ADT//TRANSFER_IN//icu"]),
    "death": ("ICU team", ["HOSP//discharge_category//expired"]),
    "icu_departure": (
        "bed manager",
        ["ADT//TRANSFER_IN//ward", "ADT//TRANSFER_IN//stepdown"],
    ),
}


# the board's five predictions under probe scoring (docs/DECISIONS.md D2, D8): one
# forward pass per patient, a probe per task, probability of the event in the next 24 h
RESOURCES_REP = {
    "ventilator": ("respiratory therapy", ["RESP//device_category//imv"]),
    "vasopressor": ("pharmacy", ["LABEL//pressor_init"]),
    "crrt": ("ICU team", ["LABEL//crrt_init"]),
    "death": ("ICU team", ["HOSP//discharge_category//expired"]),
    "icu_departure": (
        "bed manager",
        ["ADT//TRANSFER_IN//ward", "ADT//TRANSFER_IN//stepdown"],
    ),
}


# what is running at the cut: the winnower's at_cut columns (icutwin/config/
# winnowing.yaml); older label files only have `_past` (started at any time)
AT_CUT_COL = {
    "imv": "LABEL//imv_at_cut",
    "vasopressor": "LABEL//pressor_at_cut",
    "crrt": "LABEL//crrt_at_cut",
}


def now_iso() -> str:
    """UTC with an offset (the job container's clock is not the hospital's): the board
    converts it to local time and works out how old the forecast is"""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: pathlib.Path, obj: dict) -> None:
    """write then rename, so the board never reads a half-written forecast.json"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)


def _summary(sums: np.ndarray, expected: float) -> dict:
    p10, p50, p90 = np.percentile(sums, [10, 50, 90])
    return {
        "p10": int(p10),
        "p50": int(p50),
        "p90": int(p90),
        "expected": round(float(expected), 2),
    }


def _draw(p: np.ndarray, rng: np.random.Generator, draws: int) -> np.ndarray:
    return (rng.random((draws, p.size)) < p).sum(axis=1)


def pb_pmf(p: np.ndarray) -> np.ndarray:
    """exact Poisson-binomial pmf of the number of events (index k = k events);
    NaN counts as 0 (the event cannot happen or the probe was skipped)"""
    p = np.nan_to_num(np.asarray(p, float), nan=0.0).clip(0.0, 1.0)
    pmf = np.zeros(p.size + 1)
    pmf[0] = 1.0
    for i, q in enumerate(p):  # O(n^2): the unit is tens of beds
        pmf[1 : i + 2] = pmf[1 : i + 2] * (1 - q) + pmf[: i + 1] * q
        pmf[0] *= 1 - q
    return pmf


def pmf_quantiles(pmf: np.ndarray, shift: int = 0) -> dict:
    """p10 / p50 / p90 of a count distribution: the smallest k whose cdf reaches q"""
    cdf = np.cumsum(pmf)
    q = lambda x: int(np.searchsorted(cdf, x - 1e-12)) + shift  # noqa: E731
    return {"p10": q(0.10), "p50": q(0.50), "p90": q(0.90)}


def unit_counts(
    p: np.ndarray, rng: np.random.Generator | None = None, draws: int = 10_000
) -> dict:
    """exact Poisson-binomial summary (rng and draws are kept for old callers)"""
    p = np.nan_to_num(p, nan=0.0).clip(0.0, 1.0)
    return {**pmf_quantiles(pb_pmf(p)), "expected": round(float(p.sum()), 2)}


def net_beds(
    p_in: np.ndarray, p_out: np.ndarray, rng: np.random.Generator, draws: int = 10_000
) -> dict:
    """ICU beds needed minus beds freed; negative means beds free up."""
    p_in = np.nan_to_num(p_in, nan=0.0).clip(0.0, 1.0)
    p_out = np.nan_to_num(p_out, nan=0.0).clip(0.0, 1.0)
    sums = _draw(p_in, rng, draws) - _draw(p_out, rng, draws)
    return _summary(sums, p_in.sum() - p_out.sum())


LABELS = {
    "24h": "Next 24 h (Day 1)",
    "48h": "Within 48 h",
    "72h": "Within 72 h",
    "stay": "Rest of stay",
}


EXCLUSIVE = {"icu_departure"}  # tokens that cannot both happen: probabilities add


def _combine(name: str, x: np.ndarray) -> np.ndarray:
    """one probability per stay from a resource's token columns (NaN counts as 0):
    mutually exclusive tokens (ward vs step-down transfer) add, clipped to 1; any-of
    tokens (a vasopressor drug) take the largest, a lower bound on "any of them"."""
    x = np.nan_to_num(x, nan=0.0).clip(0.0, 1.0)
    if name in EXCLUSIVE:
        return x.sum(axis=1).clip(0.0, 1.0)
    return x.max(axis=1)


def unit_probs(
    unit: pl.DataFrame, suffix: str, resources: dict | None = None
) -> dict[str, np.ndarray]:
    """per-resource probability per stay for one horizon (score column suffix).

    "Already happened" comes from the winnower's flags only (running at the cut, or
    `<task>_past`), plus NaN in the Monte Carlo scorer's own past mask. A NaN from a
    probe that was skipped (one class in training) is not "already": a resource whose
    every scorable stay is NaN comes back all NaN, meaning no data (not zero).
    """
    resources = resources or RESOURCES
    nan_is_past = suffix != "_rep_score"  # probe scores carry no NaN past mask
    scores = {c.removesuffix(suffix): c for c in unit.columns if c.endswith(suffix)}
    probs = {}
    for name, (_, patterns) in resources.items():
        cols = [
            c for t, c in scores.items() if any(fnmatch.fnmatch(t, p) for p in patterns)
        ]
        if not cols:
            continue
        x = unit.select(cols).to_numpy().astype(float)
        mask = np.zeros(x.shape, bool)
        past = [f"{c.removesuffix(suffix)}_past" for c in cols]
        key = next((k for k, r in SUPPORT_RESOURCE.items() if r == name), None)
        if AT_CUT_COL.get(key) in unit.columns:
            # running at the cut; a support stopped before it is forecastable
            mask[:] = unit[AT_CUT_COL[key]].to_numpy().astype(bool)[:, None]
        elif all(c in unit.columns for c in past):
            mask = unit.select(past).to_numpy().astype(bool)
        if nan_is_past:
            mask |= np.isnan(x)
        already = mask.any(axis=1)
        x[mask] = np.nan
        scorable = ~already
        if scorable.any() and np.isnan(x[scorable]).all():
            probs[name] = np.full(unit.height, np.nan)  # probe skipped: no data
            continue
        # a past hit means the patient is already on it: not a new start, so 0
        probs[name] = np.where(already, 0.0, _combine(name, x))
    return probs


def unavailable(p: np.ndarray) -> bool:
    """True for a resource with no data (every stay NaN: its probe was skipped)"""
    return p.size > 0 and bool(np.isnan(p).all())


def _counts_or_none(p: np.ndarray, rng: np.random.Generator | None = None) -> dict:
    """unit_counts plus `available`; a skipped probe gives null counts, never 0"""
    if unavailable(p):
        return {
            "available": False,
            "p10": None,
            "p50": None,
            "p90": None,
            "expected": None,
        }
    return {"available": True, **unit_counts(p, rng)}


def strain(
    probs: dict[str, np.ndarray],
    rng: np.random.Generator,
    resources: dict | None = None,
) -> dict:
    """unit counts per resource, plus net ICU beds for the bed manager"""
    resources = resources or RESOURCES
    out = {
        name: {"team": resources[name][0], **_counts_or_none(p, rng)}
        for name, p in probs.items()
    }
    if "icu_admission" in probs and "icu_departure" in probs:
        leave = probs["icu_departure"] + probs.get("death", 0.0)
        out["icu_beds_net"] = {
            "team": "bed manager",
            **net_beds(probs["icu_admission"], leave, rng),
        }
    return out


def already_started(unit: pl.DataFrame) -> dict[str, int]:
    """acuity now: stays whose vasopressor or ventilator began before the cut
    (the scorer leaves those NaN). A count, not a current-census measure."""
    out = {}
    for name in ("vasopressor", "ventilator"):
        patterns = RESOURCES[name][1]
        cols = [
            c
            for c in unit.columns
            if c.endswith("_mc_score")
            and any(fnmatch.fnmatch(c.removesuffix("_mc_score"), p) for p in patterns)
        ]
        if cols:
            x = unit.select(cols).to_numpy().astype(float)
            out[name] = int(np.isnan(x).any(axis=1).sum())
    return out


STRAIN_BANDS = ((0.8, "QUIET"), (1.2, "USUAL"), (1.6, "BUSY"))  # as the board mockup
ABOVE_USUAL = 1.25  # a task is "above its usual" when forecast / typical reaches this


def band_of(ratio: float) -> str:
    for upper, word in STRAIN_BANDS:
        if ratio < upper:
            return word
    return "VERY BUSY"


def typical_rates(
    labels: pl.DataFrame, resources: dict | None = None
) -> dict[str, float]:
    """new events per stay in a typical 24 h, from training labels.

    labels: train_for_inference.parquet (one row per training stay, cut 24 h after
    ICU arrival, `<token>_past` / `<token>_future` flags). A task's rate is the
    share of training stays with the event in the next 24 h and not already
    happening: for a life support that is "running at the cut" (`at_cut` columns,
    else `_past`), the same rule unit_probs applies to the forecast, so a support
    that stopped before the cut stays forecastable on both sides of the ratio.
    """
    resources = resources or RESOURCES_REP
    rates = {}
    for name, (_, patterns) in resources.items():
        toks = [
            c.removesuffix("_future")
            for c in labels.columns
            if c.endswith("_future")
            and f"{c.removesuffix('_future')}_past" in labels.columns
            and any(fnmatch.fnmatch(c.removesuffix("_future"), p) for p in patterns)
        ]
        if not toks or not labels.height:
            continue
        fut = labels.select([f"{t}_future" for t in toks]).to_numpy().astype(bool)
        past = labels.select([f"{t}_past" for t in toks]).to_numpy().astype(bool)
        key = next((k for k, r in SUPPORT_RESOURCE.items() if r == name), None)
        at_cut = AT_CUT_COL.get(key)
        busy = (
            labels[at_cut].to_numpy().astype(bool)
            if at_cut in labels.columns
            else past.any(axis=1)
        )
        rates[name] = float((fut.any(axis=1) & ~busy).mean())
    return rates


def strain_index(
    probs: dict[str, np.ndarray],
    rates: dict[str, float],
    rng: np.random.Generator,
    draws: int = 10_000,
) -> dict | None:
    """unit strain: new events forecast across the board tasks / a typical day.

    typical_day = beds x the training rate of each task (mean `_future` among stays
    not already on); ratio = simulated total new events / typical_day, with an 80%
    range; band words as on the board (QUIET < 0.8 <= USUAL < 1.2 <= BUSY < 1.6).
    A forecast summary against the unit's own norm, not a validated outcome score.
    """
    tasks = [t for t in probs if t in rates and not unavailable(probs[t])]
    beds = max((p.size for p in probs.values()), default=0)
    typical = {t: beds * rates[t] for t in tasks}
    total_typical = sum(typical.values())
    if not tasks or total_typical <= 0:
        return None
    clean = {t: np.nan_to_num(probs[t], nan=0.0).clip(0.0, 1.0) for t in tasks}
    totals = sum(_draw(p, rng, draws) for p in clean.values())
    ratio = totals / total_typical
    p10, p50, p90 = np.percentile(ratio, [10, 50, 90])
    expected = {t: float(clean[t].sum()) for t in tasks}
    per_task = {
        t: {
            "typical": round(typical[t], 2),
            "expected": round(expected[t], 2),
            "ratio": round(expected[t] / typical[t], 2) if typical[t] > 0 else None,
        }
        for t in tasks
    }
    return {
        "beds": beds,
        "tasks": tasks,
        "typical_day": round(total_typical, 2),
        "expected": round(sum(expected.values()), 2),
        "ratio": {
            "p10": round(float(p10), 2),
            "p50": round(float(p50), 2),
            "p90": round(float(p90), 2),
        },
        "band": band_of(float(p50)),
        "above_usual": sorted(
            (t for t, v in per_task.items() if (v["ratio"] or 0) >= ABOVE_USUAL),
            key=lambda t: -per_task[t]["ratio"],
        ),
        "per_task": per_task,
        "baseline": "training stays: mean new-event rate per task x beds",
    }


# ---- Lookahead (docs/DECISIONS.md D8, docs/CONTRACT.md): life support, yardstick ----
SUPPORTS = ("imv", "vasopressor", "crrt")  # life support the board counts
SUPPORT_RESOURCE = {"imv": "ventilator", "vasopressor": "vasopressor", "crrt": "crrt"}
LEVELS = {"medium": 0.2, "high": 0.4}  # any_life_support cut-offs (configurable)
OUT_TAG = 0.6  # icu_departure at or above this tags a room "out"
TYPICAL_WORDS = ((1.0, "USUAL", "ok"), (1.3, "BUSY", "amber"))  # else VERY BUSY / red
CUT_HOUR = 7  # morning rounds
DEFAULT_TZ = "America/Chicago"  # the site: t7-twin runs with TZ=America/Chicago


def _first_col(unit: pl.DataFrame, patterns: list[str], suffix: str):
    return [
        c
        for c in unit.columns
        if c.endswith(suffix)
        and any(fnmatch.fnmatch(c.removesuffix(suffix), p) for p in patterns)
    ]


def clif_override(
    ids: list[str], run: np.ndarray, clif: dict | None, key: str
) -> np.ndarray:
    """running-at-cut flags with the raw-CLIF answer (app/clif_now.py) laid over the
    token flags; a stay CLIF cannot answer for (None: no device row) keeps the token
    flag"""
    if not clif:
        return run
    out = run.copy()
    for i, sid in enumerate(ids):
        v = (clif.get(sid) or {}).get(key)
        if v is not None:
            out[i] = bool(v)
    return out


def patient_table(
    unit: pl.DataFrame, suffix: str = "_rep_score", clif: dict | None = None
) -> dict:
    """per-stay arrays for the five predictions and what is on at the cut.

    p[name]: probability of the event in the next 24 h, NaN where it cannot be a
    new event (a support running at the cut) or the probe was skipped.
    on[support]: running at the cut (the winnower's `at_cut` columns, from the
    last record before the cut); label files without them fall back to `_past`
    (started before the cut). stopped[support]: started before the cut but not
    running at it, so forecastable again.
    skipped[name]: no score although the stay is scorable (the probe was skipped in
    training or has no column): no data, which is not the same as "not a new event".
    Two tokens that exclude each other (ward / step-down) add, clipped to 1.
    clif: {stay id: {"imv", "vasopressor", "crrt"}} from app/clif_now.py (`--clif-now`);
    it replaces the token flags for `on` (and so for `stopped` and the exclusion).
    """
    n = unit.height
    ids = unit["hospitalization_id"].to_list() if clif else []
    p, on, stopped, skipped = {}, {}, {}, {}
    for name, (_, patterns) in RESOURCES_REP.items():
        cols = _first_col(unit, patterns, suffix)
        pasts = [f"{c.removesuffix(suffix)}_past" for c in cols]
        pasts = [c for c in pasts if c in unit.columns]
        x = (
            unit.select(cols).to_numpy().astype(float)
            if cols
            else np.full((n, 1), np.nan)
        )
        none = np.isnan(x).all(axis=1)
        if name in EXCLUSIVE:
            pr = np.where(none, np.nan, _combine(name, x))
        else:
            pr = np.fmax.reduce(x, axis=1)  # largest token probability, NaN ignored
        flag = (
            unit.select(pasts).to_numpy().astype(bool).any(axis=1)
            if pasts
            else np.zeros(n, bool)
        )
        key = next((s for s, r in SUPPORT_RESOURCE.items() if r == name), None)
        excluded = flag  # not scorable: the event already happened
        if key:
            at_cut = AT_CUT_COL[key]
            if at_cut in unit.columns:  # actually running at the cut
                run = unit[at_cut].to_numpy().astype(bool)
                stopped[key] = flag & ~run
            else:  # old label files: started before the cut is all we know
                run = flag
                stopped[key] = np.zeros(n, bool)
            run = clif_override(ids, run, clif, key)
            stopped[key] = flag & ~run
            on[key] = run
            excluded = run
            pr = np.where(run, np.nan, pr)
        p[name] = pr
        skipped[name] = none & ~excluded
    # vasoactive agents running at the cut: only raw CLIF can count them
    agents = [(clif or {}).get(sid, {}).get("vasoactives") for sid in ids] or [None] * n
    return {
        "p": p,
        "on": on,
        "stopped": stopped,
        "skipped": skipped,
        "vasoactives": [None if v is None else int(v) for v in agents],
    }


def p_any_life_support(p: dict[str, np.ndarray]) -> np.ndarray:
    """1 - prod(1 - p_k) over IMV, vasopressor, CRRT; a support already on has
    p = NaN and drops out of the product"""
    q = np.ones(len(next(iter(p.values()))))
    for s in SUPPORTS:
        q = q * (1.0 - np.nan_to_num(p[SUPPORT_RESOURCE[s]], nan=0.0).clip(0.0, 1.0))
    return 1.0 - q


def level_of(x: float, levels: dict | None = None) -> str:
    levels = levels or LEVELS
    return (
        "high" if x >= levels["high"] else "medium" if x >= levels["medium"] else "low"
    )


UNIT_NAME = "Medical ICU"  # forecast.json "unit_name": the page's header chip
READY, PENDING = "ready", "pending-model"  # forecast_state (docs/CONTRACT.md)
NO_COUNTS = {
    "available": False,
    "p10": None,
    "p50": None,
    "p90": None,
    "expected": None,
}
PROBE_TASKS = (
    pathlib.Path(__file__).resolve().parent.parent / "examples" / "probe_tasks.yaml"
)


def probe_tokens() -> list[str]:
    """the tokens behind the five predictions (examples/probe_tasks.yaml)"""
    import yaml

    return list(yaml.safe_load(PROBE_TASKS.read_text())["score"]["target_tokens"])


def pending_scores(root: pathlib.Path, ids: list[str] | None = None) -> pl.DataFrame:
    """the probe-score table of a ward that has no model yet: the winnower's labels
    (every <split>_for_inference.parquet, list columns left out) with each task's
    `_rep_score` NaN. Read by patient_table / build_forecast like a real one: every
    prediction is then "no data", what is on at the cut stays real."""
    parts = []
    for f in sorted(pathlib.Path(root).glob("*_for_inference.parquet")):
        cols = [
            c for c, t in pl.read_parquet_schema(f).items() if t.base_type() != pl.List
        ]
        parts.append(pl.read_parquet(f, columns=cols))
    if not parts:
        raise SystemExit(f"no *_for_inference.parquet under {root}: winnow first")
    df = pl.concat(parts, how="diagonal")
    if ids is not None:
        df = df.filter(pl.col("hospitalization_id").is_in(list(ids)))
    return df.with_columns(
        pl.lit(float("nan")).alias(f"{t}_rep_score") for t in probe_tokens()
    )


def _on_any(on: dict[str, np.ndarray]) -> np.ndarray:
    return np.any([on[s] for s in SUPPORTS], axis=0)


def _support_counts(tab: dict, support: str) -> dict:
    """new starts of one support; null counts when its probe was skipped for every
    stay not already on it (no data, never 0)"""
    name = SUPPORT_RESOURCE[support]
    sk = tab["skipped"][name]
    if sk.any() and (sk | tab["on"][support]).all():
        return _counts_or_none(np.full(sk.size, np.nan))
    return _counts_or_none(tab["p"][name])


def life_support_block(tab: dict) -> dict:
    """unit life support: on now, new patients expected, new starts by support"""
    p, on = tab["p"], tab["on"]
    any_on = _on_any(on)
    p_any = p_any_life_support(p)
    # a patient already on one support is not a *new* life-support patient, so the
    # new-patient distribution only runs over patients on none of the three
    new = unit_counts(np.where(any_on, 0.0, p_any))
    return {
        "now_patients": int(any_on.sum()),
        "now_by": {
            "imv": int(on["imv"].sum()),
            "vasopressor": int(on["vasopressor"].sum()),
            "crrt": int(on["crrt"].sum()),
            "ecmo": None,  # no ecmo/mcs token reaches the model: "not available"
        },
        "expected_new_patients": new,
        "expected_by": {s: _support_counts(tab, s) for s in SUPPORTS},
    }


STAFFING = {  # the board's staffing rule (docs/CONTRACT.md "staffing")
    "nurse_ratio": 2,  # patients per nurse, for everyone not 1:1
    "one_to_one_crrt": True,  # a patient on CRRT has a nurse alone
    "one_to_one_vasoactives": 2,  # ...and one on this many vasoactives (0 = off)
    "rt_ratio": 6,  # ventilated patients per respiratory therapist
}


def add_staffing_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument(
        "--nurse-ratio",
        type=int,
        default=STAFFING["nurse_ratio"],
        help="patients per nurse for those not 1:1 (default 2)",
    )
    ap.add_argument(
        "--one-to-one-vasoactives",
        type=int,
        default=STAFFING["one_to_one_vasoactives"],
        help="vasoactive infusions at which a patient is 1:1 (default 2; 0 = never)",
    )
    ap.add_argument(
        "--no-one-to-one-crrt",
        action="store_true",
        help="a patient on CRRT is not 1:1 (default: 1:1)",
    )
    ap.add_argument(
        "--rt-ratio",
        type=int,
        default=STAFFING["rt_ratio"],
        help="ventilated patients per respiratory therapist (default 6)",
    )


def staffing_rules(a) -> dict:
    """the rule set from parsed arguments (add_staffing_args)"""
    if a.nurse_ratio < 1 or a.rt_ratio < 1 or a.one_to_one_vasoactives < 0:
        raise SystemExit("staffing ratios must be whole numbers of 1 or more")
    return {
        "nurse_ratio": a.nurse_ratio,
        "one_to_one_crrt": not a.no_one_to_one_crrt,
        "one_to_one_vasoactives": a.one_to_one_vasoactives,
        "rt_ratio": a.rt_ratio,
    }


def _ceil_div(n, d: int):
    return -(-n // d)


def _through(q: dict, f) -> dict:
    """p10 / p50 / p90 of f(count) for a non-decreasing f: the quantiles map through"""
    return {k: int(f(q[k])) for k in ("p10", "p50", "p90")}


def staffing_blocks(
    tab: dict, rules: dict | None = None, pending: bool = False
) -> tuple[dict, dict]:
    """(staffing_now, staffing_next_24h) for forecast.json.

    Now: a patient is 1:1 when on CRRT or on `one_to_one_vasoactives` or more
    vasoactive infusions at the cut (the count comes from raw CLIF; without it no
    patient is 1:1 for vasoactives and `vasoactives_known` is false). nurses =
    1:1 patients + ceil(the others / nurse_ratio); rt = ceil(ventilated / rt_ratio).

    Next 24 h (exact Poisson-binomial, like the unit counts): 1:1 = those 1:1 now
    plus patients who start CRRT; rt = ceil((ventilated now + IMV starts) /
    rt_ratio). Approximations: every bed stays filled (no one leaves or stops a
    support), and a second vasoactive started in the window is not forecast, so
    only patients already at the vasoactive count now are 1:1 for that reason."""
    r = {**STAFFING, **(rules or {})}
    on = tab["on"]
    n = int(on["imv"].size)
    agents = tab.get("vasoactives") or [None] * n
    known = n > 0 and all(v is not None for v in agents)
    many = np.array(
        [
            bool(r["one_to_one_vasoactives"])
            and v is not None
            and v >= r["one_to_one_vasoactives"]
            for v in agents
        ],
        bool,
    )
    alone = many | (on["crrt"] if r["one_to_one_crrt"] else np.zeros(n, bool))
    vented = int(on["imv"].sum())
    nurses = lambda k: k + _ceil_div(n - k, r["nurse_ratio"])  # noqa: E731
    rts = lambda v: _ceil_div(v, r["rt_ratio"])  # noqa: E731
    k = int(alone.sum())
    now = {
        "nurses": int(nurses(k)),
        "one_to_one": k,
        "one_to_two": n - k,
        "rt": int(rts(vented)),
        "vented": vented,
        "vasoactives_known": known,
        "rules": r,
    }

    def no_data(support: str) -> bool:
        sk = tab["skipped"][SUPPORT_RESOURCE[support]]
        return pending or bool(sk.any() and (sk | on[support]).all())

    nxt = {"nurses": dict(NO_COUNTS), "rt": dict(NO_COUNTS)}
    # CRRT matters only when it could move someone to 1:1 (not everyone is already)
    crrt_matters = bool(r["one_to_one_crrt"]) and not alone.all()
    if not pending and (not crrt_matters or not no_data("crrt")):
        p = tab["p"]["crrt"] if r["one_to_one_crrt"] else np.zeros(n)
        starts = pmf_quantiles(pb_pmf(np.where(alone, 0.0, np.nan_to_num(p))))
        nxt["nurses"] = {
            "available": True,
            **_through(starts, lambda s: nurses(k + s)),
            "one_to_one": _through(starts, lambda s: k + s),
        }
    if not no_data("imv"):
        starts = pmf_quantiles(pb_pmf(tab["p"]["ventilator"]))
        nxt["rt"] = {
            "available": True,
            **_through(starts, lambda s: rts(vented + s)),
            "vented": _through(starts, lambda s: vented + s),
        }
    for v in nxt.values():
        v.pop("expected", None)
    return now, nxt


CAPACITY_MAX = 50  # life-support patients a 25-bed unit could plausibly hold


def _count_like(v, lo: float = 0, hi: float = CAPACITY_MAX) -> bool:
    """a real number in [lo, hi]: a JSON int or float, not a bool or a string"""
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(v)
        and lo <= v <= hi
    )


def _capacity_raw(path: pathlib.Path | None):
    """the capacity file as parsed JSON; None when absent or not JSON"""
    if not path or not pathlib.Path(path).is_file():
        return None
    try:
        return json.loads(pathlib.Path(path).read_text())
    except (ValueError, OSError):
        return None


def read_capacity(path: pathlib.Path | None) -> dict | None:
    """the charge nurse's capacity file {life_support_patients, vents_free,
    vents_total, crrt_total, set_at, set_by_role}; None when absent or without a
    usable staffing number (the typical yardstick then applies).
    life_support_patients must be a number 0..50 (not a bool or a string); anything
    else prints one "unreadable" line and falls back to the typical yardstick,
    unless the file only carries machine totals (`read_machine_totals`)."""
    if not path or not pathlib.Path(path).is_file():
        return None
    return _capacity_of(_capacity_raw(path))


def _capacity_of(raw) -> dict | None:
    """`read_capacity` on an already parsed capacity file"""
    tot = capacity_mod.totals(raw)
    cap = raw.get("life_support_patients") if isinstance(raw, dict) else None
    if not _count_like(cap):
        machines_only = cap is None and (
            tot["vents_total"] is not None
            or tot["crrt_total"] is not None
            or isinstance(raw, dict)
            and (
                capacity_mod.whole(raw.get("nurses_on_shift")) is not None
                or capacity_mod.whole(raw.get("rt_on_shift")) is not None
            )
        )
        if not machines_only:
            print("capacity file unreadable: using the typical yardstick")
        return None
    vents = raw.get("vents_free")
    return {
        "life_support_patients": int(cap) if cap == int(cap) else cap,
        "vents_free": vents
        if _count_like(vents, 0, 1e6) and tot["vents_total"] is None
        else None,  # a total wins: free is derived from it
        "vents_total": tot["vents_total"],
        "crrt_total": tot["crrt_total"],
        "set_at": raw.get("set_at") if isinstance(raw.get("set_at"), str) else None,
        "set_by_role": raw.get("set_by_role")
        if isinstance(raw.get("set_by_role"), str)
        else None,
    }


def read_machine_totals(path: pathlib.Path | None) -> dict:
    """{"vents_total", "crrt_total", "vents_free"} from the capacity file: whole
    numbers 0..50 or None (an absent, broken or older file reads as not set)"""
    return capacity_mod.totals(_capacity_raw(path))


def machine_yardsticks(tab: dict, totals: dict, pending: bool = False) -> dict | None:
    """ventilators and CRRT machines against the unit's totals, as the page's cards:
    free = total - in use at the cut (an entered ventilators-free number wins);
    flagged = beds not on that support whose chance of starting it is FLAG_AT or
    more; SHORT when flagged > free, AT LIMIT when flagged == free and > 0, else
    ON TRACK. None when no total is set; a support without a total is None. With no
    forecast (pending, or the probe skipped) `flagged`, `words` and `level` are null:
    in use and free stay real."""
    out = {}
    for s in capacity_mod.MACHINES:
        on = tab["on"][s]
        in_use = int(on.sum())
        free = capacity_mod.free(s, totals, in_use)
        if free is None:
            out[s] = None
            continue
        name = SUPPORT_RESOURCE[s]
        p, sk = tab["p"][name], tab["skipped"][name]
        entry = {
            "total": totals.get(capacity_mod.MACHINES[s]),
            "in_use": in_use,
            "free": free,
            "flag_at": capacity_mod.FLAG_AT,
            "flagged": None,
            "short_by": None,
            "words": None,
            "level": None,
        }
        if not (pending or (sk.any() and (sk | on).all())):
            flagged = int((~on & (np.nan_to_num(p, nan=0.0) >= entry["flag_at"])).sum())
            w, lv = capacity_mod.words(flagged, free)
            entry.update(
                flagged=flagged, short_by=max(0, flagged - free), words=w, level=lv
            )
        out[s] = entry
    return out if any(v is not None for v in out.values()) else None


def typical_life_support_rate(labels: pl.DataFrame) -> float | None:
    """share of training stays on life support or starting it in a 24 h window:
    any of IMV, vasopressor, CRRT running at the cut (`at_cut`, else `_past`) or
    starting in the next 24 h (`_future` with that support not running). None if the
    training labels lack the columns (never guessed)."""
    on = np.zeros(labels.height, bool)
    for s in SUPPORTS:
        pats = RESOURCES_REP[SUPPORT_RESOURCE[s]][1]
        toks = [
            c.removesuffix("_future")
            for c in labels.columns
            if c.endswith("_future")
            and f"{c.removesuffix('_future')}_past" in labels.columns
            and any(fnmatch.fnmatch(c.removesuffix("_future"), p) for p in pats)
        ]
        if not toks:
            return None
        fut = labels.select([f"{t}_future" for t in toks]).to_numpy().astype(bool)
        past = labels.select([f"{t}_past" for t in toks]).to_numpy().astype(bool)
        at_cut = AT_CUT_COL[s]
        running = (
            labels[at_cut].to_numpy().astype(bool)
            if at_cut in labels.columns
            else past.any(axis=1)
        )
        on |= running | (fut.any(axis=1) & ~running)
    return float(on.mean()) if labels.height else None


def yardstick(
    ls: dict, beds: int, capacity: dict | None, typical_rate: float | None
) -> dict | None:
    """how loaded the unit will be: load = on now + expected new life-support
    patients (80% range). With a capacity file: ON TRACK / TIGHT / SHORT against
    it; otherwise USUAL / BUSY / VERY BUSY against the training baseline;
    None when neither exists."""
    now = ls["now_patients"]
    new = ls["expected_new_patients"]
    load = {k: now + new[k] for k in ("p10", "p50", "p90")}
    if capacity:
        cap = capacity["life_support_patients"]
        if load["p50"] > cap:
            words, level = "SHORT", "red"
        elif load["p90"] > cap:
            words, level = "TIGHT", "amber"
        else:
            words, level = "ON TRACK", "ok"
        return {
            "kind": "capacity",
            "words": words,
            "level": level,
            "capacity": {**capacity, "load": load},
            "typical": None,
        }
    if typical_rate is None or beds * typical_rate <= 0:
        return None
    typical = beds * typical_rate
    ratio = load["p50"] / typical
    words, level = "VERY BUSY", "red"
    for upper, w, lv in TYPICAL_WORDS:
        if ratio <= upper:
            words, level = w, lv
            break
    return {
        "kind": "typical",
        "words": words,
        "level": level,
        "capacity": None,
        "typical": {"life_support_patients": round(typical, 2), "load": load},
    }


def parse_cut(text: str) -> dt.datetime:
    """an ISO time that carries a UTC offset; a naive one is refused (the cut is a
    moment, and the job container's clock is not the hospital's)"""
    c = dt.datetime.fromisoformat(text)
    if c.tzinfo is None:
        raise ValueError(
            f"--cut-time {text!r} has no UTC offset: e.g. 2026-11-14T07:00:00-06:00"
        )
    return c


def cut_arg(text: str) -> str:
    """argparse type for --cut-time"""
    try:
        parse_cut(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None
    return text


def cut_time_for(
    made: dt.datetime, tz: str, cut: str | None, demo_clock_hours: float = 0
) -> dt.datetime:
    """the forecast's cut. Scheduled (demo clock 0): the 07:00 nearest to made_at in
    the site's time zone (06:30 -> today 07:00, a 08:00 rerun -> the same cut).
    Demo clock H: the ward is replayed H hours past the morning cut, so the cut is
    the last 07:00 at or before made_at plus H hours (as the dispatcher counts it).
    An explicit `cut` (ISO, with an offset) is taken as given, demo clock included."""
    if cut:
        return parse_cut(cut)
    zone = zoneinfo.ZoneInfo(tz)
    local = made.astimezone(zone)
    today = local.replace(hour=CUT_HOUR, minute=0, second=0, microsecond=0)
    if demo_clock_hours:
        last = today if today <= local else today - dt.timedelta(days=1)
        return last + dt.timedelta(hours=demo_clock_hours)
    cands = [today + dt.timedelta(days=d) for d in (-1, 0, 1)]
    return min(cands, key=lambda c: abs((c - local).total_seconds()))


def window_for(cut: dt.datetime) -> dict:
    return {
        "start": cut.isoformat(timespec="seconds"),
        "end": (cut + dt.timedelta(hours=24)).isoformat(timespec="seconds"),
    }


def read_room_map(path: pathlib.Path | None) -> dict[str, int]:
    """stage_ward.csv (room, hospitalization_id, score) -> {stay id: room}; the
    stage ward only, never for real MIMIC"""
    if not path or not pathlib.Path(path).is_file():
        return {}
    df = pl.read_csv(path, schema_overrides={"hospitalization_id": pl.String})
    return dict(zip(df["hospitalization_id"], df["room"].cast(int)))


DEMO_HOSP = (
    pathlib.Path(__file__).resolve().parent.parent
    / "clif_demo"
    / "clif_hospitalization.parquet"
)  # the git-tracked open MIMIC-IV Demo: the only ward that may leave the cluster
WARDS = {
    False: {"source": "open-demo", "label": "Open MIMIC-IV Demo"},
    True: {"source": "mimic-iv", "label": "Real MIMIC-IV · local only"},
}


def check_ward(room_of: dict[str, int], real_ward: bool) -> dict:
    """the `ward` block for rooms.json / forecast.json. Without --real-ward every
    stay id in the room map must be in the open demo's clif_hospitalization.parquet;
    otherwise refuse (a message with counts, never ids). With it, the ward is real
    MIMIC-IV: all of its data stays on the cluster volumes."""
    if not real_ward and room_of:
        try:
            demo = set(
                pl.read_parquet(DEMO_HOSP, columns=["hospitalization_id"])[
                    "hospitalization_id"
                ].cast(pl.String)
            )
        except (OSError, pl.exceptions.PolarsError):
            demo = set()
            why = f"{DEMO_HOSP.name} could not be read"
        else:
            why = f"not in {DEMO_HOSP.parent.name}/{DEMO_HOSP.name}"
        outside = sum(sid not in demo for sid in room_of)
        if outside:
            raise SystemExit(
                f"{outside} of {len(room_of)} stays in the room map are {why}: "
                "this is not the open demo ward. Re-run with --real-ward to confirm "
                "real MIMIC-IV, kept on the cluster volumes only"
            )
    return dict(WARDS[bool(real_ward)])


def check_first(unit: pl.DataFrame, tab: dict, rooms: dict[str, int], k: int = 3):
    """up to k High rooms by the new-start chance (stage ward only): the same
    quantity life_support_block counts, so a patient already on a support is 0"""
    if not rooms:
        return []
    score = np.where(_on_any(tab["on"]), 0.0, p_any_life_support(tab["p"]))
    ids = unit["hospitalization_id"].to_list()
    order = np.argsort(-score, kind="stable")
    out = []
    for i in order:
        if score[i] >= LEVELS["high"] and ids[i] in rooms and len(out) < k:
            out.append(
                {
                    "room": rooms[ids[i]],
                    "any_life_support": round(float(score[i]), 3),
                    "level": "high",
                }
            )
    return out


def build_forecast(
    df: pl.DataFrame,
    model: str,
    *,
    beds: int = 25,
    seed: int = 7,
    baseline: pathlib.Path | None = None,
    capacity: pathlib.Path | None = None,
    cut_time: str | None = None,
    tz: str = DEFAULT_TZ,
    demo_clock_hours: float = 0,
    stage_csv: pathlib.Path | None = None,
    ward: dict | None = None,
    clif_now: pathlib.Path | None = None,
    forecast_state: str = READY,
    clif: dict | None = None,
    unit_name: str = UNIT_NAME,
    staffing: dict | None = None,
) -> dict:
    """forecast.json (docs/CONTRACT.md) from a probe-score table; unit scope.
    clif_now: raw CLIF folder; what is on at the cut then comes from it (`clif`: the
    same answer already read, {stay id: {...}}, so the caller and the file agree).
    forecast_state "pending-model" (no weights or probes yet, `pending_scores`):
    what is on now stays real, every expected count is null, no yardstick."""
    unit = df.sample(n=min(beds, df.height), seed=seed)
    rng = np.random.default_rng(seed)
    if clif is None and clif_now:
        clif = clif_now_mod.running_for_stays(
            clif_now, unit["hospitalization_id"].to_list(), demo_clock_hours
        )
    tab = patient_table(unit, clif=clif)
    probs = unit_probs(unit, "_rep_score", RESOURCES_REP)
    resources = strain(probs, rng, RESOURCES_REP)
    made = dt.datetime.now(dt.timezone.utc)
    cut = cut_time_for(made, tz, cut_time, demo_clock_hours)
    labels = None
    if baseline and (baseline / "train_for_inference.parquet").is_file():
        labels = pl.read_parquet(baseline / "train_for_inference.parquet")
    else:
        print("no train_for_inference.parquet: typical yardstick left out")
    ls = life_support_block(tab)
    pending = forecast_state == PENDING
    cap_raw = _capacity_raw(capacity)  # one read: totals and cap never disagree
    totals = capacity_mod.totals(cap_raw)
    staff_now, staff_next = staffing_blocks(tab, staffing, pending)
    cap = None
    if cap_raw is not None or (capacity and pathlib.Path(capacity).is_file()):
        cap = _capacity_of(cap_raw)  # a broken file still says "unreadable"
    if cap and cap["vents_free"] is None:  # derived from the ventilator total
        cap["vents_free"] = capacity_mod.free("imv", totals, ls["now_by"]["imv"])
    if pending:  # no model: nothing is expected, nothing is 0
        resources = {
            name: {"team": team, **NO_COUNTS}
            for name, (team, _) in RESOURCES_REP.items()
        }
        ls["expected_new_patients"] = dict(NO_COUNTS)
        ls["expected_by"] = {s: dict(NO_COUNTS) for s in SUPPORTS}
    label = "Next 24 h (to 07:00 tomorrow)"
    forecast = {
        "made_at": made.isoformat(timespec="seconds"),
        "cut_time": cut.isoformat(timespec="seconds"),
        "window": window_for(cut),
        "scope": "unit",
        "unit_name": str(unit_name or UNIT_NAME)[:60],
        "ward": dict(ward or WARDS[False]),
        "forecast_state": forecast_state,
        "on_now_source": "clif" if (clif_now or clif) else "tokens",
        "demo_clock_hours": demo_clock_hours,
        "beds": unit.height,
        "range": "80% (p10-p90)",
        "resources": resources,
        "life_support": ls,
        "yardstick": None
        if pending
        else yardstick(
            ls,
            unit.height,
            cap,
            typical_life_support_rate(labels) if labels is not None else None,
        ),
        "machines": machine_yardsticks(tab, totals, pending),
        "staffing_now": staff_now,
        "staffing_next_24h": staff_next,
        "check_first": []
        if pending
        else check_first(unit, tab, read_room_map(stage_csv)),
        "levels": dict(LEVELS),
        "out_tag": OUT_TAG,
        # kept for the current board and chat (they read these with defaults)
        "method": "probe on icutwin features, one forward pass per patient",
        "default_horizon": "24h",
        "horizon": label,
        "model": model,
        "horizons": {"24h": {"label": label, "resources": resources}},
        "per_day": {},
        "already_started": {
            "ventilator": int(tab["on"]["imv"].sum()),
            "vasopressor": int(tab["on"]["vasopressor"].sum()),
        },
    }
    if labels is not None and not pending:
        st = strain_index(probs, typical_rates(labels), np.random.default_rng(seed + 1))
        if st:
            forecast["strain"] = st
    return forecast


def scores_path(root: pathlib.Path, model: str) -> pathlib.Path:
    """the probe-score table for one model (never another model's newest file)"""
    f = root / f"scores-rep-based-{model}.parquet"
    if not f.is_file():
        raise SystemExit(f"no {f.name} under {root}")
    return f


def newest_scores(root: pathlib.Path) -> tuple[pl.DataFrame, str]:
    files = sorted(root.glob("scores-rep-based-*.parquet"))
    if not files:
        raise SystemExit(f"no scores-rep-based-*.parquet under {root}")
    newest = max(files, key=lambda f: f.stat().st_mtime)
    return pl.read_parquet(newest), newest.stem.removeprefix("scores-rep-based-")


def main_rep(a) -> None:
    """probe scoring: <task>_rep_score per stay for the next 24 h, five predictions"""
    ward = check_ward(read_room_map(a.stage_csv), a.real_ward)
    df, model = newest_scores(a.tokenized_output)
    if a.clif_now:  # the open-demo guard holds for every stay read from this folder
        check_ward({i: 0 for i in df["hospitalization_id"]}, a.real_ward)
    forecast = build_forecast(
        df,
        model,
        beds=a.beds,
        seed=a.seed,
        baseline=a.baseline or a.tokenized_output,
        capacity=a.capacity,
        cut_time=a.cut_time,
        tz=a.tz,
        demo_clock_hours=a.demo_clock_hours,
        stage_csv=a.stage_csv,
        ward=ward,
        clif_now=a.clif_now,
        unit_name=a.unit_name,
        staffing=staffing_rules(a),
    )
    write_json(a.out, forecast)
    ls = forecast["life_support"]  # counts only
    print(
        json.dumps(
            {
                "made_at": forecast["made_at"],
                "beds": forecast["beds"],
                "model": model,
                "on_now_source": forecast["on_now_source"],
                "now_patients": ls["now_patients"],
                "expected_new_patients": ls["expected_new_patients"],
                "yardstick": (forecast["yardstick"] or {}).get("words"),
            }
        )
    )
    print({k: v["p50"] for k, v in forecast["resources"].items()})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tokenized_output", type=pathlib.Path)
    ap.add_argument("out", type=pathlib.Path)
    ap.add_argument("--beds", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--baseline",
        type=pathlib.Path,
        help="folder with train_for_inference.parquet for the strain index's "
        "typical day (default: tokenized_output; the stage-ward run points it "
        "at the training run)",
    )
    ap.add_argument(
        "--capacity",
        type=pathlib.Path,
        help="capacity JSON {life_support_patients, vents_free, vents_total, "
        "crrt_total, set_at, set_by_role}; "
        "when it exists the yardstick is ON TRACK / TIGHT / SHORT against it",
    )
    ap.add_argument(
        "--demo-clock-hours",
        type=float,
        default=0,
        help="stage ward replay: the cut offset (hours) that was given to "
        "icutwin-winnow; recorded, and the default cut_time is the last 07:00 "
        "plus these hours",
    )
    ap.add_argument(
        "--cut-time",
        type=cut_arg,
        help="ISO time WITH a UTC offset of the cut, taken as given (default: the "
        "07:00 nearest to now, plus --demo-clock-hours from the last 07:00 when set)",
    )
    ap.add_argument(
        "--tz",
        default=DEFAULT_TZ,
        help="site time zone for the default 07:00 cut (default America/Chicago: "
        "the event and t7-twin's TZ); pass it explicitly when the site differs",
    )
    ap.add_argument(
        "--stage-csv",
        type=pathlib.Path,
        help="stage_ward.csv (room, hospitalization_id): fills check_first; "
        "stage ward only, leave out for real MIMIC",
    )
    ap.add_argument(
        "--real-ward",
        action="store_true",
        help="the room map is a real MIMIC-IV ward (stay ids outside the open demo): "
        "allowed only with this flag; output is then labelled local only",
    )
    ap.add_argument(
        "--clif-now",
        type=pathlib.Path,
        help="CLIF folder (clif_adt, clif_respiratory_support, clif_medication_"
        "admin_continuous, clif_crrt_therapy): IMV, vasopressor and CRRT running at "
        "the cut are read from it instead of the tokenized at-cut flags "
        "(on_now_source 'clif'); same ward guard as --real-ward",
    )
    ap.add_argument(
        "--unit-name",
        default=UNIT_NAME,
        help=f"the unit's name: forecast.json unit_name (default {UNIT_NAME})",
    )
    ap.add_argument(
        "--score",
        choices=["rep", "mc"],
        default="rep",
        help="rep: probe probabilities (the board's method); mc: sampled futures",
    )
    add_staffing_args(ap)
    a = ap.parse_args()
    if a.score == "rep":
        return main_rep(a)

    files = sorted(a.tokenized_output.glob("scores-generative-*.parquet"))
    if not files:
        raise SystemExit(f"no scores-generative-*.parquet under {a.tokenized_output}")
    newest = max(files, key=lambda f: f.stat().st_mtime)
    m = re.search(r"^(.*)-shard\d+of(\d+)$", newest.stem)
    if m:
        parts = sorted(a.tokenized_output.glob(f"{m[1]}-shard*of{m[2]}.parquet"))
        if len(parts) != int(m[2]):
            raise SystemExit(f"{len(parts)} of {m[2]} shards for {m[1]}")
        df = pl.concat([pl.read_parquet(f) for f in parts], how="diagonal")
    else:
        df = pl.read_parquet(newest)
    rng = np.random.default_rng(a.seed)
    unit = df.sample(n=min(a.beds, df.height), seed=a.seed)

    hours = sorted(
        {int(h) for c in unit.columns for h in re.findall(r"_mc(\d+)h_score$", c)}
    )
    horizons = {f"{h}h": f"_mc{h}h_score" for h in hours} | {"stay": "_mc_score"}
    probs = {key: unit_probs(unit, suffix) for key, suffix in horizons.items()}
    by_horizon = {
        key: {"label": LABELS.get(key, key), "resources": strain(p, rng)}
        for key, p in probs.items()
    }
    default = "24h" if "24h" in by_horizon else "stay"

    # per-day new events: P(first event on day d) = P(by 24d h) - P(by 24(d-1) h)
    per_day, prev = {}, None
    for d, key in enumerate(k for k in ("24h", "48h", "72h") if k in probs):
        day = {
            name: np.clip(p - (prev[name] if prev else 0.0), 0.0, 1.0)
            for name, p in probs[key].items()
        }
        per_day[f"Day {d + 1}"] = strain(day, rng)
        prev = probs[key]

    forecast = {
        "made_at": now_iso(),
        "beds": unit.height,
        "range": "80% (p10-p90)",
        "default_horizon": default,
        "horizon": by_horizon[default]["label"],
        "model": (m[1] if m else newest.stem).removeprefix("scores-generative-"),
        "shards": int(m[2]) if m else 1,
        "resources": by_horizon[default]["resources"],
        "horizons": by_horizon,
        "per_day": per_day,
        "already_started": already_started(unit),
    }
    write_json(a.out, forecast)
    print(
        json.dumps(
            {k: forecast[k] for k in ("made_at", "beds", "horizon", "model", "shards")}
        )
    )
    print({k: v["p50"] for k, v in forecast["resources"].items()})


if __name__ == "__main__":
    main()

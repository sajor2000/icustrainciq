"""clif_now: what is running at the cut from raw CLIF, and --clif-now on rooms.py."""

import datetime as dt
import json

import polars as pl
import pytest
import test_lookahead as tl

from app import aggregate, clif_now

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
CUT = T0 + dt.timedelta(hours=24)


def h(x: float) -> dt.datetime:
    """x hours before the cut"""
    return CUT - dt.timedelta(hours=x)


def _clif(tmp_path, resp=(), meds=(), crrt=(), ids=("s1",)):
    d = tmp_path / "clif"
    d.mkdir(exist_ok=True)
    ts = pl.Datetime("us", "UTC")
    pl.DataFrame(
        [(i, t, c) for i, t, c in resp],
        schema={
            "hospitalization_id": pl.String,
            "recorded_dttm": ts,
            "device_category": pl.String,
        },
        orient="row",
    ).write_parquet(d / "clif_respiratory_support.parquet")
    pl.DataFrame(
        [(i, t, m, a, x) for i, t, m, a, x in meds],
        schema={
            "hospitalization_id": pl.String,
            "admin_dttm": ts,
            "med_category": pl.String,
            "mar_action_category": pl.String,
            "med_dose": pl.Float32,
        },
        orient="row",
    ).write_parquet(d / "clif_medication_admin_continuous.parquet")
    pl.DataFrame(
        [(i, t, m, r) for i, t, m, r in crrt],
        schema={
            "hospitalization_id": pl.String,
            "recorded_dttm": ts,
            "crrt_mode_category": pl.String,
            "blood_flow_rate": pl.Float32,
        },
        orient="row",
    ).write_parquet(d / "clif_crrt_therapy.parquet")
    pl.DataFrame({"hospitalization_id": list(ids)}).write_parquet(
        d / "clif_hospitalization.parquet"
    )
    pl.DataFrame(
        {
            "hospitalization_id": list(ids),
            "in_dttm": [T0] * len(ids),
            "location_category": ["icu"] * len(ids),
        },
        schema={
            "hospitalization_id": pl.String,
            "in_dttm": ts,
            "location_category": pl.String,
        },
    ).write_parquet(d / "clif_adt.parquet")
    return d


def run(tmp_path, cut=CUT, **tables):
    return clif_now.running_at_cut(_clif(tmp_path, **tables), {"s1": cut})["s1"]


def test_imv_then_extubated_before_cut_is_false(tmp_path):
    r = run(tmp_path, resp=[("s1", h(10), "IMV"), ("s1", h(3), "Nasal Cannula")])
    assert r["imv"] is False


def test_imv_last_row_and_null_device_ignored(tmp_path):
    r = run(
        tmp_path,
        resp=[("s1", h(5), "IMV"), ("s1", h(1), None), ("s1", h(-1), "Room Air")],
    )
    assert r["imv"] is True  # the null row and the row after the cut do not count


def test_imv_unknown_without_rows_in_24h(tmp_path):
    assert run(tmp_path, resp=[("s1", h(30), "IMV")])["imv"] is None
    assert run(tmp_path, cut=T0 - dt.timedelta(hours=1))["imv"] is None


def test_pressor_start_then_stop_is_false(tmp_path):
    m = [
        ("s1", h(8), "norepinephrine", "start", 0.1),
        ("s1", h(2), "norepinephrine", "stop", 0.0),
    ]
    assert run(tmp_path, meds=m)["vasopressor"] is False


def test_pressor_start_dose_change_running(tmp_path):
    m = [
        ("s1", h(8), "norepinephrine", "start", 0.1),
        ("s1", h(2), "norepinephrine", "dose_change", 0.2),
    ]
    assert run(tmp_path, meds=m)["vasopressor"] is True


def test_pressor_null_dose_carries_and_other_pressor_stop_does_not_end_it(tmp_path):
    m = [
        ("s1", h(8), "vasopressin", "start", 0.03),
        ("s1", h(2), "vasopressin", "going", None),  # null dose: carries 0.03
        ("s1", h(4), "norepinephrine", "start", 0.1),
        ("s1", h(3), "norepinephrine", "stop", None),
    ]
    assert run(tmp_path, meds=m)["vasopressor"] is True
    zero = [("s1", h(8), "vasopressin", "dose_change", 0.0)]
    assert run(tmp_path, meds=zero)["vasopressor"] is False  # dose 0 is not running


def test_pressor_none_and_non_pressor_rows(tmp_path):
    assert run(tmp_path)["vasopressor"] is False
    m = [
        ("s1", h(2), "propofol", "start", 20.0),
        ("s1", h(40), "vasopressin", "start", 1),
    ]
    assert (
        run(tmp_path, meds=m)["vasopressor"] is False
    )  # not a pressor / older than 24 h


def test_crrt_window_is_six_hours(tmp_path):
    assert run(tmp_path, crrt=[("s1", h(2), "cvvhdf", 200.0)])["crrt"] is True
    assert run(tmp_path, crrt=[("s1", h(10), "cvvhdf", 200.0)])["crrt"] is False
    assert run(tmp_path, crrt=[("s1", h(2), "cvvh", None)])["crrt"] is True
    assert run(tmp_path, crrt=[("s1", h(2), None, None)])["crrt"] is False
    assert run(tmp_path, crrt=[("s1", h(2), "cvvhdf", 0.0)])["crrt"] is False


def test_cut_before_any_rows(tmp_path):
    t = dict(
        resp=[("s1", h(1), "IMV")],
        meds=[("s1", h(1), "vasopressin", "start", 1.0)],
        crrt=[("s1", h(1), "cvvh", 100.0)],
    )
    r = run(tmp_path, cut=h(2), **t)
    assert r == {"imv": None, "vasopressor": False, "crrt": False}


def test_naive_cut_is_utc_and_stay_cuts_follow_icu_arrival(tmp_path):
    d = _clif(tmp_path, resp=[("s1", h(1), "IMV")])
    assert clif_now.running_at_cut(d, {"s1": CUT.replace(tzinfo=None)})["s1"]["imv"]
    assert clif_now.stay_cuts(d, ["s1"], 6) == {"s1": CUT + dt.timedelta(hours=6)}
    assert clif_now.running_for_stays(d, ["s1"])["s1"]["imv"] is True
    with pytest.raises(SystemExit):
        clif_now.stay_cuts(d, ["nope"])


def test_rooms_with_clif_now_changes_on_now(tmp_path, monkeypatch, capsys):
    ids = [f"pat-{i}" for i in range(4)]
    demo = tmp_path / "demo_hosp.parquet"
    pl.DataFrame({"hospitalization_id": ids}).write_parquet(demo)
    monkeypatch.setattr(aggregate, "DEMO_HOSP", demo)
    root = tl._stage(tmp_path, ids)  # tokens: pat-0 on a vasopressor, nobody on IMV
    clif = _clif(
        tmp_path,
        ids=ids,
        resp=[("pat-1", h(2), "IMV")],
        meds=[
            ("pat-0", h(9), "norepinephrine", "start", 0.1),
            ("pat-0", h(4), "norepinephrine", "stop", 0.0),
        ],
        crrt=[("pat-2", h(1), "cvvhdf", 150.0)],
    )
    tok = tl._run(monkeypatch, tmp_path, root)
    assert tok["on_now_source"] == "tokens"
    assert tok["rooms"][0]["on_now"]["vasopressor"] is True
    doc = tl._run(monkeypatch, tmp_path, root, "--clif-now", str(clif))
    assert doc["on_now_source"] == "clif"
    r = {x["room"]: x for x in doc["rooms"]}
    assert r[1]["on_now"]["vasopressor"] is False  # stopped before the cut
    assert r[1]["stopped_before_cut"]["vasopressor"] is True
    assert r[1]["p"]["vasopressor"] is not None  # forecastable again
    assert r[2]["on_now"]["imv"] is True and r[2]["p"]["imv"] is None
    assert r[3]["on_now"]["crrt"] is True
    assert "pat-" not in capsys.readouterr().out + json.dumps(doc)
    # a room run must not mix sources
    monkeypatch.setattr(
        "sys.argv",
        [
            "rooms",
            str(root),
            "--model",
            str(tmp_path / tl.MODEL),
            "--stay-ids",
            str(tmp_path / "stage_ward.csv"),
            "--out",
            str(tmp_path / "rooms.json"),
            "--no-apply",
            "--room",
            "2",
            "--cut-time",
            "2026-11-14T07:00:00-05:00",
        ],
    )
    with pytest.raises(SystemExit):
        tl.rooms.main()


def test_forecast_counts_follow_clif(tmp_path):
    ids = [f"s{i}" for i in range(4)]
    clif = _clif(tmp_path, ids=ids, resp=[("s0", h(2), "IMV")])
    df = tl.scores(4, ids=ids)
    fc = aggregate.build_forecast(df, "m", beds=4, clif_now=clif)
    assert fc["on_now_source"] == "clif"
    assert fc["life_support"]["now_by"]["imv"] == 1
    assert aggregate.build_forecast(df, "m", beds=4)["on_now_source"] == "tokens"


def test_vitals_before_cut_hourly_median_relative_hours(tmp_path):
    d = _clif(tmp_path, ids=("s1", "s2"))
    rows = [
        ("s1", h(0.5), "heart_rate", 100.0),
        ("s1", h(0.25), "heart_rate", 110.0),  # same hour: the median, 105
        ("s1", h(1.5), "heart_rate", 90.0),  # hour 2
        ("s1", h(11.5), "spo2", 95.0),  # hour 12
        (
            "s1",
            h(12),
            "spo2",
            80.0,
        ),  # 12 h or older: left out (the window is open there)
        ("s1", h(-1), "map", 70.0),  # after the cut: left out
        ("s1", h(3), "temp_c", 37.0),  # not one of the four
        ("s1", h(4), "map", None),  # no value
    ]
    pl.DataFrame(
        rows,
        schema={
            "hospitalization_id": pl.String,
            "recorded_dttm": pl.Datetime("us", "UTC"),
            "vital_category": pl.String,
            "vital_value": pl.Float64,
        },
        orient="row",
    ).write_parquet(d / "clif_vitals.parquet")
    got = clif_now.vitals_before_cut(d, {"s1": CUT, "s2": CUT})
    assert got == {
        "s1": {
            "heart_rate": [{"h": 1, "v": 105.0}, {"h": 2, "v": 90.0}],
            "spo2": [{"h": 12, "v": 95.0}],
        }
    }  # s2 has no reading: not in the result
    assert clif_now.vitals_for_stays(d, ["s1"]) == {"s1": got["s1"]}


def test_vitals_before_cut_without_a_vitals_table(tmp_path):
    assert clif_now.vitals_before_cut(_clif(tmp_path), {"s1": CUT}) == {}

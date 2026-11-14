"""Bed-board app: aggregate counts and the board's pages (synthetic data, no GPU)."""

import json

import numpy as np
import polars as pl

from app import aggregate


def test_unit_counts_bounds_and_order():
    rng = np.random.default_rng(0)
    c = aggregate.unit_counts(np.array([0.0, 1.0, 0.5, np.nan]), rng)
    assert 1 <= c["p10"] <= c["p50"] <= c["p90"] <= 2
    assert c["expected"] == 1.5


def test_aggregate_writes_counts_only(tmp_path, monkeypatch):
    n = 40
    df = pl.DataFrame(
        {
            "hospitalization_id": [f"h{i}" for i in range(n)],
            "RESP//device_category//imv_mc_score": np.linspace(0, 1, n),
            "HOSP//discharge_category//expired_mc_score": np.full(n, 0.1),
            "MED_CON//norepinephrine//q1_mc_score": np.full(n, 0.2),
            "MED_CON//vasopressin//q2_mc_score": np.full(n, 0.6),
            "ADT//TRANSFER_IN//icu_mc_score": np.full(n, 0.4),
            "ADT//TRANSFER_IN//ward_mc_score": np.full(n, 0.2),
        }
    )
    df.write_parquet(tmp_path / "scores-generative-mdl-icutwin.parquet")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        ["aggregate", str(tmp_path), str(out), "--beds", "25", "--score", "mc"],
    )
    aggregate.main()
    fc = json.loads(out.read_text())
    assert fc["beds"] == 25 and set(fc["resources"]) == {
        "ventilator",
        "death",
        "vasopressor",
        "icu_admission",
        "icu_departure",
        "icu_beds_net",
    }
    vaso = fc["resources"]["vasopressor"]
    assert vaso["team"] == "pharmacy" and vaso["expected"] == 15.0  # max per stay
    net = fc["resources"]["icu_beds_net"]
    assert net["team"] == "bed manager" and net["expected"] == 2.5  # 10 in - 7.5 out
    assert net["p10"] <= net["p50"] <= net["p90"]
    assert "h1" not in out.read_text()  # no stay ids leave the script


def test_aggregate_joins_burst_shards(tmp_path, monkeypatch):
    for i in range(2):
        pl.DataFrame(
            {
                "hospitalization_id": [f"h{i}-{k}" for k in range(20)],
                "RESP//device_category//imv_mc_score": np.full(20, 0.5),
            }
        ).write_parquet(tmp_path / f"scores-generative-mdl-icutwin-shard{i}of2.parquet")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        ["aggregate", str(tmp_path), str(out), "--beds", "40", "--score", "mc"],
    )
    aggregate.main()
    fc = json.loads(out.read_text())
    assert fc["beds"] == 40 and fc["shards"] == 2 and fc["model"] == "mdl-icutwin"
    assert fc["resources"]["ventilator"]["expected"] == 20.0


def test_parse_shard():
    pytest = __import__("pytest")
    gen = pytest.importorskip("icutwin.scoring.generative")
    assert gen.parse_shard(None) is None and gen.parse_shard("1/2") == (1, 2)
    with pytest.raises(ValueError):
        gen.parse_shard("2/2")


def test_already_on_vasopressor_is_not_a_new_start(tmp_path, monkeypatch):
    n = 10
    nan_first = np.where(
        np.arange(n) == 0, np.nan, 0.5
    )  # stay 0: norepi B2 before the cut
    pl.DataFrame(
        {
            "hospitalization_id": [f"h{i}" for i in range(n)],
            "MED_CON//norepinephrine//B2_mc_score": nan_first,
            "MED_CON//norepinephrine//B3_mc_score": np.full(n, 0.9),
        }
    ).write_parquet(tmp_path / "scores-generative-mdl-icutwin.parquet")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        ["aggregate", str(tmp_path), str(out), "--beds", "10", "--score", "mc"],
    )
    aggregate.main()
    vaso = json.loads(out.read_text())["resources"]["vasopressor"]
    assert vaso["expected"] == 8.1  # 9 stays x 0.9; stay 0 is already on it


def test_forecast_scoring_override_merges():
    from pathlib import Path

    from icutwin.common import merge_config

    cfg = merge_config(
        "scoring.yaml", Path(__file__).parents[1] / "examples/forecast_scoring.yaml"
    )
    assert list(cfg.generation.methods) == ["M1"]
    assert "ADT//TRANSFER_IN//ward" in cfg.score.repeat_ok
    assert "RESP//device_category//imv" in cfg.score.target_tokens  # base kept


def test_horizons_default_to_24h_and_split_per_day(tmp_path, monkeypatch):
    n = 20
    pl.DataFrame(
        {
            "hospitalization_id": [f"h{i}" for i in range(n)],
            "RESP//device_category//imv_mc_score": np.full(n, 0.6),
            "RESP//device_category//imv_mc24h_score": np.full(n, 0.2),
            "RESP//device_category//imv_mc48h_score": np.full(n, 0.35),
            "RESP//device_category//imv_mc72h_score": np.full(n, 0.45),
        }
    ).write_parquet(tmp_path / "scores-generative-mdl-icutwin.parquet")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        ["aggregate", str(tmp_path), str(out), "--beds", "20", "--score", "mc"],
    )
    aggregate.main()
    fc = json.loads(out.read_text())
    assert fc["default_horizon"] == "24h" and fc["horizon"] == "Next 24 h (Day 1)"
    assert fc["resources"]["ventilator"]["expected"] == 4.0  # 20 x 0.2
    assert set(fc["horizons"]) == {"24h", "48h", "72h", "stay"}
    assert fc["horizons"]["stay"]["resources"]["ventilator"]["expected"] == 12.0
    days = fc["per_day"]
    assert [days[d]["ventilator"]["expected"] for d in days] == [4.0, 3.0, 2.0]


def test_within_clocks_counts_four_hour_clock_tokens():
    gen = __import__("pytest").importorskip("icutwin.scoring.generative")
    clocks = {900, 901}
    # event after 2 clocks: within 12 h (3 clocks) but not within 4 h (1 clock)
    out = [5, 900, 6, 901, 42, 900]
    assert gen.within_clocks(out, 42, clocks, 3)
    assert not gen.within_clocks(out, 42, clocks, 1)
    assert not gen.within_clocks([5, 900, 900], 42, clocks, 6)


def test_rep_mode_six_tasks_and_past_flags(tmp_path, monkeypatch):
    n = 10
    pl.DataFrame(
        {
            "hospitalization_id": [f"h{i}" for i in range(n)],
            "RESP//device_category//imv_rep_score": np.full(n, 0.3),
            "RESP//device_category//imv_past": [True] + [False] * (n - 1),
            "LABEL//pressor_init_rep_score": np.full(n, 0.2),
            "LABEL//crrt_init_rep_score": np.full(n, 0.1),
            "HOSP//discharge_category//expired_rep_score": np.full(n, 0.05),
            "LABEL//hyperk_init_rep_score": np.full(n, 0.1),  # not one of the five
        }
    ).write_parquet(tmp_path / "scores-rep-based-mdl-icutwin.parquet")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv", ["aggregate", str(tmp_path), str(out), "--beds", "10"]
    )
    aggregate.main()
    fc = json.loads(out.read_text())
    r = fc["resources"]
    assert set(r) == {"ventilator", "vasopressor", "crrt", "death"}
    assert "other_tasks" not in fc  # five predictions only (D8)
    assert r["ventilator"]["expected"] == 2.7  # 9 x 0.3; stay 0 already ventilated
    assert r["vasopressor"]["team"] == "pharmacy" and fc["default_horizon"] == "24h"
    assert (
        fc["already_started"]["ventilator"] == 1
        and "hospitalization_id" not in out.read_text()
    )


def test_strain_baseline_from_training_labels(tmp_path, monkeypatch):
    # training labels: ventilation 0.2 new per stay (one stay already on: not new),
    # vasopressor 0.1; everything else never happens
    t = 100
    imv_f = np.zeros(t, bool)
    imv_f[:20] = True
    imv_p = np.zeros(t, bool)
    imv_p[0] = True  # on before the cut: excluded from the new-event rate
    vp_f = np.zeros(t, bool)
    vp_f[50:60] = True
    z = np.zeros(t, bool)
    tr = tmp_path / "train"
    tr.mkdir()
    pl.DataFrame(
        {
            "hospitalization_id": [f"t{i}" for i in range(t)],
            "RESP//device_category//imv_past": imv_p,
            "RESP//device_category//imv_future": imv_f,
            "LABEL//pressor_init_past": z,
            "LABEL//pressor_init_future": vp_f,
        }
    ).write_parquet(tr / "train_for_inference.parquet")
    rates = aggregate.typical_rates(pl.read_parquet(tr / "train_for_inference.parquet"))
    assert rates == {"ventilator": 0.19, "vasopressor": 0.1}

    n = 25  # the stage ward: forecast at twice the usual vent and pressor rate
    sw = tmp_path / "stage"
    sw.mkdir()
    pl.DataFrame(
        {
            "hospitalization_id": [f"s{i}" for i in range(n)],
            "RESP//device_category//imv_rep_score": np.full(n, 0.38),
            "LABEL//pressor_init_rep_score": np.full(n, 0.2),
        }
    ).write_parquet(sw / "scores-rep-based-mdl-icutwin.parquet")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        ["aggregate", str(sw), str(out), "--beds", "25", "--baseline", str(tr)],
    )
    aggregate.main()
    s = json.loads(out.read_text())["strain"]
    assert s["beds"] == 25 and s["typical_day"] == round(25 * 0.29, 2)  # 7.25
    assert s["expected"] == 14.5 and s["per_task"]["ventilator"]["ratio"] == 2.0
    assert s["ratio"]["p10"] <= s["ratio"]["p50"] <= s["ratio"]["p90"]
    assert s["band"] == "VERY BUSY" and s["above_usual"][0] in s["tasks"]
    assert "t1" not in out.read_text() and "s1" not in out.read_text()


def test_strain_bands_and_missing_baseline(tmp_path, monkeypatch):
    assert [aggregate.band_of(x) for x in (0.5, 0.8, 1.19, 1.2, 1.59, 1.6)] == [
        "QUIET",
        "USUAL",
        "USUAL",
        "BUSY",
        "BUSY",
        "VERY BUSY",
    ]
    pl.DataFrame(
        {
            "hospitalization_id": ["a", "b"],
            "RESP//device_category//imv_rep_score": [0.1, 0.2],
        }
    ).write_parquet(tmp_path / "scores-rep-based-mdl-icutwin.parquet")
    out = tmp_path / "f.json"
    monkeypatch.setattr("sys.argv", ["aggregate", str(tmp_path), str(out)])
    aggregate.main()  # no train_for_inference.parquet: strain is left out, not guessed
    assert "strain" not in json.loads(out.read_text())


def test_made_at_carries_an_offset_and_the_file_is_replaced_whole(tmp_path):
    import datetime as dt

    assert dt.datetime.fromisoformat(aggregate.now_iso()).utcoffset() is not None
    out = tmp_path / "forecast.json"
    aggregate.write_json(out, {"a": 1})
    aggregate.write_json(out, {"a": 2})
    assert json.loads(out.read_text()) == {"a": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["forecast.json"]  # no .tmp left

"""ICU Horizon forecast: life support, yardstick, rooms, demo clock (synthetic data)."""

import datetime as dt
import itertools
import json
import pathlib

import numpy as np
import polars as pl
import pytest
import yaml
from omegaconf import OmegaConf

from app import aggregate, rooms
from icutwin.scoring import rep_based
from icutwin.scoring.winnower import Winnower

IMV = "RESP//device_category//imv"
VASO = "LABEL//pressor_init"
CRRT = "LABEL//crrt_init"
WARD = "ADT//TRANSFER_IN//ward"
STEP = "ADT//TRANSFER_IN//stepdown"
DEATH = "HOSP//discharge_category//expired"


@pytest.fixture(autouse=True)
def demo_ward(tmp_path_factory, monkeypatch):
    """a stand-in for the git-tracked clif_demo/clif_hospitalization.parquet that
    holds every synthetic stay id these tests use (the real one is checked below)"""
    ids = (
        [f"secret-{i}" for i in range(40)]
        + [f"pat-{i}" for i in range(10)]
        + [f"held_out{i}" for i in range(10)]
        + ["a", "b"]
    )
    f = tmp_path_factory.mktemp("demo") / "clif_hospitalization.parquet"
    pl.DataFrame({"hospitalization_id": ids}).write_parquet(f)
    monkeypatch.setattr(aggregate, "DEMO_HOSP", f)


def scores(n=6, p=None, past=None, ids=None):
    """a probe-score table; p / past map a token to per-stay values"""
    p, past = p or {}, past or {}
    cols = {"hospitalization_id": ids or [f"s{i}" for i in range(n)]}
    for t in (IMV, VASO, CRRT, WARD, STEP, DEATH):
        cols[f"{t}_rep_score"] = np.asarray(p.get(t, np.full(n, 0.1)), float)
        cols[f"{t}_past"] = np.asarray(past.get(t, np.zeros(n, bool)), bool)
    return pl.DataFrame(cols)


def test_any_life_support_math_and_already_on_drops_out():
    df = scores(
        3,
        p={IMV: [0.5, 0.5, 0.2], VASO: [0.5, 0.2, 0.0], CRRT: [0.0, 0.1, 0.0]},
        past={IMV: [False, True, False]},
    )
    tab = aggregate.patient_table(df)
    assert np.isnan(tab["p"]["ventilator"][1])  # already on: p is null
    assert tab["on"]["imv"].tolist() == [False, True, False]
    got = aggregate.p_any_life_support(tab["p"])
    # 1 - (1-pi)(1-pv)(1-pc); the on-already IMV of stay 1 is left out
    np.testing.assert_allclose(got, [0.75, 1 - 0.8 * 0.9, 0.2])


def test_levels_and_out_tag_thresholds():
    assert [aggregate.level_of(x) for x in (0.0, 0.19, 0.2, 0.39, 0.4, 0.9)] == [
        "low",
        "low",
        "medium",
        "medium",
        "high",
        "high",
    ]
    assert (
        aggregate.level_of(0.3, {"medium": 0.1, "high": 0.3}) == "high"
    )  # configurable
    assert aggregate.OUT_TAG == 0.6


def test_poisson_binomial_matches_enumeration():
    p = np.array([0.1, 0.7, 0.35, 0.0, 0.9])
    pmf = aggregate.pb_pmf(p)
    brute = np.zeros(p.size + 1)
    for bits in itertools.product([0, 1], repeat=p.size):
        w = np.prod([q if b else 1 - q for q, b in zip(p, bits)])
        brute[sum(bits)] += w
    np.testing.assert_allclose(pmf, brute, atol=1e-12)
    cdf = np.cumsum(brute)
    q = aggregate.unit_counts(p)
    assert q["p10"] == int(np.argmax(cdf >= 0.10 - 1e-12))
    assert q["p50"] == int(np.argmax(cdf >= 0.50 - 1e-12))
    assert q["p90"] == int(np.argmax(cdf >= 0.90 - 1e-12))
    assert q["expected"] == round(float(p.sum()), 2)


def test_expected_new_patients_skips_patients_already_on_life_support():
    df = scores(
        4,
        p={IMV: np.full(4, 0.5), VASO: np.zeros(4), CRRT: np.zeros(4)},
        past={IMV: [True, False, False, False]},
    )
    ls = aggregate.life_support_block(aggregate.patient_table(df))
    assert ls["now_patients"] == 1 and ls["now_by"]["imv"] == 1
    assert ls["now_by"]["ecmo"] is None  # no ecmo token: not available, not invented
    assert ls["expected_new_patients"]["expected"] == 1.5  # 3 patients x 0.5
    assert ls["expected_by"]["imv"]["expected"] == 1.5
    assert set(ls["expected_by"]) == {"imv", "vasopressor", "crrt"}


def _ls(now, p50, p10=None, p90=None):
    return {
        "now_patients": now,
        "expected_new_patients": {
            "p10": p10 if p10 is not None else p50,
            "p50": p50,
            "p90": p90 if p90 is not None else p50,
        },
    }


def test_yardstick_capacity_words():
    cap = {
        "life_support_patients": 8,
        "vents_free": 2,
        "set_at": "t",
        "set_by_role": "x",
    }
    on = aggregate.yardstick(_ls(2, 3, 2, 6), 25, cap, None)  # load p90 8 <= 8
    assert (on["kind"], on["words"], on["level"]) == ("capacity", "ON TRACK", "ok")
    tight = aggregate.yardstick(_ls(2, 3, 2, 7), 25, cap, None)  # p90 9 > 8 >= p50 5
    assert (tight["words"], tight["level"]) == ("TIGHT", "amber")
    short = aggregate.yardstick(_ls(5, 4, 3, 6), 25, cap, None)  # p50 9 > 8
    assert (short["words"], short["level"]) == ("SHORT", "red")
    assert short["capacity"]["vents_free"] == 2 and short["typical"] is None


def test_yardstick_typical_words_and_no_guess():
    # typical = 25 beds x 0.4 = 10 life-support patients
    words = lambda load: aggregate.yardstick(_ls(0, load), 25, None, 0.4)["words"]  # noqa: E731
    assert [words(x) for x in (9, 10, 11, 13, 14)] == [
        "USUAL",
        "USUAL",
        "BUSY",
        "BUSY",
        "VERY BUSY",
    ]
    y = aggregate.yardstick(_ls(0, 14), 25, None, 0.4)
    assert y["kind"] == "typical" and y["level"] == "red" and y["capacity"] is None
    assert y["typical"]["life_support_patients"] == 10.0
    assert aggregate.yardstick(_ls(0, 3), 25, None, None) is None  # no baseline


def test_typical_rate_from_training_labels():
    cols = {}
    for t, past, fut in (
        (IMV, [1, 0, 0, 0], [0, 1, 0, 0]),
        (VASO, [0, 0, 0, 0], [0, 0, 0, 0]),
        (CRRT, [0, 0, 0, 0], [0, 0, 0, 0]),
    ):
        cols[f"{t}_past"], cols[f"{t}_future"] = (
            np.array(past, bool),
            np.array(fut, bool),
        )
    rate = aggregate.typical_life_support_rate(pl.DataFrame(cols))
    assert rate == 0.5  # stay 0 on at the cut, stay 1 starting, 2 and 3 neither
    assert aggregate.typical_life_support_rate(pl.DataFrame({"x": [1]})) is None


def test_capacity_file_roundtrip(tmp_path):
    f = tmp_path / "cap.json"
    assert aggregate.read_capacity(f) is None  # absent
    f.write_text(json.dumps({"life_support_patients": 9, "vents_free": 3}))
    assert aggregate.read_capacity(f)["life_support_patients"] == 9
    f.write_text("not json")
    assert aggregate.read_capacity(f) is None  # unusable: typical applies


def _write_scores(root, df, model="mdl-test", home=None):
    out = root / f"scores-rep-based-{model}.parquet"
    df.write_parquet(out)
    rep_based.write_scores_meta(out, home or root.parent / model)  # provenance


def test_forecast_contract_keys_and_no_ids(tmp_path, monkeypatch, capsys):
    n = 30
    rng = np.random.default_rng(1)
    _write_scores(
        tmp_path,
        scores(
            n,
            p={t: rng.uniform(0, 0.6, n) for t in (IMV, VASO, CRRT, WARD, STEP, DEATH)},
            past={IMV: rng.random(n) < 0.2},
            ids=[f"secret-{i}" for i in range(n)],
        ),
    )
    train = {}
    for t in (IMV, VASO, CRRT):
        train[f"{t}_past"] = rng.random(100) < 0.2
        train[f"{t}_future"] = rng.random(100) < 0.2
    pl.DataFrame(train).write_parquet(tmp_path / "train_for_inference.parquet")
    pl.DataFrame(
        {"room": [1, 2], "hospitalization_id": ["secret-0", "secret-1"]}
    ).write_csv(tmp_path / "stage.csv")
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "aggregate",
            str(tmp_path),
            str(out),
            "--beds",
            "25",
            "--demo-clock-hours",
            "6",
            "--cut-time",
            "2026-11-14T07:00:00-05:00",
            "--stage-csv",
            str(tmp_path / "stage.csv"),
        ],
    )
    aggregate.main()
    assert "secret" not in capsys.readouterr().out + out.read_text()
    fc = json.loads(out.read_text())
    for k in (
        "made_at cut_time window scope demo_clock_hours beds range resources "
        "life_support yardstick check_first levels out_tag"
    ).split():
        assert k in fc
    assert fc["scope"] == "unit" and fc["demo_clock_hours"] == 6
    assert fc["cut_time"] == "2026-11-14T07:00:00-05:00"
    assert fc["window"] == {
        "start": "2026-11-14T07:00:00-05:00",
        "end": "2026-11-15T07:00:00-05:00",
    }
    assert set(fc["resources"]) == {
        "icu_departure",
        "ventilator",
        "vasopressor",
        "crrt",
        "death",
    }
    ls = fc["life_support"]
    assert set(ls["now_by"]) == {"imv", "vasopressor", "crrt", "ecmo"}
    assert set(ls["expected_new_patients"]) >= {"p10", "p50", "p90"}
    assert set(ls["expected_by"]) == {"imv", "vasopressor", "crrt"}
    assert fc["yardstick"]["kind"] == "typical" and fc["yardstick"]["capacity"] is None
    assert fc["levels"] == {"medium": 0.2, "high": 0.4} and fc["out_tag"] == 0.6
    assert len(fc["check_first"]) <= 3 and all(
        set(c) >= {"room", "any_life_support"} for c in fc["check_first"]
    )
    assert fc["made_at"].endswith("+00:00")


def test_yardstick_uses_capacity_file_when_present(tmp_path, monkeypatch):
    _write_scores(tmp_path, scores(25))
    cap = tmp_path / "capacity.json"
    cap.write_text(
        json.dumps(
            {
                "life_support_patients": 1,
                "vents_free": 0,
                "set_at": "x",
                "set_by_role": "nurse",
            }
        )
    )
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv", ["aggregate", str(tmp_path), str(out), "--capacity", str(cap)]
    )
    aggregate.main()
    y = json.loads(out.read_text())["yardstick"]
    assert y["kind"] == "capacity" and y["words"] == "SHORT" and y["level"] == "red"
    assert y["capacity"]["set_by_role"] == "nurse"


# ---- rooms.json ----
MODEL = "mdl-test"
LOOKUP = {
    "BOS": 1,
    "ADT//TRANSFER_IN//icu": 2,
    IMV: 3,
    "MED_CON//norepinephrine//B3": 4,
    "VITAL//map//B2": 5,
    "TIME//5m-15m": 6,
}


def _model_dir(tmp_path, weights=b"w1"):
    home = tmp_path / MODEL
    home.mkdir(exist_ok=True)
    (home / "model.safetensors").write_bytes(weights)
    (home / "config.json").write_text("{}")
    return home


def _stage(tmp_path, ids, ended=()):
    """a stage-ward folder: vocab, winnowed labels with tokens_past, probe scores"""
    root = tmp_path / "stage"
    root.mkdir()
    _model_dir(tmp_path)
    (root / "vocab.yaml").write_text(yaml.safe_dump({"lookup": LOOKUP}))
    n = len(ids)
    pl.DataFrame(
        {
            "hospitalization_id": ids,
            "tokens_past": [[1, 2, 3, 4, 5, 6]] * n,
            "s_elapsed_past": [[0, 100, 83000, 83100, 83200, 83300]] * n,
            "cut_s": [86500.0] * n,
        }
    ).write_parquet(root / "held_out_for_inference.parquet")
    _write_scores(
        root,
        scores(
            n,
            p={
                DEATH: np.full(n, 0.05),
                WARD: np.linspace(0.1, 0.9, n),
                IMV: np.full(n, 0.5),
            },
            past={VASO: np.arange(n) == 0},
            ids=ids,
        ),
        MODEL,
    )
    pl.DataFrame({"room": range(1, n + 1), "hospitalization_id": ids}).write_csv(
        tmp_path / "stage_ward.csv"
    )
    return root


def _run(monkeypatch, tmp_path, root, *extra):
    monkeypatch.setattr(
        "sys.argv",
        [
            "rooms",
            str(root),
            "--model",
            str(tmp_path / MODEL),
            "--stay-ids",
            str(tmp_path / "stage_ward.csv"),
            "--out",
            str(tmp_path / "rooms.json"),
            "--no-apply",
            "--cut-time",
            "2026-11-14T07:00:00-05:00",
            *extra,
        ],
    )
    rooms.main()
    return json.loads((tmp_path / "rooms.json").read_text())


def test_rooms_json_contract_and_readable_past(tmp_path, monkeypatch, capsys):
    ids = [f"pat-{i}" for i in range(4)]
    root = _stage(tmp_path, ids)
    doc = _run(monkeypatch, tmp_path, root)
    assert "pat-" not in capsys.readouterr().out + json.dumps(doc)  # room numbers only
    assert set(doc) == {
        "made_at",
        "ward",
        "rooms",
        "dropped",
        "on_now_source",
        "forecast_state",
    } and [r["room"] for r in doc["rooms"]] == [1, 2, 3, 4]
    r1, r4 = doc["rooms"][0], doc["rooms"][3]
    keys = "room updated_at cut_time window scope on_now p any_life_support"
    for k in (keys + " level out past_12h").split():
        assert k in r1
    assert set(r1["on_now"]) == {"imv", "vasopressor", "crrt", "ecmo"}
    assert set(r1["p"]) == {"imv", "vasopressor", "crrt", "icu_departure", "death"}
    assert r1["on_now"]["vasopressor"] is True and r1["p"]["vasopressor"] is None
    assert r1["on_now"]["ecmo"] is None and r1["scope"] == "room"
    assert r1["out"] is False and r4["out"] is True  # departure 0.1 vs 0.9 against 0.6
    assert r1["any_life_support"] == pytest.approx(1 - 0.5 * 0.9)  # IMV 0.5, crrt 0.1
    texts = {e["text"] for e in r1["past_12h"]}
    assert "On a ventilator (invasive)" in texts
    assert "Norepinephrine infusion running" in texts
    assert not any("TIME" in t or "5m" in t for t in texts)  # structure tokens skipped
    assert len(r1["past_12h"]) <= 8 and all(1 <= e["h"] <= 12 for e in r1["past_12h"])


def test_room_scope_rewrites_only_that_room(tmp_path, monkeypatch, capsys):
    ids = [f"pat-{i}" for i in range(4)]
    root = _stage(tmp_path, ids)
    before = _run(monkeypatch, tmp_path, root)
    # change room 3's death probability only, then rewrite room 3
    df = pl.read_parquet(root / f"scores-rep-based-{MODEL}.parquet")
    d = df[f"{DEATH}_rep_score"].to_numpy().copy()
    d[2] = 0.77
    df.with_columns(pl.Series(f"{DEATH}_rep_score", d)).write_parquet(
        root / f"scores-rep-based-{MODEL}.parquet"
    )
    fc = tmp_path / "forecast.json"
    after = _run(monkeypatch, tmp_path, root, "--room", "3")
    assert after["rooms"][2]["p"]["death"] == 0.77
    for i in (0, 1, 3):
        assert after["rooms"][i] == before["rooms"][i]  # untouched
    assert after["made_at"] == before["made_at"] and not fc.exists()  # no recount
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert (
        out["scope"] == "room"
        and out["rooms_written"] == 1
        and out["rooms_in_file"] == 4
    )
    # --recount rebuilds the forecast too
    _run(monkeypatch, tmp_path, root, "--room", "3", "--recount", "--forecast", str(fc))
    assert json.loads(fc.read_text())["scope"] == "unit"


def test_room_scope_drops_a_room_whose_stay_ended(tmp_path, monkeypatch, capsys):
    ids = [f"pat-{i}" for i in range(3)]
    root = _stage(tmp_path, ids)
    _run(monkeypatch, tmp_path, root)
    df = pl.read_parquet(root / f"scores-rep-based-{MODEL}.parquet").filter(
        pl.col("hospitalization_id") != "pat-1"
    )  # the winnower dropped it after a later cut
    df.write_parquet(root / f"scores-rep-based-{MODEL}.parquet")
    doc = _run(monkeypatch, tmp_path, root, "--room", "2")
    assert [r["room"] for r in doc["rooms"]] == [1, 3]
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["dropped"] == 1


def test_rooms_apply_probes_for_one_room_keeps_the_ward_scores(tmp_path, monkeypatch):
    rng = np.random.default_rng(0)
    train = tmp_path / "train"
    train.mkdir()
    for split, n in (("train", 120), ("held_out", 30)):
        x = rng.normal(size=(n, 4)).astype(np.float32)
        ids = [f"{split}{i}" for i in range(n)]
        pl.DataFrame({"hospitalization_id": ids, "features": list(x)}).write_parquet(
            train / f"features-{split}-{MODEL}.parquet"
        )
        lab = {"hospitalization_id": ids}
        for t in (IMV, VASO, CRRT, WARD, STEP, DEATH):
            lab[f"{t}_past"] = np.zeros(n, bool)
            lab[f"{t}_future"] = x[:, 0] + rng.normal(size=n) > 0
        pl.DataFrame(lab).write_parquet(train / f"{split}_for_inference.parquet")
    cfg = OmegaConf.create({"score": {"target_tokens": ["*"]}})
    home = _model_dir(tmp_path)
    rep_based.RepBasedScorer(train, {}, home, cfg, "logistic").save_all(n_samples=20)
    probes = train / f"probe-{home.name}.joblib"
    ids = [f"held_out{i}" for i in range(5)]
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "vocab.yaml").write_text(yaml.safe_dump({"lookup": LOOKUP}))
    lab = pl.read_parquet(train / "held_out_for_inference.parquet").filter(
        pl.col("hospitalization_id").is_in(ids)
    )
    lab.with_columns(
        tokens_past=pl.lit([1, 2, 3]),
        s_elapsed_past=pl.lit([0, 100, 90000]),
        cut_s=pl.lit(86500.0),
    ).write_parquet(stage / "held_out_for_inference.parquet")
    pl.read_parquet(train / f"features-held_out-{MODEL}.parquet").filter(
        pl.col("hospitalization_id").is_in(ids)
    ).with_columns(cut_s=pl.lit(86500.0)).write_parquet(
        stage / f"features-held_out-{MODEL}.parquet"
    )
    rep_based.write_features_meta(stage / f"features-held_out-{MODEL}.parquet", home)
    pl.DataFrame({"room": range(1, 6), "hospitalization_id": ids}).write_csv(
        tmp_path / "stage_ward.csv"
    )
    args = ["--model", str(home), "--probes", str(probes)]
    argv = lambda *e: [  # noqa: E731
        "rooms",
        str(stage),
        *args,
        "--stay-ids",
        str(tmp_path / "stage_ward.csv"),
        "--out",
        str(tmp_path / "rooms.json"),
        *e,
    ]
    monkeypatch.setattr("sys.argv", argv())  # whole ward
    rooms.main()
    ward = stage / f"scores-rep-based-{MODEL}.parquet"
    assert pl.read_parquet(ward).height == 5
    monkeypatch.setattr("sys.argv", argv("--room", "2"))
    rooms.main()
    assert pl.read_parquet(ward).height == 5  # the one-room rescore went to a side file
    assert pl.read_parquet(stage / "scores-rep-room-2.parquet").height == 1
    assert len(json.loads((tmp_path / "rooms.json").read_text())["rooms"]) == 5


def test_rooms_refuse_stale_features(tmp_path, monkeypatch):
    import os

    ids = ["a", "b"]
    root = _stage(tmp_path, ids)
    feats = root / f"features-held_out-{MODEL}.parquet"
    pl.DataFrame({"hospitalization_id": ids, "features": [[0.0], [0.0]]}).write_parquet(
        feats
    )
    lab = root / "held_out_for_inference.parquet"
    os.utime(feats, (1, 1))  # features older than the winnowed labels
    monkeypatch.setattr(
        "sys.argv",
        [
            "rooms",
            str(root),
            "--model",
            MODEL,
            "--probes",
            str(tmp_path),
            "--stay-ids",
            str(tmp_path / "stage_ward.csv"),
            "--out",
            str(tmp_path / "r.json"),
        ],
    )
    with pytest.raises(SystemExit, match="icutwin-extract"):
        rooms.main()
    assert lab.exists()


# ---- demo clock ----
def _timeline(tmp_path):
    lookup = {
        "BOS": 1,
        "ADT//TRANSFER_IN//icu": 2,
        "RESP//device_category//imv": 4,
        "EOS": 5,
    }
    t0 = dt.datetime(2020, 1, 1)
    h = lambda x: t0 + dt.timedelta(hours=x)  # noqa: E731
    rows = [
        ("a", 0, "BOS"),
        ("a", 10, "ADT//TRANSFER_IN//icu"),  # cut at 34 h
        ("a", 30, "RESP//device_category//imv"),
        ("a", 40, "RESP//device_category//imv"),
        ("a", 70, "EOS"),
        ("b", 0, "BOS"),
        ("b", 2, "ADT//TRANSFER_IN//icu"),  # cut at 26 h
        ("b", 30, "EOS"),  # the record ends 4 h after the cut
    ]
    pl.DataFrame(
        {
            "hospitalization_id": [r[0] for r in rows],
            "event_time": [h(r[1]) for r in rows],
            "token_id": [lookup[r[2]] for r in rows],
            "value": [None] * len(rows),
            "position_id": list(range(len(rows))),
        },
        schema_overrides={"value": pl.Float64},
    ).write_parquet(tmp_path / "tokens_held_out.parquet")
    return lookup


def _cfg(offset_s=None):
    spec = {"token": "ADT//TRANSFER_IN//icu", "duration_s": 86400}
    if offset_s is not None:
        spec["offset_s"] = offset_s
    return OmegaConf.create(
        {
            "outcome_tokens": ["RESP//device_category//imv"],
            "threshold": {"after_first_occurrence": spec},
            "horizon_after_threshold_s": 86400,
        }
    )


def test_demo_clock_offset_moves_the_cut_and_drops_ended_stays(tmp_path):
    lookup = _timeline(tmp_path)
    base = Winnower(tmp_path, _cfg(), lookup).prepare_winnowed_frame().collect()
    assert sorted(base["hospitalization_id"]) == ["a", "b"]
    a0 = base.filter(pl.col("hospitalization_id") == "a")
    assert a0["tokens_past"].list.len().to_list() == [3] and a0["cut_s"].to_list() == [
        34 * 3600
    ]
    # +10 h: stay a is cut at 44 h (one more imv in the past); stay b's record
    # ends at 30 h, before its new cut
    moved = (
        Winnower(tmp_path, _cfg(10 * 3600), lookup).prepare_winnowed_frame().collect()
    )
    assert moved["hospitalization_id"].to_list() == ["a"]  # b dropped: record ended
    assert moved["tokens_past"].list.len().to_list() == [4]
    assert moved["cut_s"].to_list() == [44 * 3600]


def test_demo_clock_flag_is_applied_by_winnow(tmp_path):
    from icutwin.scoring import winnower

    lookup = _timeline(tmp_path)
    pl.DataFrame({"x": [1]}).write_parquet(tmp_path / "tokens_train.parquet")
    pl.DataFrame({"x": [1]}).write_parquet(tmp_path / "tokens_tuning.parquet")
    (tmp_path / "vocab.yaml").write_text(yaml.safe_dump({"lookup": lookup}))
    cfgf = tmp_path / "w.yaml"
    cfgf.write_text(
        yaml.safe_dump(
            {
                "outcome_tokens": ["RESP//device_category//imv"],
                "threshold": {
                    "after_first_occurrence": {
                        "token": "ADT//TRANSFER_IN//icu",
                        "duration_s": 86400,
                    }
                },
                "horizon_after_threshold_s": 86400,
                "splits": ["held_out"],
            }
        )
    )
    winnower.winnow(tmp_path, cfgf, demo_clock_hours=10)
    out = pl.read_parquet(tmp_path / "held_out_for_inference.parquet")
    assert out["hospitalization_id"].to_list() == ["a"]
    assert out["last_valid"].to_list() == [4]


# ---- running at the cut (2026-11-14): last record before the cut ----
AT_LOOKUP = {
    "BOS": 1,
    "ADT//TRANSFER_IN//icu": 2,
    "RESP//device_category//imv": 3,
    "RESP//device_category//nippv": 4,
    "MED_CON//norepinephrine//B2": 5,
    "MED_CON//vasopressin//B1": 6,
    "CRRT//crrt_init": 7,
    "EOS": 8,
}


def _at_cut_frame(tmp_path):
    t0 = dt.datetime(2020, 1, 1)
    h = lambda x: t0 + dt.timedelta(hours=x)  # noqa: E731
    imv, nippv = "RESP//device_category//imv", "RESP//device_category//nippv"
    nor, vas = "MED_CON//norepinephrine//B2", "MED_CON//vasopressin//B1"
    crrt = "CRRT//crrt_init"
    ev = {  # stay -> [(hours, token, value)]; ICU at 1 h, so the cut is at 25 h
        "imv_on": [(5, imv, None), (20, imv, None)],
        "imv_to_nippv": [(5, imv, None), (20, nippv, None)],  # device changed: off
        "pressor_on": [(5, nor, 0.2), (20, nor, 0.1)],
        "pressor_stopped": [(5, nor, 0.2), (20, nor, 0.0)],  # dose 0: off
        "pressor_mixed": [(5, nor, 0.0), (6, vas, 0.04), (20, nor, 0.0)],  # vaso on
        "pressor_after_cut": [(30, nor, 0.2)],  # after the cut: not known at the cut
        "pressor_null_carry": [(5, nor, 0.2), (20, nor, None)],  # null = unknown
        "pressor_null_only": [(20, nor, None)],  # never a known dose
        "crrt_recent": [(10, crrt, None)],
        "crrt_old": [(0.5, crrt, None)],  # 24.5 h before the cut: outside 24 h
    }
    rows = []
    for sid, e in ev.items():
        rows += [(sid, 0, "BOS", None), (sid, 1, "ADT//TRANSFER_IN//icu", None)]
        rows += [(sid, hh, tok, v) for hh, tok, v in e]
        rows += [(sid, 60, "EOS", None)]
    pl.DataFrame(
        {
            "hospitalization_id": [r[0] for r in rows],
            "event_time": [h(r[1]) for r in rows],
            "token_id": [AT_LOOKUP[r[2]] for r in rows],
            "value": [r[3] for r in rows],
            "position_id": list(range(len(rows))),
        },
        schema_overrides={"value": pl.Float64},
    ).write_parquet(tmp_path / "tokens_held_out.parquet")


def test_at_cut_flags_last_record_before_the_cut(tmp_path):
    from icutwin.common import merge_config

    _at_cut_frame(tmp_path)
    cfg = OmegaConf.merge(
        _cfg(), {"at_cut": merge_config("winnowing.yaml", None).at_cut}
    )
    df = Winnower(tmp_path, cfg, AT_LOOKUP).prepare_winnowed_frame().collect()
    got = {
        r["hospitalization_id"]: (
            r["LABEL//imv_at_cut"],
            r["LABEL//pressor_at_cut"],
            r["LABEL//crrt_at_cut"],
        )
        for r in df.iter_rows(named=True)
    }
    assert got["imv_on"][0] is True
    assert got["imv_to_nippv"][0] is False  # imv then nippv before the cut: off
    assert got["pressor_on"][1] is True
    assert got["pressor_stopped"][1] is False  # last dose 0: off
    assert got["pressor_mixed"][1] is True  # one drug's last dose is still > 0
    assert got["pressor_after_cut"][1] is False  # only after the cut
    assert got["pressor_null_carry"][1] is True  # last non-null dose (0.2) carries
    assert got["pressor_null_only"][1] is False  # no known dose: not running
    assert got["crrt_recent"][2] is True
    assert got["crrt_old"][2] is False  # no stop signal: only the last 24 h count
    assert got["imv_on"][1:] == (False, False)  # nothing else running


def test_running_at_cut_drives_now_counts_and_stopped_is_forecastable():
    df = scores(3, p={IMV: [0.5, 0.5, 0.5]}, past={IMV: [True, True, False]})
    df = df.with_columns(
        pl.Series("LABEL//imv_at_cut", [True, False, False]),  # stay 1: stopped
        pl.Series("LABEL//pressor_at_cut", [False] * 3),
        pl.Series("LABEL//crrt_at_cut", [False] * 3),
    )
    tab = aggregate.patient_table(df)
    assert tab["on"]["imv"].tolist() == [True, False, False]
    assert tab["stopped"]["imv"].tolist() == [False, True, False]
    assert np.isnan(tab["p"]["ventilator"][0]) and tab["p"]["ventilator"][1] == 0.5
    ls = aggregate.life_support_block(tab)
    assert ls["now_patients"] == 1 and ls["now_by"]["imv"] == 1
    # the resource count also treats the stopped stay as a possible new start
    probs = aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)
    assert probs["ventilator"].tolist() == [0.0, 0.5, 0.5]
    # typical baseline: a stay whose imv stopped before the cut is not "on"
    cols = {}
    for t in (IMV, VASO, CRRT):
        cols[f"{t}_past"] = [True, False, False, False] if t == IMV else [False] * 4
        cols[f"{t}_future"] = [False] * 4
    lab = pl.DataFrame(cols)
    for c in ("imv", "pressor", "crrt"):
        lab = lab.with_columns(pl.Series(f"LABEL//{c}_at_cut", [False] * 4))
    assert aggregate.typical_life_support_rate(lab) == 0.0


def test_rooms_on_life_support_stopped_note_and_plain_bands(tmp_path, monkeypatch):
    ids = [f"pat-{i}" for i in range(3)]
    root = _stage(tmp_path, ids)
    df = pl.read_parquet(root / f"scores-rep-based-{MODEL}.parquet")
    run = {
        "LABEL//imv_at_cut": [True, True, False],
        "LABEL//pressor_at_cut": [True, False, False],
        "LABEL//crrt_at_cut": [False, False, False],
    }
    df = df.with_columns(*(pl.Series(k, v) for k, v in run.items())).with_columns(
        pl.Series(f"{IMV}_past", [True, True, True])  # room 3: stopped before the cut
    )
    df.write_parquet(root / f"scores-rep-based-{MODEL}.parquet")
    doc = _run(monkeypatch, tmp_path, root)
    r1, r2, r3 = doc["rooms"]
    assert r1["on_life_support"] is True and r2["on_life_support"] is False
    assert r1["level"] in ("low", "medium", "high")  # level still computed
    assert r3["stopped_before_cut"] == {
        "imv": True,
        "vasopressor": False,
        "crrt": False,
    }
    assert r3["on_now"]["imv"] is False and r3["p"]["imv"] is not None
    assert doc["dropped"] == 0
    assert rooms.token_text("LAB_RES//lactate//H2") == "Lactate result: high"
    assert rooms.token_text("LAB_RES//lactate//N1") == "Lactate result: normal"
    assert rooms.token_text("LAB_RES//lactate//B3") == "Lactate result"  # no reference
    assert "band" not in rooms.token_text("VITAL//map//B2")


def test_merge_features_keeps_other_stays(tmp_path):
    from icutwin.scoring.extractor import merge_features

    f = tmp_path / "f.parquet"
    pl.DataFrame(
        {"hospitalization_id": ["a", "b"], "features": [[1.0], [2.0]]}
    ).write_parquet(f)
    new = pl.DataFrame({"hospitalization_id": ["b"], "features": [[9.0]]})
    out = merge_features(f, new).sort("hospitalization_id")
    assert out["hospitalization_id"].to_list() == ["a", "b"]
    assert out["features"].to_list() == [[1.0], [9.0]]
    assert merge_features(tmp_path / "none.parquet", new).height == 1


def test_apply_probes_leaves_past_events_unscored(tmp_path):
    """main's task rule: an event already seen before the cut gets no probability,
    even when the support was stopped by the cut (`at_cut` is display-only)"""
    rng = np.random.default_rng(0)
    train = tmp_path / "train"
    train.mkdir()
    for split, n in (("train", 120), ("held_out", 10)):
        x = rng.normal(size=(n, 4)).astype(np.float32)
        ids = [f"{split}{i}" for i in range(n)]
        pl.DataFrame({"hospitalization_id": ids, "features": list(x)}).write_parquet(
            train / f"features-{split}-{MODEL}.parquet"
        )
        lab = {"hospitalization_id": ids, f"{IMV}_past": np.zeros(n, bool)}
        lab[f"{IMV}_future"] = x[:, 0] + rng.normal(size=n) > 0
        pl.DataFrame(lab).write_parquet(train / f"{split}_for_inference.parquet")
    cfg = OmegaConf.create({"score": {"target_tokens": [IMV]}})
    rep_based.RepBasedScorer(train, {}, MODEL, cfg, "logistic").save_all(n_samples=20)
    probes = train / f"probe-{pathlib.Path(MODEL).name}.joblib"
    lab = pl.read_parquet(train / "held_out_for_inference.parquet").with_columns(
        pl.Series(f"{IMV}_past", [True] * 3 + [False] * 7),
        pl.Series("LABEL//imv_at_cut", [True, False, False] + [False] * 7),
    )
    lab.write_parquet(train / "held_out_for_inference.parquet")
    scored = pl.read_parquet(
        rep_based.apply_probes(
            train, MODEL, probes, [f"held_out{i}" for i in range(10)]
        )
    ).sort("hospitalization_id")
    p = scored.sort(pl.col("hospitalization_id").str.replace("held_out", "").cast(int))[
        f"{IMV}_rep_score"
    ].to_numpy()
    assert np.isnan(p[:3]).all() and not np.isnan(p[3:]).any()


def test_demographics_age_band_and_sex(tmp_path):
    import polars as pl

    from app import rooms

    pl.DataFrame(
        {
            "hospitalization_id": ["h1", "h2", "h3"],
            "patient_id": ["p1", "p2", "p3"],
            "age_at_admission": [67, 91, None],
        }
    ).write_parquet(tmp_path / "clif_hospitalization.parquet")
    pl.DataFrame(
        {"patient_id": ["p1", "p2", "p3"], "sex_category": ["Female", "Male", None]}
    ).write_parquet(tmp_path / "clif_patient.parquet")
    d = rooms.demographics(tmp_path, ["h1", "h2", "h3"])
    assert d["h1"] == {"age": "67", "sex": "F"}
    assert d["h2"] == {"age": "90+", "sex": "M"}  # 90 and over shown as 90+
    assert d["h3"] == {"age": None, "sex": None}
    assert rooms.demographics(None, ["h1"]) == {}


# ---- review fixes (2026-11-14) ----
def test_skipped_probe_is_not_already_happened():
    """P1: a NaN from a skipped probe must not zero a whole unit's departure"""
    n = 5
    nan = np.full(n, np.nan)
    df = scores(n, p={WARD: nan, STEP: np.full(n, 0.3)})  # ward probe skipped
    probs = aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)
    np.testing.assert_allclose(probs["icu_departure"], 0.3)
    # a stay that really had a ward transfer before the cut is still "already"
    df = df.with_columns(pl.Series(f"{WARD}_past", [True] + [False] * (n - 1)))
    got = aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)
    assert got["icu_departure"].tolist() == [0.0] + [0.3] * (n - 1)


def test_skipped_single_token_probe_is_no_data_not_zero(tmp_path):
    n = 6
    df = scores(n, p={CRRT: np.full(n, np.nan)})  # CRRT probe skipped in training
    probs = aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)
    assert np.isnan(probs["crrt"]).all()
    res = aggregate.strain(probs, np.random.default_rng(0), aggregate.RESOURCES_REP)
    assert res["crrt"] == {
        "team": "ICU team",
        "available": False,
        "p10": None,
        "p50": None,
        "p90": None,
        "expected": None,
    }
    assert res["ventilator"]["available"] is True and res["ventilator"]["p50"] >= 0
    # life support: the skipped support has null counts, the others keep theirs
    tab = aggregate.patient_table(df)
    ls = aggregate.life_support_block(tab)
    assert ls["expected_by"]["crrt"]["available"] is False
    assert ls["expected_by"]["crrt"]["p50"] is None
    assert ls["expected_by"]["imv"]["available"] is True
    # a stay with the probe running is not "skipped" (NaN there is "already on")
    df2 = scores(n, p={CRRT: np.full(n, np.nan)}, past={CRRT: np.ones(n, bool)})
    assert not aggregate.patient_table(df2)["skipped"]["crrt"].any()
    probs2 = aggregate.unit_probs(df2, "_rep_score", aggregate.RESOURCES_REP)
    assert probs2["crrt"].tolist() == [0.0] * n  # everyone on it: zero new, real data
    # the strain index leaves a task with no data out of the typical day
    st = aggregate.strain_index(
        probs, {"crrt": 0.1, "ventilator": 0.2}, np.random.default_rng(0)
    )
    assert st["tasks"] == ["ventilator"]


def test_rooms_show_a_skipped_probe_as_null_with_a_flag(tmp_path, monkeypatch):
    ids = [f"pat-{i}" for i in range(2)]
    root = _stage(tmp_path, ids)
    df = pl.read_parquet(root / f"scores-rep-based-{MODEL}.parquet").with_columns(
        pl.Series(f"{CRRT}_rep_score", [float("nan")] * 2)
    )
    _write_scores(root, df, MODEL, tmp_path / MODEL)
    r = _run(monkeypatch, tmp_path, root)["rooms"][0]
    assert r["p"]["crrt"] is None and r["skipped"]["crrt"] is True
    assert r["skipped"]["imv"] is False and r["p"]["imv"] == 0.5
    # running at the cut is null too, but not "skipped"
    assert r["on_now"]["vasopressor"] is True and r["skipped"]["vasopressor"] is False


def test_ward_and_stepdown_add_not_max():
    """P2: the two transfers exclude each other, so the leaving chance is their sum"""
    df = scores(3, p={WARD: [0.3, 0.8, 0.0], STEP: [0.4, 0.5, 0.0]})
    tab = aggregate.patient_table(df)
    np.testing.assert_allclose(tab["p"]["icu_departure"], [0.7, 1.0, 0.0])  # clipped
    probs = aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)
    np.testing.assert_allclose(probs["icu_departure"], [0.7, 1.0, 0.0])
    # the out tag reads the corrected value: 0.3 + 0.4 crosses 0.6, max would not
    assert 0.7 >= aggregate.OUT_TAG > max(0.3, 0.4)


def test_out_tag_uses_the_summed_departure(tmp_path, monkeypatch):
    ids = ["pat-0", "pat-1"]
    root = _stage(tmp_path, ids)
    df = pl.read_parquet(root / f"scores-rep-based-{MODEL}.parquet").with_columns(
        pl.Series(f"{WARD}_rep_score", [0.35, 0.1]),
        pl.Series(f"{STEP}_rep_score", [0.35, 0.1]),
    )
    _write_scores(root, df, MODEL, tmp_path / MODEL)
    r1, r2 = _run(monkeypatch, tmp_path, root)["rooms"]
    assert r1["p"]["icu_departure"] == 0.7 and r1["out"] is True
    assert r2["p"]["icu_departure"] == 0.2 and r2["out"] is False


def test_typical_rates_use_the_at_cut_definition():
    """a support that stopped before the cut is a possible new start on both sides"""
    cols = {}
    for t in (IMV, VASO, CRRT, WARD, STEP, DEATH):
        cols[f"{t}_past"] = [True, True, False, False]
        cols[f"{t}_future"] = [True, False, True, False]
    lab = pl.DataFrame(cols).with_columns(
        pl.Series("LABEL//imv_at_cut", [False, False, False, False])  # stay 0 stopped
    )
    r = aggregate.typical_rates(lab)
    # stay 0 (stopped, then again) and stay 2 are new starts: 2 of 4
    assert r["ventilator"] == 0.5
    assert r["vasopressor"] == 0.25  # no at_cut column: the old `_past` rule
    # departure is "either", unchanged
    assert r["icu_departure"] == 0.25


def test_check_first_ranks_the_new_start_chance_the_unit_count_uses():
    # stay 0 is on IMV with a 0.9 vasopressor chance; stay 1 is on nothing at 0.5
    df = scores(
        3,
        p={IMV: [0.0, 0.5, 0.1], VASO: [0.9, 0.0, 0.1], CRRT: np.zeros(3)},
        past={IMV: [True, False, False]},
    )
    tab = aggregate.patient_table(df)
    rooms_map = {"s0": 1, "s1": 2, "s2": 3}
    first = aggregate.check_first(df, tab, rooms_map)
    assert [c["room"] for c in first] == [2]  # stay 0 is already on: not a new start
    ls = aggregate.life_support_block(tab)
    assert ls["now_patients"] == 1 and ls["expected_new_patients"]["expected"] == 0.69


def test_read_capacity_accepts_numbers_only(tmp_path, capsys):
    f = tmp_path / "cap.json"
    ok = lambda body: (f.write_text(body), aggregate.read_capacity(f))[1]  # noqa: E731
    assert ok('{"life_support_patients": 0}')["life_support_patients"] == 0
    assert ok('{"life_support_patients": 50}')["life_support_patients"] == 50
    assert ok('{"life_support_patients": 7.5}')["life_support_patients"] == 7.5
    assert capsys.readouterr().out == ""
    for bad in (
        '{"life_support_patients": true}',  # bool is not a count
        '{"life_support_patients": "9"}',  # nor is a string
        '{"life_support_patients": 51}',
        '{"life_support_patients": -1}',
        '{"life_support_patients": NaN}',
        '{"life_support_patients": null}',
        "[1, 2]",
        "{}",
        "not json",
    ):
        assert ok(bad) is None, bad
        assert "capacity file unreadable" in capsys.readouterr().out, bad  # all alike


def test_past_12h_hour_is_rounded_up_and_stops_at_12_h(tmp_path):
    lookup = {
        "BOS": 1,
        "ADT//TRANSFER_IN//icu": 2,
        IMV: 3,
        "MED_CON//norepinephrine//B3": 4,
    }
    lookup |= {"VITAL//map//B2": 5, "VITAL//sbp//B2": 6, "VITAL//heart_rate//B2": 7}
    cut = 100_000.0
    ages = {3: 0, 4: 3600, 5: 3601, 6: 43200, 7: 43201}  # token -> seconds before cut
    toks = [7, 6, 5, 4, 3]
    secs = [cut - ages[t] for t in toks]
    pl.DataFrame(
        {
            "hospitalization_id": ["a"],
            "tokens_past": [toks],
            "s_elapsed_past": [secs],
            "cut_s": [cut],
        }
    ).write_parquet(tmp_path / "held_out_for_inference.parquet")
    words = {i: w for w, i in lookup.items()}
    got = {e["text"]: e["h"] for e in rooms.past_events(tmp_path, ["a"], words)["a"]}
    assert got["On a ventilator (invasive)"] == 1  # age 0: hour 1, not 0
    assert got["Norepinephrine infusion running"] == 1  # exactly 1 h: hour 1
    assert got["Mean arterial pressure"] == 2  # 3601 s: hour 2
    assert got["Systolic blood pressure"] == 12  # exactly 12 h: hour 12
    assert "Heart rate" not in got  # 12 h + 1 s: left out


def test_dropped_is_the_ward_minus_rooms_present_never_negative(
    tmp_path, monkeypatch, capsys
):
    ids = [f"pat-{i}" for i in range(3)]
    root = _stage(tmp_path, ids)
    # room scope with no rooms.json yet: refused (it would be a one-room file)
    with pytest.raises(SystemExit, match="whole ward first"):
        _run(monkeypatch, tmp_path, root, "--room", "2")
    doc = _run(monkeypatch, tmp_path, root)
    assert doc["dropped"] == 0
    # a hand-edited / older file with a room the map no longer has: never negative
    doc["rooms"].append({**doc["rooms"][0], "room": 9})
    (tmp_path / "rooms.json").write_text(json.dumps(doc))
    again = _run(monkeypatch, tmp_path, root, "--room", "1")
    assert again["dropped"] == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["dropped"] == 0


def test_default_time_zone_is_the_site_and_demo_clock_moves_the_cut():
    import argparse
    import inspect

    assert aggregate.DEFAULT_TZ == "America/Chicago"
    assert (
        inspect.signature(aggregate.build_forecast).parameters["tz"].default
        == "America/Chicago"
    )
    chi = dt.timezone(dt.timedelta(hours=-6))
    at = lambda h, m=0, d=14: dt.datetime(2026, 11, d, h, m, tzinfo=chi)  # noqa: E731
    cut = lambda made, hours=0: aggregate.cut_time_for(  # noqa: E731
        made, "America/Chicago", None, hours
    )
    assert cut(at(6, 30)) == at(7)  # scheduled: the 07:00 nearest
    assert cut(at(8)) == at(7)
    # demo clock: the last 07:00 plus the hours (what the dispatcher counts)
    assert cut(at(13), 6) == at(13)
    assert cut(at(23), 16) == at(23)  # not tomorrow's 07:00 + 16 h
    assert cut(at(1), 18) == at(1)  # after midnight: yesterday's 07:00 + 18 h
    w = aggregate.window_for(cut(at(13), 6))
    assert w["start"] == "2026-11-14T13:00:00-06:00"
    assert w["end"] == "2026-11-15T13:00:00-06:00"
    # an explicit cut is taken as given, and must carry an offset
    given = aggregate.cut_time_for(at(13), "UTC", "2026-11-14T07:00:00-06:00", 6)
    assert given == at(7)
    with pytest.raises(ValueError, match="UTC offset"):
        aggregate.cut_time_for(at(13), "UTC", "2026-11-14T07:00:00")
    with pytest.raises(argparse.ArgumentTypeError, match="UTC offset"):
        aggregate.cut_arg("2026-11-14T07:00:00")


def test_forecast_cut_time_and_window_follow_the_demo_clock(monkeypatch):
    real = dt.datetime

    class Fake(real):
        @classmethod
        def now(cls, tz=None):
            return real(2026, 11, 14, 19, 0, tzinfo=dt.timezone.utc)  # 13:00 Chicago

    monkeypatch.setattr(
        aggregate,
        "dt",
        type(
            "D",
            (),
            {"datetime": Fake, "timedelta": dt.timedelta, "timezone": dt.timezone},
        ),
    )
    fc = aggregate.build_forecast(scores(25), "m", demo_clock_hours=6)
    assert fc["demo_clock_hours"] == 6
    assert fc["cut_time"] == "2026-11-14T13:00:00-06:00" == fc["window"]["start"]
    assert fc["window"]["end"] == "2026-11-15T13:00:00-06:00"
    fc0 = aggregate.build_forecast(scores(25), "m")  # scheduled run, hours 0
    assert fc0["cut_time"] == "2026-11-14T07:00:00-06:00"


def test_cli_refuses_a_naive_cut_time_and_says_chicago(tmp_path, monkeypatch, capsys):
    _write_scores(tmp_path, scores(25))
    out = tmp_path / "forecast.json"
    monkeypatch.setattr(
        "sys.argv",
        ["aggregate", str(tmp_path), str(out), "--cut-time", "2026-11-14T07:00:00"],
    )
    with pytest.raises(SystemExit):
        aggregate.main()
    assert "UTC offset" in capsys.readouterr().err and not out.exists()
    for main in (aggregate.main, rooms.main):
        monkeypatch.setattr("sys.argv", ["x", "--help"])
        with pytest.raises(SystemExit):
            main()
        assert "America/Chicago" in capsys.readouterr().out


# ---- features carry their cut; probes and scores carry their weights ----
def _fit_probes(tmp_path, home):
    rng = np.random.default_rng(0)
    train = tmp_path / "train"
    train.mkdir()
    for split, n in (("train", 120), ("held_out", 30)):
        x = rng.normal(size=(n, 4)).astype(np.float32)
        ids = [f"{split}{i}" for i in range(n)]
        pl.DataFrame({"hospitalization_id": ids, "features": list(x)}).write_parquet(
            train / f"features-{split}-{MODEL}.parquet"
        )
        lab = {"hospitalization_id": ids}
        for t in (IMV, VASO, CRRT, WARD, STEP, DEATH):
            lab[f"{t}_past"] = np.zeros(n, bool)
            lab[f"{t}_future"] = x[:, 0] + rng.normal(size=n) > 0
        pl.DataFrame(lab).write_parquet(train / f"{split}_for_inference.parquet")
    cfg = OmegaConf.create({"score": {"target_tokens": ["*"]}})
    rep_based.RepBasedScorer(train, {}, home, cfg, "logistic").save_all(n_samples=20)
    probes = train / f"probe-{pathlib.Path(home).name}.joblib"
    return train, probes


def _ward_stage(tmp_path, train, ids, cut_s, last_valid=40):
    """a stage folder whose labels and features carry the given cut"""
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "vocab.yaml").write_text(yaml.safe_dump({"lookup": LOOKUP}))
    lab = pl.read_parquet(train / "held_out_for_inference.parquet").filter(
        pl.col("hospitalization_id").is_in(ids)
    )
    lab.with_columns(
        tokens_past=pl.lit([1, 2, 3]),
        s_elapsed_past=pl.lit([0, 100, 90000]),
        cut_s=pl.lit(cut_s),
        last_valid=pl.lit(last_valid),
    ).write_parquet(stage / "held_out_for_inference.parquet")
    pl.read_parquet(train / f"features-held_out-{MODEL}.parquet").filter(
        pl.col("hospitalization_id").is_in(ids)
    ).with_columns(cut_s=pl.lit(cut_s), last_valid=pl.lit(last_valid)).write_parquet(
        stage / f"features-held_out-{MODEL}.parquet"
    )
    rep_based.write_features_meta(  # as icutwin-extract does, for the model in use
        stage / f"features-held_out-{MODEL}.parquet", tmp_path / MODEL
    )
    pl.DataFrame({"room": range(1, len(ids) + 1), "hospitalization_id": ids}).write_csv(
        tmp_path / "stage_ward.csv"
    )
    return stage


def _rooms_argv(tmp_path, stage, home, probes, *extra):
    return [
        "rooms",
        str(stage),
        "--model",
        str(home),
        "--probes",
        str(probes),
        "--stay-ids",
        str(tmp_path / "stage_ward.csv"),
        "--out",
        str(tmp_path / "rooms.json"),
        *extra,
    ]


def test_one_room_extract_after_a_demo_clock_move_leaves_the_rest_stale(
    tmp_path, monkeypatch
):
    from icutwin.scoring.extractor import merge_features

    home = _model_dir(tmp_path)
    train, probes = _fit_probes(tmp_path, home)
    ids = [f"held_out{i}" for i in range(5)]
    stage = _ward_stage(tmp_path, train, ids, 86500.0)
    monkeypatch.setattr("sys.argv", _rooms_argv(tmp_path, stage, home, probes))
    rooms.main()  # whole ward at the 24 h cut: features and labels agree

    # demo clock +6 h: the winnower moves every stay's cut ...
    lab = pl.read_parquet(stage / "held_out_for_inference.parquet")
    lab.with_columns(
        cut_s=pl.lit(86500.0 + 21600), last_valid=pl.lit(55)
    ).write_parquet(stage / "held_out_for_inference.parquet")
    # ... and only room 2 is re-extracted (merge_features keeps the other rows)
    feats = stage / f"features-held_out-{MODEL}.parquet"
    one = (
        pl.read_parquet(feats)
        .filter(pl.col("hospitalization_id") == "held_out1")
        .with_columns(cut_s=pl.lit(86500.0 + 21600), last_valid=pl.lit(55))
    )
    merge_features(feats, one).write_parquet(feats)

    monkeypatch.setattr(
        "sys.argv", _rooms_argv(tmp_path, stage, home, probes, "--room", "2")
    )
    rooms.main()  # the re-extracted room is current: fine
    for argv in ((), ("--room", "3")):  # the whole ward, or a room still at the old cut
        monkeypatch.setattr(
            "sys.argv", _rooms_argv(tmp_path, stage, home, probes, *argv)
        )
        with pytest.raises(SystemExit, match="icutwin-extract"):
            rooms.main()
    # apply_probes itself refuses them too (not only rooms.py)
    with pytest.raises(rep_based.StaleFeatures):
        rep_based.apply_probes(stage, home, probes, ["held_out2"])
    rep_based.apply_probes(stage, home, probes, ["held_out1"])


def test_features_made_before_cuts_were_stored_are_refused(tmp_path):
    home = _model_dir(tmp_path)
    train, probes = _fit_probes(tmp_path, home)
    stage = _ward_stage(tmp_path, train, ["held_out0"], 86500.0)
    f = stage / f"features-held_out-{MODEL}.parquet"
    pl.read_parquet(f).select("hospitalization_id", "features").write_parquet(f)
    with pytest.raises(rep_based.StaleFeatures, match="icutwin-extract"):
        rep_based.apply_probes(stage, home, probes)


def test_extractor_stores_each_rows_cut(tmp_path):
    """the extractor's per-row cut columns, from the labels (no model needed)"""
    from icutwin.scoring.extractor import merge_features

    old = pl.DataFrame({"hospitalization_id": ["a", "b"], "features": [[1.0], [2.0]]})
    f = tmp_path / "f.parquet"
    old.write_parquet(f)
    new = pl.DataFrame(
        {
            "hospitalization_id": ["b"],
            "features": [[9.0]],
            "last_valid": [7],
            "cut_s": [123.0],
        }
    )
    out = merge_features(f, new).sort("hospitalization_id")
    assert out["last_valid"].to_list() == [None, 7]  # kept row has no stored cut


def test_rooms_no_apply_needs_scores_made_with_these_weights(tmp_path, monkeypatch):
    ids = ["pat-0", "pat-1"]
    root = _stage(tmp_path, ids)
    _run(monkeypatch, tmp_path, root)  # made with the weights in the model folder
    (tmp_path / MODEL / "model.safetensors").write_bytes(b"retrained")  # same name
    with pytest.raises(SystemExit, match="other weights"):
        _run(monkeypatch, tmp_path, root)
    (tmp_path / MODEL / "model.safetensors").write_bytes(b"w1")
    rep_based.scores_meta_path(root / f"scores-rep-based-{MODEL}.parquet").unlink()
    with pytest.raises(SystemExit, match="not made for"):
        _run(monkeypatch, tmp_path, root)


def test_rooms_no_apply_reads_this_models_scores_not_the_newest(tmp_path, monkeypatch):
    ids = ["pat-0", "pat-1"]
    root = _stage(tmp_path, ids)
    other = scores(2, p={DEATH: [0.99, 0.99]}, ids=ids)  # another model, newer file
    _write_scores(root, other, "mdl-other", tmp_path / "mdl-other")
    doc = _run(monkeypatch, tmp_path, root)
    assert doc["rooms"][0]["p"]["death"] == 0.05


# ---- real MIMIC-IV ward: an explicit mode ----
def test_open_demo_check_reads_the_git_tracked_demo_hospitalization(monkeypatch):
    import pathlib

    real = (
        pathlib.Path(__file__).parent.parent / "clif_demo/clif_hospitalization.parquet"
    )
    monkeypatch.setattr(aggregate, "DEMO_HOSP", real)
    some = pl.read_parquet(real, columns=["hospitalization_id"])["hospitalization_id"]
    ok = {str(some[0]): 1, str(some[1]): 2}
    assert aggregate.check_ward(ok, False) == {
        "source": "open-demo",
        "label": "Open MIMIC-IV Demo",
    }
    with pytest.raises(SystemExit, match="--real-ward"):
        aggregate.check_ward({**ok, "not-in-the-demo": 3}, False)


def test_ward_without_real_flag_refuses_a_non_demo_stay(tmp_path, monkeypatch, capsys):
    ids = ["real-A", "real-B", "pat-0"]  # two stays are not in the open demo
    root = _stage(tmp_path, ids)
    with pytest.raises(SystemExit, match="2 of 3 stays") as e:
        _run(monkeypatch, tmp_path, root)
    assert "--real-ward" in str(e.value) and "real-A" not in str(e.value)  # counts only
    assert not (tmp_path / "rooms.json").exists()
    # aggregate.py with --stage-csv does the same
    _write_scores(tmp_path, scores(3, ids=ids))
    monkeypatch.setattr(
        "sys.argv",
        [
            "aggregate",
            str(tmp_path),
            str(tmp_path / "forecast.json"),
            "--stage-csv",
            str(tmp_path / "stage_ward.csv"),
        ],
    )
    with pytest.raises(SystemExit, match="--real-ward"):
        aggregate.main()
    assert not (tmp_path / "forecast.json").exists()


def test_real_ward_flag_allows_it_and_labels_the_output(tmp_path, monkeypatch, capsys):
    ids = ["real-A", "real-B", "real-C"]
    root = _stage(tmp_path, ids)
    doc = _run(monkeypatch, tmp_path, root, "--real-ward")
    assert doc["ward"] == {"source": "mimic-iv", "label": "Real MIMIC-IV · local only"}
    out = capsys.readouterr().out
    assert "real-" not in out and "real-" not in json.dumps(doc)  # counts, no ids
    assert [r["room"] for r in doc["rooms"]] == [1, 2, 3]
    # room scope keeps the ward block
    again = _run(monkeypatch, tmp_path, root, "--real-ward", "--room", "2")
    assert again["ward"]["source"] == "mimic-iv"
    # forecast.json says so too
    fc = tmp_path / "forecast.json"
    _run(monkeypatch, tmp_path, root, "--real-ward", "--recount", "--forecast", str(fc))
    assert json.loads(fc.read_text())["ward"]["source"] == "mimic-iv"
    # the unit CLI, with the stage csv
    monkeypatch.setattr(
        "sys.argv",
        [
            "aggregate",
            str(root),
            str(fc),
            "--stage-csv",
            str(tmp_path / "stage_ward.csv"),
            "--real-ward",
        ],
    )
    aggregate.main()
    got = json.loads(fc.read_text())
    assert got["ward"] == {"source": "mimic-iv", "label": "Real MIMIC-IV · local only"}
    assert "real-" not in capsys.readouterr().out + fc.read_text()


def test_default_ward_block_is_the_open_demo(tmp_path, monkeypatch):
    root = _stage(tmp_path, ["pat-0", "pat-1"])
    doc = _run(monkeypatch, tmp_path, root)
    assert doc["ward"] == {"source": "open-demo", "label": "Open MIMIC-IV Demo"}
    fc = aggregate.build_forecast(scores(25), "m")
    assert fc["ward"] == {"source": "open-demo", "label": "Open MIMIC-IV Demo"}


def test_demographics_may_point_at_the_real_clif_folder(tmp_path, monkeypatch):
    ids = ["real-A", "real-B"]
    root = _stage(tmp_path, ids)
    clif = tmp_path / "real_clif"
    clif.mkdir()
    pl.DataFrame(
        {
            "hospitalization_id": ids,
            "patient_id": ["p1", "p2"],
            "age_at_admission": [54.0, 93.0],
        }
    ).write_parquet(clif / "clif_hospitalization.parquet")
    pl.DataFrame(
        {"patient_id": ["p1", "p2"], "sex_category": ["Male", "Female"]}
    ).write_parquet(clif / "clif_patient.parquet")
    doc = _run(monkeypatch, tmp_path, root, "--real-ward", "--demographics", str(clif))
    assert [(r["age"], r["sex"]) for r in doc["rooms"]] == [("54", "M"), ("90+", "F")]


def test_room_scope_refuses_a_file_made_for_the_other_ward(tmp_path, monkeypatch):
    root = _stage(tmp_path, ["pat-0", "pat-1"])  # demo ids, run as a real ward first
    _run(monkeypatch, tmp_path, root, "--real-ward")
    with pytest.raises(SystemExit, match="another ward"):
        _run(monkeypatch, tmp_path, root, "--room", "2")


# ---- CodeRabbit PR #16: unknown stays unknown in the shared producers ----


def test_unit_summaries_keep_incomplete_coverage_unknown(tmp_path):
    """one stay whose current IMV state is unknown: the unit's ventilator count, the
    combined count, the yardstick and the strain index have no estimate, never a
    count that treats the unknown stay as 0"""
    train = scores(8).with_columns(
        pl.lit(False).alias(f"{t}_future") for t in (IMV, VASO, CRRT, WARD, STEP, DEATH)
    )
    train.write_parquet(tmp_path / "train_for_inference.parquet")
    df = scores(2, p={IMV: [0.4, 0.4]}, ids=["a", "b"])
    off = {"imv": False, "vasopressor": False, "crrt": False}
    clif = {"a": {**off, "imv": None}, "b": off}
    fc = aggregate.build_forecast(df, "m", clif=clif, baseline=tmp_path)
    vent = fc["resources"]["ventilator"]
    assert vent["available"] is False and vent["expected"] is None
    assert fc["resources"]["vasopressor"]["available"] is True  # fully observed
    ls = fc["life_support"]
    assert ls["expected_by"]["imv"]["available"] is False
    assert ls["expected_new_patients"]["available"] is False
    assert ls["expected_new_patients"]["p50"] is None
    assert fc["yardstick"] is None
    assert "ventilator" not in (fc.get("strain") or {"tasks": []})["tasks"]
    # the same unit, fully observed, keeps every count
    fc = aggregate.build_forecast(df, "m", clif={"a": off, "b": off}, baseline=tmp_path)
    assert fc["resources"]["ventilator"]["expected"] == 0.8
    assert fc["life_support"]["expected_new_patients"]["p50"] is not None


def test_room_combined_forecast_is_unknown_when_a_support_is_skipped():
    """IMV unknown, the other two at 0: not any_life_support 0 and level low"""
    p = {IMV: [0.4, 0.4], VASO: [0.0, 0.0], CRRT: [0.0, 0.0]}
    df = scores(2, p=p, ids=["a", "b"])
    off = {"imv": False, "vasopressor": False, "crrt": False}
    clif = {"a": {**off, "imv": None}, "b": off}
    cut = dt.datetime(2026, 11, 14, 7, tzinfo=dt.timezone.utc)
    a, b = rooms.room_entries(df, {"a": 1, "b": 2}, {}, cut, "now", clif=clif)
    assert a["skipped"]["imv"] is True
    assert a["any_life_support"] is None and a["level"] == "unavailable"
    assert b["any_life_support"] == 0.4 and b["level"] == "high"
    # a probe skipped in training, token path: the same rule
    df = scores(1, p={CRRT: [float("nan")]}, ids=["a"])
    (r,) = rooms.room_entries(df, {"a": 1}, {}, cut, "now")
    assert r["any_life_support"] is None and r["level"] == "unavailable"
    # check_first never lists a room without a combined forecast
    df = scores(1, p={IMV: [0.9], CRRT: [float("nan")]}, ids=["a"])
    assert aggregate.check_first(df, aggregate.patient_table(df), {"a": 1}) == []


def test_an_event_already_seen_before_the_cut_is_not_missing_data():
    """the probes give no score to a stay whose event was seen before the cut (the
    task rule). A vasopressor started and stopped earlier is "not a new start", not
    "no data": it must not make the unit's count or the room's forecast unknown."""
    df = scores(
        2, p={VASO: [float("nan"), 0.3]}, past={VASO: [True, False]}, ids=["a", "b"]
    ).with_columns(pl.lit(False).alias(aggregate.AT_CUT_COL["vasopressor"]))
    tab = aggregate.patient_table(df)
    assert tab["stopped"]["vasopressor"].tolist() == [True, False]
    assert not tab["skipped"]["vasopressor"].any()
    fc = aggregate.build_forecast(df, "m", beds=2)
    assert fc["resources"]["vasopressor"]["available"] is True
    assert fc["resources"]["vasopressor"]["expected"] == 0.3
    assert fc["life_support"]["expected_new_patients"]["p50"] is not None
    cut = dt.datetime(2026, 11, 14, 7, tzinfo=dt.timezone.utc)
    a, _ = rooms.room_entries(df, {"a": 1, "b": 2}, {}, cut, "now")
    assert a["p"]["vasopressor"] is None and a["skipped"]["vasopressor"] is False
    assert a["level"] in ("low", "medium", "high")


def test_a_patient_already_on_support_does_not_blank_the_combined_count():
    """CodeRabbit PR #16: known on a vasopressor, IMV unknown. That patient cannot be
    a NEW life-support patient, so the others' combined forecast stays available; the
    ventilator count itself is still unknown."""
    df = scores(2, p={IMV: [0.4, 0.4]}, ids=["a", "b"])
    off = {"imv": False, "vasopressor": False, "crrt": False}
    clif = {"a": {**off, "imv": None, "vasopressor": True}, "b": off}
    fc = aggregate.build_forecast(df, "m", clif=clif)
    ls = fc["life_support"]
    assert ls["expected_by"]["imv"]["available"] is False
    assert ls["expected_new_patients"]["p50"] is not None
    assert ls["expected_new_patients"]["expected"] == round(1 - 0.6 * 0.9 * 0.9, 2)
    # not on any support and IMV unknown: the combined count is unknown
    clif = {"a": {**off, "imv": None}, "b": off}
    ls = aggregate.build_forecast(df, "m", clif=clif)["life_support"]
    assert ls["expected_new_patients"]["p50"] is None

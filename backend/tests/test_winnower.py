"""winnower: derived labels are cut exactly like tokens (synthetic data only)"""

import datetime as dt

import polars as pl
import pytest
from omegaconf import OmegaConf

from icutwin.scoring.winnower import Winnower

LOOKUP = {"BOS": 1, "LAB_RES//potassium//L1": 2, "ADT//TRANSFER_IN//icu": 3, "EOS": 4}


def test_labels_split_past_future(tmp_path):
    t0 = dt.datetime(2020, 1, 1)
    h = lambda x: t0 + dt.timedelta(hours=x)
    rows = [  # (stay, hours, token, value)
        ("a", 0, "BOS", None),
        ("a", 1, "LAB_RES//potassium//L1", 7.0),  # hyperK before the 24h cut
        ("a", 30, "EOS", None),
        ("b", 0, "BOS", None),
        ("b", 2, "LAB_RES//potassium//L1", 6.0),  # below threshold
        ("b", 26, "LAB_RES//potassium//L1", 6.5),  # hyperK after the cut
        ("b", 27, "ADT//TRANSFER_IN//icu", None),
        ("b", 30, "EOS", None),
    ]
    pl.DataFrame(
        {
            "hospitalization_id": [r[0] for r in rows],
            "event_time": [h(r[1]) for r in rows],
            "token_id": [LOOKUP[r[2]] for r in rows],
            "value": [r[3] for r in rows],
            "position_id": list(range(len(rows))),
        },
        schema_overrides={"value": pl.Float64},
    ).write_parquet(tmp_path / "tokens_held_out.parquet")
    cfg = OmegaConf.create(
        {
            "outcome_tokens": ["ADT//TRANSFER_IN//icu"],
            "threshold": {"duration_s": 86400},
            "labels": {"LABEL//hyperk_init": [["LAB_RES//potassium//*", ">=", 6.5]]},
        }
    )
    df = Winnower(tmp_path, cfg, LOOKUP).prepare_winnowed_frame().collect()
    df = df.sort("hospitalization_id")
    assert df["LABEL//hyperk_init_past"].to_list() == [True, False]
    assert df["LABEL//hyperk_init_future"].to_list() == [False, True]
    assert df["ADT//TRANSFER_IN//icu_future"].to_list() == [False, True]
    assert not any(c.endswith("_hit") for c in df.columns)
    # a label must not change the cut: same past length as tokens
    assert df["tokens_past"].list.len().to_list() == [2, 2]

    # horizon 1h, counted from the last past token: b's 26h hit drops out
    cfg.horizon_after_threshold_s = 3600
    df = Winnower(tmp_path, cfg, LOOKUP).prepare_winnowed_frame().collect()
    assert df.sort("hospitalization_id")["LABEL//hyperk_init_future"].to_list() == [
        False,
        False,
    ]


def test_cut_24h_after_icu_arrival(tmp_path):
    """D3: cut 24 h after the first ICU token; drop stays that left the ICU first"""
    lookup = {
        "BOS": 1,
        "ADT//TRANSFER_IN//icu": 2,
        "ADT//TRANSFER_IN//ward": 3,
        "RESP//device_category//imv": 4,
        "EOS": 5,
    }
    t0 = dt.datetime(2020, 1, 1)
    h = lambda x: t0 + dt.timedelta(hours=x)
    rows = [  # (stay, hours, token)
        ("a", 0, "BOS"),  # ward 10 h, ICU at 10 h, cut at 34 h
        ("a", 10, "ADT//TRANSFER_IN//icu"),
        ("a", 30, "RESP//device_category//imv"),  # before the cut: past
        ("a", 40, "RESP//device_category//imv"),  # within 24 h after: future
        ("a", 70, "EOS"),  # past the 24 h window
        ("b", 0, "BOS"),  # ICU at 2 h, out to the ward at 20 h: not an ICU patient
        ("b", 2, "ADT//TRANSFER_IN//icu"),
        ("b", 20, "ADT//TRANSFER_IN//ward"),
        ("b", 50, "EOS"),
        ("c", 0, "BOS"),  # ICU at 1 h, ends at 12 h: never reaches the cut
        ("c", 1, "ADT//TRANSFER_IN//icu"),
        ("c", 12, "EOS"),
        ("d", 0, "BOS"),  # never in the ICU
        ("d", 40, "EOS"),
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
    cfg = OmegaConf.create(
        {
            "outcome_tokens": ["RESP//device_category//imv"],
            "threshold": {
                "duration_s": 86400,  # the shipped default; the new rule wins
                "after_first_occurrence": {
                    "token": "ADT//TRANSFER_IN//icu",
                    "duration_s": 86400,
                    "stay_until_cut": "ADT//TRANSFER_IN//*",
                },
            },
            "horizon_after_threshold_s": 86400,
        }
    )
    df = Winnower(tmp_path, cfg, lookup).prepare_winnowed_frame().collect()
    assert df["hospitalization_id"].to_list() == ["a"]
    assert df["tokens_past"].list.len().to_list() == [3]
    assert df["RESP//device_category//imv_past"].to_list() == [True]
    assert df["RESP//device_category//imv_future"].to_list() == [True]


def test_shipped_24h_override_is_accepted():
    # hardware pivot: examples/winnow_24h.yaml used to be refused as "unknown option"
    # (horizon_after_threshold_s was only a comment in winnowing.yaml), which stopped
    # t7-smoke and t7-build at the winnow step
    import pathlib

    from icutwin.common import merge_config

    cfg = merge_config(
        "winnowing.yaml",
        pathlib.Path(__file__).parent.parent / "examples/winnow_24h.yaml",
    )
    assert cfg.horizon_after_threshold_s == 86400
    assert cfg.threshold.after_first_occurrence.token == "ADT//TRANSFER_IN//icu"
    assert merge_config("winnowing.yaml", None).horizon_after_threshold_s is None


def _after_icu_cfg(offset_s):
    return OmegaConf.create(
        {
            "outcome_tokens": ["RESP//device_category//imv"],
            "threshold": {
                "after_first_occurrence": {
                    "token": "ADT//TRANSFER_IN//icu",
                    "duration_s": 86400,
                    "offset_s": offset_s,
                }
            },
            "horizon_after_threshold_s": 86400,
        }
    )


def test_offset_cannot_put_the_cut_before_icu_arrival(tmp_path):
    lookup = {"BOS": 1, "ADT//TRANSFER_IN//icu": 2, "RESP//device_category//imv": 3}
    t0 = dt.datetime(2020, 1, 1)
    pl.DataFrame(
        {
            "hospitalization_id": ["a"] * 3,
            "event_time": [t0 + dt.timedelta(hours=x) for x in (0, 2, 60)],
            "token_id": [1, 2, 3],
            "value": [None] * 3,
            "position_id": [0, 1, 2],
        },
        schema_overrides={"value": pl.Float64},
    ).write_parquet(tmp_path / "tokens_held_out.parquet")
    for bad in (-86400, -90000):  # cut at, and 1 h before, ICU arrival
        with pytest.raises(ValueError, match="after ICU arrival"):
            Winnower(tmp_path, _after_icu_cfg(bad), lookup).prepare_winnowed_frame()
    ok = Winnower(tmp_path, _after_icu_cfg(-82800), lookup)  # cut 1 h after arrival
    df = ok.prepare_winnowed_frame().collect()
    assert df["cut_s"].to_list() == [2 * 3600 + 3600]


def test_counts_only_keeps_outcome_rates_out_of_the_log(tmp_path, caplog):
    """CodeRabbit PR #16: a small ward's outcome rates are clinical values; the
    workflows that winnow one ask for counts only"""
    import yaml
    from typer.testing import CliRunner

    from icutwin.common import logger
    from icutwin.scoring import winnower

    lookup = {"BOS": 1, "RESP//device_category//imv": 2, "EOS": 3}
    pl.DataFrame(
        {
            "hospitalization_id": ["a", "a", "a", "b", "b"],
            "token_id": [1, 2, 3, 1, 3],
            "event_time": [0, 100000, 200000, 0, 200000],
            "value": [None] * 5,
            "position_id": [0, 1, 2, 0, 1],
        },
        schema_overrides={"event_time": pl.Datetime("us"), "value": pl.Float64},
    ).write_parquet(tmp_path / "tokens_held_out.parquet")
    for split in ("train", "tuning"):
        pl.DataFrame({"x": [1]}).write_parquet(tmp_path / f"tokens_{split}.parquet")
    (tmp_path / "vocab.yaml").write_text(yaml.safe_dump({"lookup": lookup}))
    cfg = tmp_path / "w.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "outcome_tokens": ["RESP//device_category//imv"],
                "threshold": {"duration_s": 1},
                "horizon_after_threshold_s": 86400,
                "splits": ["held_out"],
            }
        )
    )
    level = logger.level  # another test may have quietened the shared logger
    logger.setLevel("INFO")
    logger.addHandler(caplog.handler)
    try:
        for flag, rates in (([], True), (["--counts-only"], False)):
            caplog.clear()
            args = [str(tmp_path), "-c", str(cfg), *flag]
            done = CliRunner().invoke(winnower.app, args)
            assert done.exit_code == 0, done.output
            assert "held_out: " in caplog.text and "stays" in caplog.text
            assert ("_future" in caplog.text) == rates
            assert ("_past" in caplog.text) == rates
    finally:
        logger.removeHandler(caplog.handler)
        logger.setLevel(level)

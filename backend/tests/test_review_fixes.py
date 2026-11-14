"""Findings from the pull-request review (PRs 3 and 4), each pinned by a test.
Synthetic frames only."""

import json

import numpy as np
import polars as pl
import pytest
import test_lookahead as tl
from omegaconf import OmegaConf

from app import aggregate
from icutwin.scoring import rep_based
from tests.test_lookahead import demo_ward  # noqa: F401  (fixture)

WARD, STEP, IMV = tl.WARD, tl.STEP, tl.IMV


def _fit(train, home, probes):
    cfg = OmegaConf.create({"score": {"target_tokens": ["*"]}})
    rep_based.RepBasedScorer(
        train, {}, home, cfg, "logistic", save_probes=probes
    ).save_all(verbose=False)
    return pl.read_parquet(train / f"scores-rep-based-{tl.MODEL}.parquet").sort(
        "hospitalization_id"
    )


def test_features_are_paired_with_labels_by_stay_not_by_row(tmp_path):
    """rep_based.py: a partial extraction moves stays to the end of the features
    file; fitting must still give each stay its own vector"""
    home = tl._model_dir(tmp_path)
    train, probes = tl._fit_probes(tmp_path, home)
    want = _fit(train, home, probes)
    for split in ("train", "held_out"):
        f = train / f"features-{split}-{tl.MODEL}.parquet"
        pl.read_parquet(f).reverse().write_parquet(f)  # same rows, another order
    got = _fit(train, home, tmp_path / "probes2")
    col = f"{IMV}_rep_score"
    assert np.allclose(want[col].to_numpy(), got[col].to_numpy())
    # a labelled stay without a vector is refused, not shifted onto its neighbour
    f = train / f"features-train-{tl.MODEL}.parquet"
    pl.read_parquet(f).head(100).write_parquet(f)
    with pytest.raises(ValueError, match="20 train stays have no features"):
        _fit(train, home, tmp_path / "probes3")


def test_a_ward_stay_before_the_icu_does_not_remove_the_leaving_forecast(tmp_path):
    """rep_based.py / aggregate.py: a patient who came to the ICU from a ward has
    `ADT//TRANSFER_IN//ward_past` true and can still leave for a ward"""
    home = tl._model_dir(tmp_path)
    train, probes = tl._fit_probes(tmp_path, home)
    for split in ("train", "held_out"):  # half of the stays came from a ward
        f = train / f"{split}_for_inference.parquet"
        lab = pl.read_parquet(f)
        came = pl.Series(np.arange(lab.height) % 2 == 0)
        lab.with_columns(came.alias(f"{WARD}_past")).write_parquet(f)
    scores = _fit(train, home, probes)
    assert scores[f"{WARD}_rep_score"].is_finite().all()  # every stay is scored
    manifest = json.loads((probes / "manifest.json").read_text())
    assert manifest["tokens"][WARD]["n_train"] == 120  # and every stay is fit on
    ids = [f"held_out{i}" for i in range(6)]
    stage = tl._ward_stage(tmp_path, train, ids, 86500.0)
    out = pl.read_parquet(rep_based.apply_probes(stage, home, probes))
    assert out[f"{WARD}_rep_score"].is_finite().all()
    # the board's side: the past transfer is not "already left"
    df = tl.scores(
        4,
        p={WARD: [0.5, 0.5, 0.2, 0.2], STEP: [0.1, 0.1, 0.1, 0.1]},
        past={WARD: [True, False, True, False]},
    )
    assert aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)[
        "icu_departure"
    ].tolist() == pytest.approx([0.6, 0.6, 0.3, 0.3])
    tab = aggregate.patient_table(df)
    assert tab["p"]["icu_departure"].tolist() == pytest.approx([0.6, 0.6, 0.3, 0.3])
    assert not tab["skipped"]["icu_departure"].any()
    # a support is different: started before and still running is not a new start
    df = tl.scores(2, p={IMV: [0.5, 0.5]}, past={IMV: [True, False]})
    assert aggregate.unit_probs(df, "_rep_score", aggregate.RESOURCES_REP)[
        "ventilator"
    ].tolist() == [0.0, 0.5]


def test_features_from_other_weights_under_the_same_name_are_refused(tmp_path):
    """extractor.py: retraining under the same model name must not let the old
    vectors through; each feature row carries the checksum of its weights"""
    from icutwin.scoring.extractor import merge_features

    home = tl._model_dir(tmp_path)
    train, probes = tl._fit_probes(tmp_path, home)
    ids = [f"held_out{i}" for i in range(4)]
    stage = tl._ward_stage(tmp_path, train, ids, 86500.0)
    rep_based.apply_probes(stage, home, probes)  # same weights: fine
    f = stage / f"features-held_out-{tl.MODEL}.parquet"
    now = rep_based.weights_digest(home)
    assert pl.read_parquet(f)["weights_sha256"].unique().to_list() == [now]
    # retrained: new weights in the same folder, probes refit on new train features
    tl._model_dir(tmp_path, weights=b"w2")
    new = rep_based.weights_digest(home)
    assert new != now
    for split in ("train", "held_out"):
        t = train / f"features-{split}-{tl.MODEL}.parquet"
        pl.read_parquet(t).with_columns(weights_sha256=pl.lit(new)).write_parquet(t)
    _fit(train, home, probes)
    with pytest.raises(rep_based.StaleFeatures, match="other weights"):
        rep_based.apply_probes(stage, home, probes)  # the stage vectors are old
    # one room re-extracted with the new weights: only that room passes
    one = (
        pl.read_parquet(f)
        .filter(pl.col("hospitalization_id") == "held_out1")
        .with_columns(weights_sha256=pl.lit(new))
    )
    merge_features(f, one, ["held_out1"]).write_parquet(f)
    rep_based.apply_probes(stage, home, probes, ["held_out1"])
    with pytest.raises(rep_based.StaleFeatures, match="other weights"):
        rep_based.apply_probes(stage, home, probes, ["held_out2"])
    # fitting on train vectors of other weights is refused too
    t = train / f"features-train-{tl.MODEL}.parquet"
    pl.read_parquet(t).with_columns(weights_sha256=pl.lit(now)).write_parquet(t)
    with pytest.raises(rep_based.StaleFeatures, match="other weights"):
        _fit(train, home, tmp_path / "p4")
    # a file from before the checksum was stored
    pl.read_parquet(f).drop("weights_sha256").write_parquet(f)
    with pytest.raises(rep_based.StaleFeatures, match="other weights"):
        rep_based.apply_probes(stage, home, probes, ["held_out1"])

"""Probe save/apply: the stage ward is scored with probes fit on training stays."""

import json

import numpy as np
import polars as pl
import pytest
from omegaconf import OmegaConf

from icutwin.scoring import rep_based

TASK = "LABEL//pressor_init"
RARE = "LABEL//crrt_init"
MODEL = "mdl-test"


def _split(root, split, n, rng, with_labels):
    x = rng.normal(size=(n, 6)).astype(np.float32)
    ids = [f"{split}{i}" for i in range(n)]
    pl.DataFrame({"hospitalization_id": ids, "features": list(x)}).write_parquet(
        root / f"features-{split}-{MODEL}.parquet"
    )
    y = (x[:, 0] + 0.3 * rng.normal(size=n) > 0) if with_labels else np.zeros(n, bool)
    pl.DataFrame(
        {
            "hospitalization_id": ids,
            f"{TASK}_past": np.zeros(n, bool),
            f"{TASK}_future": y,
            f"{RARE}_past": np.zeros(n, bool),
            f"{RARE}_future": np.zeros(n, bool),  # one class: probe skipped
        }
    ).write_parquet(root / f"{split}_for_inference.parquet")
    return x


@pytest.fixture
def cohorts(tmp_path):
    rng = np.random.default_rng(0)
    train, demo = tmp_path / "train", tmp_path / "demo"
    train.mkdir(), demo.mkdir()
    _split(train, "train", 200, rng, True)
    _split(train, "held_out", 40, rng, True)
    xd = _split(demo, "held_out", 30, rng, False)
    return train, demo, xd


def test_probes_saved_then_applied_without_refit(cohorts, tmp_path):
    train, demo, xd = cohorts
    cfg = OmegaConf.create({"score": {"target_tokens": ["LABEL//*"]}})
    probes = tmp_path / "probes"
    rep_based.RepBasedScorer(
        train, {}, MODEL, cfg, "logistic", save_probes=probes
    ).save_all(verbose=False)
    manifest = json.loads((probes / "manifest.json").read_text())
    assert manifest["features"] == 6 and manifest["tokens"][RARE]["file"] is None
    assert (probes / rep_based.probe_file(TASK)).is_file()

    keep = [f"held_out{i}" for i in range(10)]
    out = rep_based.apply_probes(demo, MODEL, probes, stay_ids=keep)
    df = pl.read_parquet(out)
    assert df.height == 10 and set(df["hospitalization_id"]) == set(keep)
    p = df[f"{TASK}_rep_score"].to_numpy()
    assert ((p > 0) & (p < 1)).all()
    assert np.isnan(df[f"{RARE}_rep_score"].to_numpy()).all()
    # same numbers as predicting directly with the saved probe: nothing was refit
    import joblib

    mdl = joblib.load(probes / rep_based.probe_file(TASK))
    ids = [int(i.removeprefix("held_out")) for i in df["hospitalization_id"]]
    np.testing.assert_allclose(p, mdl.predict_proba(xd[ids])[:, 1], atol=1e-6)


def test_apply_refuses_probes_from_another_model(cohorts, tmp_path):
    train, demo, _ = cohorts
    cfg = OmegaConf.create({"score": {"target_tokens": ["LABEL//*"]}})
    probes = tmp_path / "probes"
    rep_based.RepBasedScorer(
        train, {}, MODEL, cfg, "logistic", save_probes=probes
    ).save_all(verbose=False)
    with pytest.raises(ValueError, match="refit"):
        rep_based.apply_probes(demo, "mdl-other", probes)


def _fit_with_weights(train, tmp_path, weights):
    home = tmp_path / "models" / MODEL
    home.mkdir(parents=True, exist_ok=True)
    (home / "model.safetensors").write_bytes(weights)
    cfg = OmegaConf.create({"score": {"target_tokens": ["LABEL//*"]}})
    probes = tmp_path / "probes"
    rep_based.RepBasedScorer(
        train, {}, home, cfg, "logistic", save_probes=probes
    ).save_all(verbose=False)
    return home, probes


def test_probes_are_tied_to_the_weights_not_the_folder_name(cohorts, tmp_path):
    train, demo, _ = cohorts
    home, probes = _fit_with_weights(train, tmp_path, b"weights-v1")
    manifest = json.loads((probes / "manifest.json").read_text())
    assert manifest["weights_sha256"] == rep_based.weights_digest(home)
    rep_based.apply_probes(demo, home, probes)  # same weights: fine
    (home / "model.safetensors").write_bytes(b"weights-v2")  # same name, new weights
    with pytest.raises(ValueError, match="other weights"):
        rep_based.apply_probes(demo, home, probes)


def test_probes_without_a_recorded_checksum_are_refused(cohorts, tmp_path):
    train, demo, _ = cohorts
    home, probes = _fit_with_weights(train, tmp_path, b"weights-v1")
    m = json.loads((probes / "manifest.json").read_text())
    del m["weights_sha256"]  # probes made before the checksum existed
    (probes / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(ValueError, match="refit"):
        rep_based.apply_probes(demo, home, probes)


def test_scores_file_provenance(cohorts, tmp_path):
    train, demo, _ = cohorts
    home, probes = _fit_with_weights(train, tmp_path, b"weights-v1")
    out = rep_based.apply_probes(demo, home, probes)
    rep_based.verify_scores(out, home)  # made with these weights
    rep_based.scores_meta_path(out).unlink()
    with pytest.raises(ValueError, match="not made by"):
        rep_based.verify_scores(out, home)
    rep_based.write_scores_meta(out, home)
    (home / "model.safetensors").write_bytes(b"weights-v2")
    with pytest.raises(ValueError, match="other weights"):
        rep_based.verify_scores(out, home)

"""Probe save/apply: the stage ward is scored with main's probe-<model>.joblib,
fit on training stays and never refit."""

import pathlib

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


CFG = {"score": {"target_tokens": ["LABEL//*"]}}


def _fit(train, home):
    cfg = OmegaConf.create(CFG)
    rep_based.RepBasedScorer(train, {}, home, cfg, "logistic").save_all(n_samples=20)
    return train / f"probe-{pathlib.Path(home).name}.joblib"


def test_probes_saved_then_applied_without_refit(cohorts):
    train, demo, xd = cohorts
    probe = _fit(train, MODEL)
    import joblib

    saved = joblib.load(probe)
    assert TASK in saved and RARE not in saved  # one class in train: no probe

    keep = [f"held_out{i}" for i in range(10)]
    out = rep_based.apply_probes(demo, MODEL, probe, stay_ids=keep)
    df = pl.read_parquet(out)
    assert df.height == 10 and set(df["hospitalization_id"]) == set(keep)
    p = df[f"{TASK}_rep_score"].to_numpy()
    assert ((p > 0) & (p < 1)).all()
    # same numbers as predicting directly with the saved probe: nothing was refit
    ids = [int(i.removeprefix("held_out")) for i in df["hospitalization_id"]]
    np.testing.assert_allclose(p, saved[TASK].predict_proba(xd[ids])[:, 1], atol=1e-6)


def _home(tmp_path, weights):
    home = tmp_path / "models" / MODEL
    home.mkdir(parents=True, exist_ok=True)
    (home / "model.safetensors").write_bytes(weights)
    return home


def test_probes_are_tied_to_the_weights_not_the_folder_name(cohorts, tmp_path):
    train, demo, _ = cohorts
    home = _home(tmp_path, b"weights-v1")
    probe = _fit(train, home)
    rep_based.apply_probes(demo, home, probe)  # same weights: fine
    (home / "model.safetensors").write_bytes(b"weights-v2")  # same name, new weights
    with pytest.raises(ValueError, match="other weights"):
        rep_based.apply_probes(demo, home, probe)


def test_probes_without_a_recorded_checksum_are_refused(cohorts, tmp_path):
    train, demo, _ = cohorts
    home = _home(tmp_path, b"weights-v1")
    probe = _fit(train, home)
    rep_based.scores_meta_path(probe).unlink()  # a probe made before the checksum
    with pytest.raises(ValueError, match="no probe-"):
        rep_based.apply_probes(demo, home, probe)


def test_scores_file_provenance(cohorts, tmp_path):
    train, demo, _ = cohorts
    home = _home(tmp_path, b"weights-v1")
    out = rep_based.apply_probes(demo, home, _fit(train, home))
    rep_based.verify_scores(out, home)  # made with these weights
    rep_based.scores_meta_path(out).unlink()
    with pytest.raises(ValueError, match="not made for"):
        rep_based.verify_scores(out, home)
    rep_based.write_scores_meta(out, home)
    (home / "model.safetensors").write_bytes(b"weights-v2")
    with pytest.raises(ValueError, match="other weights"):
        rep_based.verify_scores(out, home)

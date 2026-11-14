"""rep-based probe: no probability once the event happened; saved probe reloads;
metrics file has the train and held-out sides (synthetic data only)"""

import json

import numpy as np
import polars as pl
from omegaconf import OmegaConf

from icutwin.scoring.rep_based import RepBasedScorer

T = "RESP//device_category//imv"


def write_split(root, split, x, past, future):
    ids = [f"{split}{i}" for i in range(len(x))]
    pl.DataFrame({"hospitalization_id": ids, "features": list(x)}).write_parquet(
        root / f"features-{split}-mdl-x.parquet"
    )
    pl.DataFrame(
        {"hospitalization_id": ids, f"{T}_past": past, f"{T}_future": future}
    ).write_parquet(root / f"{split}_for_inference.parquet")


def test_probe_masks_past_and_reloads(tmp_path):
    rng = np.random.default_rng(0)
    x = rng.normal(size=(200, 4)).astype(np.float16)
    y = x[:, 0] > 0
    write_split(tmp_path, "train", x, [False] * 190 + [True] * 10, y.tolist())
    past = [True] + [False] * 49
    write_split(tmp_path, "held_out", x[:50], past, y[:50].tolist())
    cfg = OmegaConf.create({"score": {"target_tokens": [T]}})
    lookup = {T: 1}

    fit = RepBasedScorer(tmp_path, lookup, "mdl-x", cfg, "logistic")
    fit.save_all(n_samples=50)
    scores = pl.read_parquet(tmp_path / "scores-rep-based-mdl-x.parquet")[
        f"{T}_rep_score"
    ].to_numpy()
    assert np.isnan(scores[0])  # already on the ventilator before the cut
    assert not np.isnan(scores[1:]).any()
    assert ((scores[1:] > 0.5) == y[1:50]).mean() > 0.9

    probe = tmp_path / "probe-mdl-x.joblib"
    assert probe.is_file()
    (tmp_path / "features-train-mdl-x.parquet").unlink()  # inference needs no train
    again = RepBasedScorer(tmp_path, lookup, "mdl-x", cfg, "logistic", probe)
    np.testing.assert_array_equal(again.score()[f"{T}_rep_score"], scores)

    m = json.loads((tmp_path / "metrics-rep-based-mdl-x.json").read_text())["tasks"][T]
    assert (m["n_train"], m["n_train_pos"]) == (190, int(y[:190].sum()))
    assert m["n"] == 49 and m["roc_auc"] > 0.9  # held-out row 0 already happened
    assert m["roc_auc_ci"][0] <= m["roc_auc"] <= m["roc_auc_ci"][1]


def test_cv_probe_records_c_and_cv_auroc(tmp_path):
    rng = np.random.default_rng(1)
    x = rng.normal(size=(300, 4)).astype(np.float16)
    y = (x[:, 0] + rng.normal(size=300) > 0).tolist()
    for split in ("train", "held_out"):
        write_split(tmp_path, split, x, [False] * 300, y)
    cfg = OmegaConf.create({"score": {"target_tokens": [T]}})
    RepBasedScorer(tmp_path, {T: 1}, "mdl-x", cfg, "logistic-CV-z").save_all(10)
    m = json.loads((tmp_path / "metrics-rep-based-mdl-x.json").read_text())["tasks"][T]
    assert m["C"] > 0 and 0.6 < m["cv_roc_auc"] <= 1

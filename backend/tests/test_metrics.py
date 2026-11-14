"""summarize_preds: runs on a materialized frame and reports PR-AUC too"""

import numpy as np
import polars as pl

from icutwin.scoring.metrics import summarize_preds


class Capture:
    def __init__(self):
        self.lines = []

    def info(self, msg, *a, **k):
        self.lines.append(str(msg))

    def warning(self, msg, *a, **k):
        self.lines.append(str(msg))


def test_summarize_preds_logs_all_three_metrics_on_a_dataframe():
    df = pl.DataFrame(
        {
            "X_past": [False, False, True, False],
            "X_future": [False, True, False, True],
            "X_rep_score": [0.1, 0.9, 0.5, 0.8],
            "X_reach_score": [0.2, 0.8, 0.4, 0.7],
        }
    )
    log = Capture()
    summarize_preds(log, df, ["X"], n_samples=50)
    text = "\n".join(log.lines)
    for metric in ("roc_auc", "pr_auc", "brier"):
        assert text.count(metric) >= 2  # rep and reach
    assert "method='rep'" in text and "method='reach'" in text
    assert "method='mc'" not in text and "method='scope'" not in text


def test_a_past_outcome_is_skipped_for_its_own_method():
    df = pl.DataFrame(
        {
            "X_past": [True, True, True],
            "X_future": [False, False, False],
            "X_rep_score": [0.1, 0.2, 0.3],
        }
    )
    log = Capture()
    summarize_preds(log, df, ["X"], n_samples=10)  # no valid rows: no crash
    assert not any("roc_auc" in line for line in log.lines)


def test_scope_scores_above_one_do_not_crash_and_skip_only_brier():
    # SCOPE is a sum of per-step probabilities (an expected count), so it can
    # exceed 1; Brier needs probabilities, but AUROC / AUPRC are still valid
    df = pl.DataFrame(
        {
            "X_past": [False] * 6,
            "X_future": [False, True, False, True, False, True],
            "X_scope_score": [0.2, 1.7, 0.4, 2.3, 0.1, 0.9],
            "X_reach_score": [0.2, 0.8, 0.4, 0.7, 0.1, 0.9],
        }
    )
    log = Capture()
    summarize_preds(log, df, ["X"], n_samples=50)
    text = "\n".join(log.lines)
    assert "method='scope'" in text and "method='reach'" in text
    assert text.count("roc_auc") >= 2
    assert text.count("brier") >= 2  # reach reports a real one, scope reports nan


def test_returns_point_estimates_cis_and_calibration():
    rng = np.random.default_rng(0)
    y = rng.random(400) < 0.3
    df = pl.DataFrame(
        {
            "X_past": [True] * 20 + [False] * 380,
            "X_future": y,
            "X_rep_score": np.clip(y * 0.4 + rng.random(400) * 0.6, 0, 1),
        }
    )
    m = summarize_preds(Capture(), df, ["X"], n_samples=50)["X"]["rep"]
    assert m["n"] == 380 and m["n_pos"] == int(y[20:].sum())
    for k in ("roc_auc", "pr_auc", "brier"):
        lo, hi = m[f"{k}_ci"]
        assert lo <= m[k] <= hi
    assert sum(b["n"] for b in m["calibration"]) == 380
    assert len(m["calibration"]) == 10


def test_one_class_is_skipped_not_crashed():
    df = pl.DataFrame(
        {"X_past": [False] * 4, "X_future": [False] * 4, "X_rep_score": [0.1] * 4}
    )
    assert summarize_preds(Capture(), df, ["X"], n_samples=10) == {}

"""summarize_preds: runs on a materialized frame and reports PR-AUC too"""

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

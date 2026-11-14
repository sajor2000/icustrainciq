#!/usr/bin/env python3

"""
bootstrapped AUROC / AUPRC / Brier intervals for the scorers' predictions

Based on cotorra's metrics (github.com/bbj-lab/cotorra); see ACKNOWLEDGMENTS.md.
"""

import collections
import typing
import warnings

import joblib as jl
import numpy as np
import polars as pl
from sklearn import metrics as skl_mets

Generator: typing.TypeAlias = np.random._generator.Generator


def pr_auc_score(y_true: np.ndarray, y_score: np.ndarray):
    precs, recs, *_ = skl_mets.precision_recall_curve(
        y_true, np.round(y_score, decimals=4), drop_intermediate=True
    )
    return skl_mets.auc(recs, precs)


METRICS = {
    "roc_auc": skl_mets.roc_auc_score,
    "pr_auc": pr_auc_score,
    "brier": skl_mets.brier_score_loss,
}


def runnable(y_score: np.ndarray, metrics) -> tuple:
    """Brier needs probabilities; SCOPE is a sum of them (an expected count) and
    can exceed 1, so Brier is left out there while AUROC / AUPRC still run"""
    probs = np.nanmin(y_score) >= 0 and np.nanmax(y_score) <= 1
    return tuple(m for m in metrics if m != "brier" or probs)


def calibration(y_true: np.ndarray, y_score: np.ndarray, n_bins: int = 10) -> list:
    """D7: of the patients given about this risk (risk deciles), how many had the
    event"""
    edges = np.quantile(y_score, np.linspace(0, 1, n_bins + 1)[1:-1])
    b = np.searchsorted(edges, y_score, side="right")
    return [
        {
            "n": int((b == i).sum()),
            "mean_score": float(y_score[b == i].mean()),
            "event_rate": float(y_true[b == i].mean()),
        }
        for i in np.unique(b)
    ]


def bootstrap_ci(
    y_true: np.ndarray,
    y_score: np.ndarray,
    *,
    n_samples: int = 10_000,
    alpha: float = 0.05,
    rng: Generator = np.random.default_rng(seed=42),
    metrics: collections.abc.Sequence[typing.Literal["roc_auc", "pr_auc", "brier"]] = (
        "roc_auc",
        "pr_auc",
        "brier",
    ),
    n_jobs: int = -1,
    stratified: bool = False,
) -> dict[str, np.ndarray]:
    """
    Calculates a bootstrapped percentile interval for objectives `objs` as
    described in §13.3 of Efron & Tibshirani's "An Introduction to the Bootstrap"
    (Chapman & Hall, Boca Raton, 1993), ignoring variance due to model-fitting
    (i.e. this measures variability in the test-set alone);
    """

    run = runnable(y_score, metrics)

    def get_scores_i(rng_i: Generator) -> dict[str, float]:
        warnings.filterwarnings("ignore")
        if stratified:
            pos = np.flatnonzero(y_true.astype(int))
            neg = np.flatnonzero(1 - (y_true).astype(int))
            samp_pos = rng_i.choice(pos, size=len(pos), replace=True)
            samp_neg = rng_i.choice(neg, size=len(neg), replace=True)
            samp_i = rng_i.permutation(np.concatenate([samp_pos, samp_neg]))
        else:
            samp_i = rng_i.choice(len(y_true), size=len(y_true), replace=True)
        return {m: METRICS[m](y_true[samp_i], y_score[samp_i]) for m in run}

    with jl.Parallel(n_jobs=n_jobs) as par:
        scores = par(jl.delayed(get_scores_i)(rng_i) for rng_i in rng.spawn(n_samples))

    q = [alpha / 2, 1 - (alpha / 2)]
    return {
        m: (
            np.full(2, np.nan)
            if m not in run
            else np.nanquantile([s[m] for s in scores], q=q)
        )
        for m in metrics
    }


def summarize_preds(logger, df_res, target_tokens, n_samples: int = 10_000) -> dict:
    """logs and returns, per task and method, on the scoreable rows (event not
    already seen before the cut): n, positives, prevalence, AUROC / AUPRC / Brier
    with bootstrap 95% CIs, and calibration by risk decile"""
    cols = df_res.collect_schema().names()
    out = {}
    for tt in target_tokens:
        logger.info("=" * 42)
        logger.info(f"{tt=}")
        for method in ("mc", "scope", "reach", "rep"):
            if f"{tt}_{method}_score" in cols:
                logger.info(f"{method=}")
                y_qual, y_true, y_score = (
                    df_res.lazy()
                    .select(
                        ~pl.col(f"{tt}_past"), f"{tt}_future", f"{tt}_{method}_score"
                    )
                    .collect()
                    .to_numpy()
                    .T
                )
                ok = y_qual.astype(bool)
                finite = np.isfinite(y_score.astype(float))
                if (nf := np.sum(ok & ~finite)) > 0:
                    # no estimate is not a zero-risk estimate: leave those rows out
                    # (a task with no fitted probe then has no rows and is skipped)
                    logger.warning(
                        f"{nf} non-finite {method} estimates for {tt}: left out."
                    )
                    ok = ok & finite
                if len(np.unique(y_true[ok])) < 2:
                    logger.warning(
                        f"{ok.sum()} scoreable {method} rows for {tt}, "
                        "fewer than two classes; skipped"
                    )
                    continue
                y_true = y_true[ok].astype(int)
                y_score = y_score[ok].astype(float)
                v_rare = y_true.mean().item() < 0.001
                if v_rare:
                    logger.warning("using stratified sampling due to rarity")
                ci = bootstrap_ci(
                    y_true, y_score, stratified=v_rare, n_samples=n_samples
                )
                run = runnable(y_score, ci)
                res = {
                    "n": int(ok.sum()),
                    "n_pos": int(y_true.sum()),
                    "prevalence": float(y_true.mean()),
                }
                for k, v in ci.items():
                    est = float(METRICS[k](y_true, y_score)) if k in run else np.nan
                    res[k], res[f"{k}_ci"] = est, v.round(4).tolist()
                    logger.info(f"{k:<7}: {est:.3f} {v.round(3)}")
                res["calibration"] = calibration(y_true, y_score)
                out.setdefault(tt, {})[method] = res
    return out

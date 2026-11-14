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

    # Brier needs probabilities; SCOPE is a sum of them (an expected count) and
    # can exceed 1, so it is reported as nan there while AUROC / AUPRC still run
    no_brier = "brier" in metrics and (np.nanmin(y_score) < 0 or np.nanmax(y_score) > 1)
    run = tuple(m for m in metrics if not (m == "brier" and no_brier))

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
        yti, ysi = y_true[samp_i], y_score[samp_i]
        ret = dict()
        if "roc_auc" in run:
            ret["roc_auc"] = skl_mets.roc_auc_score(yti, ysi)
        if "pr_auc" in run:
            ret["pr_auc"] = pr_auc_score(yti, ysi)
        if "brier" in run:
            ret["brier"] = skl_mets.brier_score_loss(yti, ysi)
        return ret

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


def summarize_preds(logger, df_res, target_tokens, n_samples: int = 10_000):
    cols = df_res.collect_schema().names()
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
                if (nf := np.sum(~np.isfinite(y_score[y_qual.astype(bool)]))) > 0:
                    logger.warning(f"{nf} non-finite {method} estimates for {tt}.")
                if (ok := y_qual.astype(bool)).sum() < 2:
                    logger.warning(
                        f"{ok.sum()} scoreable {method} rows for {tt}; skipped"
                    )
                    continue
                v_rare = y_true[ok].mean().item() < 0.001
                if v_rare:
                    logger.warning("using stratified sampling due to rarity")
                for k, v in bootstrap_ci(
                    y_true[ok],
                    np.nan_to_num(y_score)[ok],
                    stratified=v_rare,
                    n_samples=n_samples,
                ).items():
                    logger.info("{k:<7}: {v}".format(k=k, v=v.round(3)))

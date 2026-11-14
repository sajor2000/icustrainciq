#!/usr/bin/env python3

"""
representation-based predictions on held-out data: a logistic-regression probe
on icutwin-extract features, fit on train; writes scores-rep-based-<model>.parquet,
probe-<model>.joblib and metrics-rep-based-<model>.json (held-out AUROC / AUPRC /
Brier with bootstrap 95% CIs, calibration, train counts). The probe file gets a
probe-<model>.meta.json beside it with the model's weights checksum, so
`apply_probes` (the board's stage ward) refuses probes fit on other weights.

Based on cotorra's rep-based scorer (github.com/bbj-lab/cotorra); see
ACKNOWLEDGMENTS.md.
"""

import enum
import fnmatch
import hashlib
import json
import pathlib
import time
from typing import Annotated, Optional

import joblib
import numpy as np
import polars as pl
import polars.selectors as cs
import sklearn as skl
import sklearn.linear_model  # noqa: F401
import sklearn.pipeline  # noqa: F401
import sklearn.preprocessing  # noqa: F401
import typer

from icutwin.common import load_vocab, logger, merge_config
from icutwin.scoring.metrics import summarize_preds


class EstimatorType(str, enum.Enum):
    logistic = "logistic"
    logistic_z = "logistic-z"
    logistic_cv = "logistic-CV"
    logistic_cv_z = "logistic-CV-z"


SPLITS = ("train", "tuning", "held_out")
CUT_COLS = ("last_valid", "cut_s")  # a stay's cut, stored by the winnower and extractor


def weights_digest(model_home) -> str | None:
    """sha256 over the model's weight files (and config.json): ties probes, features
    and scores to the weights, not to a folder name. None when no weights are found."""
    home = pathlib.Path(model_home).expanduser()
    files = sorted(home.glob("*.safetensors")) or sorted(
        home.glob("pytorch_model*.bin")
    )
    if not files:
        return None
    h = hashlib.sha256()
    for f in [
        *files,
        *([home / "config.json"] if (home / "config.json").is_file() else []),
    ]:
        h.update(f.name.encode())
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def scores_meta_path(path: pathlib.Path) -> pathlib.Path:
    return path.with_suffix(".meta.json")


def write_scores_meta(path: pathlib.Path, model_home) -> None:
    """provenance beside a scores or probe file: which weights it was made with"""
    scores_meta_path(path).write_text(
        json.dumps(
            {
                "model": pathlib.Path(model_home).name,
                "weights_sha256": weights_digest(model_home),
            }
        )
    )


def verify_scores(path: pathlib.Path, model_home) -> None:
    """refuse a scores or probe file that was not made with this model's weights"""
    meta = scores_meta_path(path)
    if not meta.is_file():
        raise ValueError(
            f"{path.name} has no {meta.name}: it was not made for this model; "
            "run icutwin-rep-score again"
        )
    got = json.loads(meta.read_text())
    if got.get("weights_sha256") != weights_digest(model_home):
        raise ValueError(
            f"{path.name} was made with other weights than {model_home}: "
            "run icutwin-rep-score again"
        )


class StaleFeatures(ValueError):
    """the features were extracted at another cut than the labels now have"""


def check_features_current(root, model_name: str, stay_ids=None) -> None:
    """refuse features whose stored cut differs from the winnowed labels' cut.

    icutwin-extract stores each row's cut (`last_valid`, and `cut_s` when the winnower
    wrote it); a demo-clock move or a new threshold changes the labels' cut, and a
    one-room re-extract leaves the other rows at the old cut. Only `stay_ids` are
    checked when given. Label files without a cut column (old) are not checked."""
    root = pathlib.Path(root)
    bad = 0
    for s in SPLITS:
        f, lab = (
            root / f"features-{s}-{model_name}.parquet",
            root / f"{s}_for_inference.parquet",
        )
        if not (f.is_file() and lab.is_file()):
            continue
        have = pl.read_parquet_schema(lab)
        want = [c for c in CUT_COLS if c in have]
        if not want:
            continue
        fcols = pl.read_parquet_schema(f)
        cur = pl.read_parquet(lab, columns=["hospitalization_id", *want])
        got = pl.read_parquet(
            f, columns=["hospitalization_id", *[c for c in want if c in fcols]]
        ).rename({c: f"feat_{c}" for c in want if c in fcols})
        both = cur.join(got, on="hospitalization_id", how="inner")
        if stay_ids is not None:
            both = both.filter(pl.col("hospitalization_id").is_in(list(stay_ids)))
        mism = pl.lit(False)
        for c in want:
            if f"feat_{c}" not in both.columns:
                mism = pl.lit(True)  # extracted before the cut was stored
                break
            f_, l_ = pl.col(f"feat_{c}"), pl.col(c)
            diff = (f_ - l_).abs() > 1e-6 if c == "cut_s" else f_ != l_
            mism = mism | f_.is_null() | diff
        bad += both.filter(mism).height
    if bad:
        raise StaleFeatures(
            f"{bad} stays have features extracted at another cut than their labels "
            "now have: run icutwin-extract again"
        )


class RepBasedScorer:
    def __init__(
        self, root, lookup, model_home, cfg, estimator_type="logistic-CV-z", probe=None
    ):
        self.root, self.cfg = root, cfg
        # fitted probe per task; loaded from `probe` (inference only) or fit on train
        self.probes = joblib.load(probe) if probe else {}
        self.fit_info = {}  # training side of each fit, for the metrics file
        self.fit = probe is None
        self.splits = ("train", "held_out") if self.fit else ("held_out",)
        self.model_home = pathlib.Path(model_home)
        self.model_name = self.model_home.name
        self.estimator_type = estimator_type
        try:
            self.features = {
                s: np.vstack(
                    pl.read_parquet(
                        root / f"features-{s}-{self.model_name}.parquet",
                        columns=["features"],
                    )
                    .to_series()
                    .to_list()
                )
                for s in self.splits
            }
        except FileNotFoundError as e:
            raise FileNotFoundError(
                "Features not found. Please run `icutwin-extract` first."
            ) from e
        self.labels = {
            s: pl.scan_parquet(root / f"{s}_for_inference.parquet")
            for s in self.splits
        }
        # vocab tokens, plus winnower-derived labels (flag columns, not tokens)
        cols = self.labels["held_out"].collect_schema().names()
        derived = [c[:-5] for c in cols if c.endswith("_past") and c[:-5] not in lookup]
        self.grokked_outcome_tokens = [
            x
            for x in [*lookup, *derived]
            if f"{x}_past" in cols
            and any(fnmatch.fnmatch(x, p) for p in self.cfg.score.target_tokens)
        ]
        logger.info(f"Processed expressions to generate {self.grokked_outcome_tokens=}")

    def make_model(self):
        match str(self.estimator_type).lower():
            case "logistic" | "lr" | "logistic-regression":
                logger.info("Using logistic regression classifier")
                return skl.linear_model.LogisticRegression(max_iter=10_000)
            case "logistic-z" | "lr-z" | "logistic-regression-z":
                logger.info("Using logistic regression classifier on z-scored features")
                return skl.pipeline.make_pipeline(
                    skl.preprocessing.StandardScaler(),
                    skl.linear_model.LogisticRegression(max_iter=10_000),
                )
            case "logistic-cv" | "lr-cv":
                logger.info(
                    "Using logistic regression classifier with cross-validation"
                )
                return skl.linear_model.LogisticRegressionCV(
                    n_jobs=-1,
                    scoring="roc_auc",
                    max_iter=10_000,
                    use_legacy_attributes=False,
                    l1_ratios=(0,),
                )
            case "logistic-cv-z" | "lr-cv-z":
                logger.info(
                    "Using logistic regression classifier with cross-validation "
                    "on z-scored features"
                )
                return skl.pipeline.make_pipeline(
                    skl.preprocessing.StandardScaler(),
                    skl.linear_model.LogisticRegressionCV(
                        n_jobs=-1,
                        scoring="roc_auc",
                        max_iter=10_000,
                        use_legacy_attributes=False,
                        l1_ratios=(0,),  # suppresses a warning
                    ),
                )
            case _:
                raise ValueError(f"unknown estimator {self.estimator_type!r}")

    def fit_label(self, target_token):
        """fit on train stays where the event has not happened before the cut"""
        cols = (~pl.col(f"{target_token}_past"), f"{target_token}_future")
        train_valid, train_label = (
            self.labels["train"].select(*cols).collect().to_numpy().T
        )
        train_valid = train_valid.astype(bool)
        y = train_label[train_valid].astype(int)
        info = self.fit_info[target_token] = {
            "n_train": int(train_valid.sum()),
            "n_train_pos": int(y.sum()),
        }
        if len(set(y)) < 2:  # rare outcome
            logger.warning(f"{target_token}: one class in train, scores left NaN")
            return None
        mdl = self.make_model()
        mdl.fit(X=self.features["train"][train_valid], y=y)
        est = mdl[-1] if isinstance(mdl, skl.pipeline.Pipeline) else mdl
        if hasattr(est, "scores_"):  # CV estimators: chosen C, its mean fold AUROC
            info["C"] = float(est.C_)
            info["cv_roc_auc"] = float(est.scores_.mean(axis=0).max())
        return mdl

    def score_label(self, target_token):
        if self.fit:
            self.probes[target_token] = self.fit_label(target_token)
        mdl = self.probes.get(target_token)
        n_held_out = self.labels["held_out"].select(pl.len()).collect().item()
        if mdl is None:
            return np.full(n_held_out, np.nan)
        held_out_valid = (  # already happened before the cut: no probability
            self.labels["held_out"]
            .select(~pl.col(f"{target_token}_past"))
            .collect()
            .to_numpy()
            .ravel()
            .astype(bool)
        )
        scores = np.nan * np.ones(len(held_out_valid))
        if held_out_valid.any():
            scores[held_out_valid] = mdl.predict_proba(
                X=self.features["held_out"][held_out_valid]
            )[:, 1]
        return scores

    def score(self):
        return {
            f"{tt}_rep_score": self.score_label(target_token=tt)
            for tt in self.grokked_outcome_tokens
        }

    def save_all(self, n_samples: int = 10_000):
        out = self.root / f"scores-rep-based-{self.model_name}.parquet"
        (
            df_res := self.labels["held_out"]
            .select(~cs.by_dtype(pl.List))  # keep ids + flags
            .collect()
            .with_columns(pl.from_dict(self.score()))
        ).write_parquet(out)
        logger.info(out.name)
        if self.fit:
            probe = self.root / f"probe-{self.model_name}.joblib"
            joblib.dump({k: v for k, v in self.probes.items() if v is not None}, probe)
            write_scores_meta(probe, self.model_home)
            logger.info(probe.name)
        held_out = summarize_preds(
            logger, df_res, self.grokked_outcome_tokens, n_samples
        )
        out = self.root / f"metrics-rep-based-{self.model_name}.json"
        report = {
            "model": self.model_name,
            "estimator": str(self.estimator_type),
            "eval_split": "held_out",
            "bootstrap_samples": n_samples,
            "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tasks": {
                tt: {**self.fit_info.get(tt, {}), **held_out.get(tt, {}).get("rep", {})}
                for tt in self.grokked_outcome_tokens
            },
        }
        out.write_text(json.dumps(report, indent=2))
        logger.info(out.name)


def rep_score(
    tokenized_output, model_home, config=None, estimator="logistic-CV-z", probe=None
):
    cfg = merge_config("scoring.yaml", config)
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    RepBasedScorer(
        root, load_vocab(root)["lookup"], model_home, cfg, estimator, probe
    ).save_all()


def apply_probes(
    tokenized_output, model_home, probe, stay_ids=None, out_name=None
) -> pathlib.Path:
    """score another cohort (the stage ward) with a saved probe-<model>.joblib.

    Reads features-<split>-<model>.parquet and <split>_for_inference.parquet for
    every split that has both (icutwin-extract and icutwin-winnow on that cohort),
    keeps `stay_ids` when given, applies each saved probe and writes
    scores-rep-based-<model>.parquet (or `out_name`, so a one-room rescore does not
    overwrite the ward's scores). Nothing is fit here. Same rule as fitting: an
    event already seen before the cut gets no probability; a task with no probe
    (one class in train) stays NaN.
    """
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    probe = pathlib.Path(probe).expanduser().resolve()
    model_name = pathlib.Path(model_home).name
    verify_scores(probe, model_home)
    probes = joblib.load(probe)
    check_features_current(root, model_name, stay_ids)
    labels, xs = [], []
    for s in SPLITS:
        f, lab = (
            root / f"features-{s}-{model_name}.parquet",
            root / f"{s}_for_inference.parquet",
        )
        if not (f.is_file() and lab.is_file()):
            continue
        feats = pl.read_parquet(f, columns=["hospitalization_id", "features"])
        if not feats.height:
            continue
        # features rows may not follow the label order (a --stay-ids re-extract)
        lab_df = (
            pl.read_parquet(lab)
            .select(~cs.by_dtype(pl.List))
            .join(feats.with_row_index("_x"), on="hospitalization_id", how="inner")
        )
        x = np.vstack(feats["features"].to_list())
        labels.append(lab_df.drop("_x", "features"))
        xs.append(x[lab_df["_x"].to_numpy()])
    if not labels:
        raise FileNotFoundError("no features-*/for_inference pair; run extract first")
    labels, xs = pl.concat(labels, how="diagonal"), np.vstack(xs)
    if stay_ids is not None:
        keep = labels["hospitalization_id"].is_in(list(stay_ids)).to_numpy()
        labels, xs = labels.filter(pl.Series(keep)), xs[keep]
    scores = {}
    for token, mdl in probes.items():
        past = f"{token}_past"
        col = np.full(labels.height, np.nan)
        if past in labels.columns and labels.height:
            valid = ~labels[past].to_numpy().astype(bool)
            if valid.any():
                col[valid] = mdl.predict_proba(xs[valid])[:, 1]
        scores[f"{token}_rep_score"] = col
    out = root / (out_name or f"scores-rep-based-{model_name}.parquet")
    labels.with_columns(pl.from_dict(scores)).write_parquet(out)
    write_scores_meta(out, model_home)
    logger.info(f"{out.name}: {labels.height} stays, {len(scores)} probes applied")
    return out


app = typer.Typer(add_completion=False)


@app.command()
def cli(
    tokenized_output: Annotated[
        pathlib.Path, typer.Argument(help="tokenized output folder (icutwin-tokenize)")
    ],
    model_home: Annotated[
        pathlib.Path, typer.Option("--model", "-m", help="mdl-<run_name>/ folder")
    ],
    config: Annotated[
        Optional[pathlib.Path],
        typer.Option("--config", "-c", help="scoring.yaml overrides"),
    ] = None,
    estimator: Annotated[
        EstimatorType, typer.Option("--estimator", "-e")
    ] = EstimatorType.logistic_cv_z,
    probe: Annotated[
        Optional[pathlib.Path],
        typer.Option("--probe", "-p", help="saved probe-<model>.joblib: score only"),
    ] = None,
    apply_from: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            "--apply-probes",
            help="probe-<model>.joblib: score another cohort's features (every "
            "split, no metrics, no fit), e.g. the stage ward",
        ),
    ] = None,
    stay_ids: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            "--stay-ids", help="with --apply-probes: csv of hospitalization_id to keep"
        ),
    ] = None,
):
    """Fit a logistic probe on train features (saved as probe-<model>.joblib),
    score held_out, write metrics-rep-based-<model>.json; with --probe, reuse a
    saved probe and skip the fit; with --apply-probes, score another cohort."""
    if apply_from:
        keep = None
        if stay_ids:
            keep = pl.read_csv(
                stay_ids, schema_overrides={"hospitalization_id": pl.String}
            )["hospitalization_id"].to_list()
        apply_probes(tokenized_output, model_home, apply_from, keep)
        return
    rep_score(tokenized_output, model_home, config, estimator.value, probe)


def main():
    app()


if __name__ == "__main__":
    main()

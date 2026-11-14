#!/usr/bin/env python3

"""
representation-based predictions on held-out data: a logistic-regression probe
on icutwin-extract features, fit on train; writes scores-rep-based-<model>.parquet

Based on cotorra's rep-based scorer (github.com/bbj-lab/cotorra); see
ACKNOWLEDGMENTS.md.
"""

import enum
import fnmatch
import hashlib
import json
import pathlib
import re
from typing import Annotated, Optional

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
# HARDWARE/DEMO PIVOT (for Vaishvik): the winnower's `at_cut` columns say what is
# running at the cut. A support that was started and stopped before the cut is off,
# so apply_probes scores it again (the probe was fit on never-started stays, so
# that score is an extrapolation) instead of leaving it NaN like `_past` does.
AT_CUT = {
    "RESP//device_category//imv": "LABEL//imv_at_cut",
    "LABEL//pressor_init": "LABEL//pressor_at_cut",
    "LABEL//crrt_init": "LABEL//crrt_at_cut",
}
MANIFEST = "manifest.json"
# Events that can happen again: an earlier one does not take the stay out of the task.
# A patient who came to the ICU from a ward has `ADT//TRANSFER_IN//ward_past` true and
# can still leave for a ward or step-down unit (the winnower already drops stays that
# left the ICU between arrival and the cut), so `_past` is ignored for these.
REPEATABLE = ("ADT//TRANSFER_IN//*",)
WEIGHTS_COL = "weights_sha256"  # in every features row: the weights it came from


def repeatable(token: str) -> bool:
    return any(fnmatch.fnmatch(token, p) for p in REPEATABLE)


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


def scores_meta_path(scores: pathlib.Path) -> pathlib.Path:
    return scores.with_suffix(".meta.json")


def write_scores_meta(scores: pathlib.Path, model_home) -> None:
    """provenance beside a scores file: which weights it was made with"""
    scores_meta_path(scores).write_text(
        json.dumps(
            {
                "model": pathlib.Path(model_home).name,
                "weights_sha256": weights_digest(model_home),
            }
        )
    )


def verify_scores(scores: pathlib.Path, model_home) -> None:
    """refuse a scores file that was not made with this model's weights"""
    meta = scores_meta_path(scores)
    if not meta.is_file():
        raise ValueError(
            f"{scores.name} has no {meta.name}: it was not made by "
            "icutwin-rep-score --apply-probes for this model; score again"
        )
    got = json.loads(meta.read_text())
    if got.get("weights_sha256") != weights_digest(model_home):
        raise ValueError(
            f"{scores.name} was made with other weights than {model_home}: "
            "score again with icutwin-rep-score --apply-probes"
        )


class StaleFeatures(ValueError):
    """the features were extracted at another cut than the labels now have"""


def check_features_current(
    root, model_name: str, stay_ids=None, model_home=None, splits=SPLITS
) -> None:
    """refuse features whose stored cut differs from the winnowed labels' cut, and,
    with `model_home`, features made with other weights than that folder holds now
    (a model retrained under the same name; each row carries `weights_sha256`).

    icutwin-extract stores each row's cut (`last_valid`, and `cut_s` when the winnower
    wrote it); a demo-clock move or a new threshold changes the labels' cut, and a
    one-room re-extract leaves the other rows at the old cut. Only `stay_ids` are
    checked when given. Label files without a cut column (old) are not checked."""
    root = pathlib.Path(root)
    bad = other = 0
    digest = weights_digest(model_home) if model_home is not None else None
    for s in splits:
        f, lab = (
            root / f"features-{s}-{model_name}.parquet",
            root / f"{s}_for_inference.parquet",
        )
        if not (f.is_file() and lab.is_file()):
            continue
        have = pl.read_parquet_schema(lab)
        want = [c for c in CUT_COLS if c in have]
        fcols = pl.read_parquet_schema(f)
        if digest:  # no weights found at model_home: nothing to compare with
            w = pl.read_parquet(
                f,
                columns=[
                    "hospitalization_id",
                    *([WEIGHTS_COL] * (WEIGHTS_COL in fcols)),
                ],
            )
            if stay_ids is not None:
                w = w.filter(pl.col("hospitalization_id").is_in(list(stay_ids)))
            other += (
                w.filter(
                    pl.col(WEIGHTS_COL).is_null() | (pl.col(WEIGHTS_COL) != digest)
                ).height
                if WEIGHTS_COL in fcols
                else w.height
            )
        if not want:
            continue
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
    if other:
        raise StaleFeatures(
            f"{other} stays have features extracted with other weights than "
            f"{pathlib.Path(model_home).name} holds now (or none recorded): run "
            "icutwin-extract again"
        )
    if bad:
        raise StaleFeatures(
            f"{bad} stays have features extracted at another cut than their labels "
            "now have: run icutwin-extract again"
        )


def probe_file(token: str) -> str:
    """saved-probe file name: ADT//TRANSFER_IN//icu -> ADT__TRANSFER_IN__icu.joblib"""
    return re.sub(r"[^A-Za-z0-9_-]", "_", token.replace("//", "__")) + ".joblib"


class RepBasedScorer:
    def __init__(
        self,
        root,
        lookup,
        model_home,
        cfg,
        estimator_type="logistic-CV-z",
        save_probes=None,
    ):
        self.root, self.cfg = root, cfg
        # hardware pivot for the live demo: keep each fitted probe so the stage ward
        # is scored with the probe fit on MIMIC training stays, never refit on it
        self.save_probes = pathlib.Path(save_probes) if save_probes else None
        self.manifest = {}
        self.model_home = pathlib.Path(model_home)
        self.model_name = self.model_home.name
        self.estimator_type = estimator_type
        self.features, self.labels = {}, {}
        for s in ("train", "held_out"):
            f = root / f"features-{s}-{self.model_name}.parquet"
            if not f.is_file():
                raise FileNotFoundError(
                    "Features not found. Please run `icutwin-extract` first."
                )
            lab = root / f"{s}_for_inference.parquet"
            feats = pl.read_parquet(f, columns=["hospitalization_id", "features"])
            # each stay gets its own vector: joined by id, in the labels' order (a
            # partial extraction appends re-extracted stays at the end of the file)
            order = (
                pl.read_parquet(lab, columns=["hospitalization_id"])
                .with_row_index("_lab")
                .join(
                    feats.select("hospitalization_id").with_row_index("_x"),
                    on="hospitalization_id",
                    how="left",
                )
                .sort("_lab")
            )
            missing = order["_x"].null_count()
            if missing or order.height != order["_lab"].n_unique():
                raise ValueError(
                    f"{missing} {s} stays have no features (or a stay has two rows): "
                    "run icutwin-extract again"
                )
            x = feats["features"].to_list()
            self.features[s] = (
                np.vstack(x)[order["_x"].to_numpy()] if x else np.empty((0, 0))
            )
            self.labels[s] = pl.scan_parquet(lab)
        check_features_current(
            root, self.model_name, None, self.model_home, ("train", "held_out")
        )
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

    def score_label(self, target_token):
        cols = (~pl.col(f"{target_token}_past"), f"{target_token}_future")
        train_valid, train_label = (
            self.labels["train"].select(*cols).collect().to_numpy().T
        )
        train_valid = train_valid.astype(bool)
        if repeatable(target_token):  # an earlier one does not take the stay out
            train_valid = np.ones_like(train_valid)
        n_held_out = self.labels["held_out"].select(pl.len()).collect().item()
        if len(set(train_label[train_valid].astype(int))) < 2:  # rare outcome
            logger.warning(f"{target_token}: one class in train, scores left NaN")
            self.manifest[target_token] = {
                "file": None,
                "n_train": int(train_valid.sum()),
            }
            return np.full(n_held_out, np.nan)
        mdl = self.make_model()
        mdl.fit(
            X=self.features["train"][train_valid],
            y=train_label[train_valid].astype(int),
        )
        self.manifest[target_token] = {
            "file": probe_file(target_token),
            "n_train": int(train_valid.sum()),
            "positives": int(train_label[train_valid].astype(int).sum()),
        }
        if self.save_probes:
            import joblib

            self.save_probes.mkdir(parents=True, exist_ok=True)
            joblib.dump(mdl, self.save_probes / probe_file(target_token))
        # demo pivot: a support stopped before the cut is off, so score it; the probe
        # was fit on never-started stays (see AT_CUT)
        ho_cols = self.labels["held_out"].collect_schema().names()
        running = AT_CUT.get(target_token)
        ho_mask = ~pl.col(running) if running in ho_cols else cols[0]
        held_out_valid = (
            self.labels["held_out"]
            .select(ho_mask)
            .collect()
            .to_numpy()
            .ravel()
            .astype(bool)
        )
        if running not in ho_cols and repeatable(target_token):
            held_out_valid = np.ones_like(held_out_valid)
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

    def save_all(self, verbose: bool = True):
        out = self.root / f"scores-rep-based-{self.model_name}.parquet"
        (
            df_res := self.labels["held_out"]
            .select(~cs.by_dtype(pl.List))  # keep ids + flags
            .collect()
            .with_columns(pl.from_dict(self.score()))
        ).write_parquet(out)
        logger.info(out.name)
        write_scores_meta(out, self.model_home)
        if self.save_probes:
            (self.save_probes / MANIFEST).write_text(
                json.dumps(
                    {
                        "model": self.model_name,
                        "weights_sha256": weights_digest(self.model_home),
                        "estimator": str(self.estimator_type),
                        "features": int(self.features["train"].shape[1]),
                        "tokens": self.manifest,
                    },
                    indent=2,
                )
            )
            logger.info(f"{len(self.manifest)} probes saved")
        if verbose:
            summarize_preds(logger, df_res, self.grokked_outcome_tokens)


def rep_score(
    tokenized_output,
    model_home,
    config=None,
    estimator="logistic-CV-z",
    save_probes=None,
):
    cfg = merge_config("scoring.yaml", config)
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    RepBasedScorer(
        root, load_vocab(root)["lookup"], model_home, cfg, estimator, save_probes
    ).save_all()


def apply_probes(
    tokenized_output, model_home, probes_dir, stay_ids=None, out_name=None
) -> pathlib.Path:
    """score another cohort (the stage ward) with probes saved by a training run.

    Reads features-<split>-<model>.parquet and <split>_for_inference.parquet for
    every split that has both (icutwin-extract and icutwin-winnow on that cohort),
    keeps `stay_ids` (hospitalization ids) when given, applies each saved probe
    and writes scores-rep-based-<model>.parquet in the same layout fitting writes.
    Nothing is fit here; a task whose probe was skipped in training stays NaN.
    `out_name` (live-demo pivot, for Vaishvik) writes to another file name in the
    folder, so a one-room rescore does not overwrite the whole ward's scores.
    """
    import joblib

    root = pathlib.Path(tokenized_output).expanduser().resolve()
    probes = pathlib.Path(probes_dir).expanduser().resolve()
    model_name = pathlib.Path(model_home).name
    manifest = json.loads((probes / MANIFEST).read_text())
    if manifest["model"] != model_name:
        raise ValueError(
            f"probes were fit for {manifest['model']}, not {model_name}; refit them"
        )
    if manifest.get("weights_sha256") != weights_digest(model_home):
        raise ValueError(
            f"probes were fit on other weights than {model_home} (checksum differs "
            "or none was recorded); refit them with icutwin-rep-score --save-probes"
        )
    check_features_current(root, model_name, stay_ids, model_home)
    parts = []
    for s in SPLITS:
        f, lab = (
            root / f"features-{s}-{model_name}.parquet",
            root / f"{s}_for_inference.parquet",
        )
        if not (f.is_file() and lab.is_file()):
            continue
        ids = pl.read_parquet(f, columns=["hospitalization_id"])
        x = pl.read_parquet(f, columns=["features"]).to_series().to_list()
        feats = pl.DataFrame(
            {"hospitalization_id": ids.to_series(), "_x": list(range(len(x)))}
        )
        labels = (
            pl.read_parquet(lab)
            .select(~cs.by_dtype(pl.List))
            .join(feats, on="hospitalization_id", how="inner")
        )
        parts.append(
            (labels, np.vstack(x) if x else np.empty((0, manifest["features"])))
        )
    if not parts:
        raise FileNotFoundError("no features-*/for_inference pair; run extract first")
    labels = pl.concat([p[0].drop("_x") for p in parts], how="diagonal")
    xs = np.vstack([p[1][p[0]["_x"].to_numpy()] for p in parts])
    if stay_ids is not None:
        keep = labels["hospitalization_id"].is_in(list(stay_ids)).to_numpy()
        labels, xs = labels.filter(pl.Series(keep)), xs[keep]
    scores = {}
    for token, meta in manifest["tokens"].items():
        past = f"{token}_past"
        col = np.full(labels.height, np.nan)
        if meta["file"] and past in labels.columns and labels.height:
            running = AT_CUT.get(token)
            if running in labels.columns:  # off at the cut = forecastable again
                valid = ~labels[running].to_numpy().astype(bool)
            elif repeatable(token):  # e.g. came from a ward: can still leave
                valid = np.ones(labels.height, bool)
            else:
                valid = ~labels[past].to_numpy().astype(bool)
            if valid.any():
                mdl = joblib.load(probes / meta["file"])
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
    save_probes: Annotated[
        Optional[pathlib.Path],
        typer.Option("--save-probes", help="folder to keep the fitted probes in"),
    ] = None,
    apply_from: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            "--apply-probes",
            help="do not fit: score this folder's features with probes saved earlier",
        ),
    ] = None,
    stay_ids: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            "--stay-ids", help="with --apply-probes: csv of hospitalization_id to keep"
        ),
    ] = None,
):
    """Fit a logistic probe on train features, score held_out (or apply probes)."""
    if apply_from:
        keep = None
        if stay_ids:
            keep = pl.read_csv(
                stay_ids, schema_overrides={"hospitalization_id": pl.String}
            )["hospitalization_id"].to_list()
        apply_probes(tokenized_output, model_home, apply_from, keep)
        return
    rep_score(tokenized_output, model_home, config, estimator.value, save_probes)


def main():
    app()


if __name__ == "__main__":
    main()

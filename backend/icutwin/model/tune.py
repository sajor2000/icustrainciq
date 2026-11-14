#!/usr/bin/env python3

"""
find the best decoder with optuna, then train it: each trial is one normal
train() run on one device, searching the model size, learning rate, weight decay,
LR schedule and the weight of every switched-on auxiliary loss (TNT stays on);
objective = best tuning eval_loss (token CE only). The study lives in study.db, so
re-running resumes it and one process per GPU on the same -o tunes in parallel.
At the end best.yaml (a -c override for icutwin-train) is written and, unless
--no-final, the best config is trained in full into <out>/best/
"""

import gc
import pathlib
import shutil
from typing import Annotated, Optional

import optuna
import polars as pl
import torch as t
import typer
from omegaconf import OmegaConf
from transformers import TrainerCallback

from icutwin.common import logger, merge_config
from icutwin.model import decoder

# training_args fields to search via trial.suggest_<type>
SPACE = {
    "learning_rate": {"type": "float", "low": 1e-4, "high": 3e-3, "log": True},
    "weight_decay": {"type": "float", "low": 0.0, "high": 0.3},
    "lr_scheduler_type": {
        "type": "categorical",
        "choices": ["cosine", "linear", "constant_with_warmup"],
    },
}
WEIGHT = {"low": 0.05, "high": 1.0, "log": True}


def suggest(trial, cfg) -> dict:
    """nested train() overrides for one trial; a loss off in cfg stays off"""
    args = {
        n: getattr(trial, f"suggest_{s['type']}")(
            n, **{a: b for a, b in s.items() if a != "type"}
        )
        for n, s in SPACE.items()
    }
    losses = {
        k: {"weight": trial.suggest_float(f"{k}.weight", **WEIGHT)}
        for k, v in cfg.losses.items()
        if v.use
    }
    size = trial.suggest_categorical("size", sorted(cfg.sizes))
    return {"size": size, "losses": losses, "training_args": args}


class Prune(TrainerCallback):
    """report eval_loss after each evaluation; stop the run once optuna prunes it"""

    def __init__(self, trial):
        self.trial, self.n, self.pruned = trial, 0, False

    def on_evaluate(self, args, state, control, metrics=None, **kwargs):
        self.n += 1
        self.trial.report(metrics["eval_loss"], self.n)
        if self.trial.should_prune():
            self.pruned = control.should_training_stop = True


def free():
    gc.collect()
    if t.cuda.is_available():
        t.cuda.empty_cache()


def tune(
    tokenized_output, output, config=None, n_trials=20, study_name="icutwin", final=True
):
    out = pathlib.Path(output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    cfg = merge_config("decoder.yaml", config)

    def objective(trial):
        ov = suggest(trial, cfg)
        trial.set_user_attr("overrides", ov)
        run = out / f"trial-{trial.number}"
        prune = Prune(trial)
        # ponytail: every trial reloads the data; cache rows if that dominates
        trainer = decoder.train(
            tokenized_output, run, config, port=0, callbacks=[prune], **ov
        )
        best = trainer.state.best_metric
        del trainer
        free()
        for d in [*run.glob("checkpoint-*"), *run.glob("mdl-*")]:
            if d.is_dir():  # keep metrics.jsonl and the training yaml
                shutil.rmtree(d)
        if prune.pruned:
            raise optuna.TrialPruned()
        return best

    study = optuna.create_study(
        study_name=study_name,
        storage=f"sqlite:///{out / 'study.db'}",
        load_if_exists=True,
        direction="minimize",
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5, n_warmup_steps=2),
    )
    study.optimize(objective, n_trials=n_trials)

    pl.DataFrame(
        [
            {"trial": s.number, "state": s.state.name, "eval_loss": s.value}
            | {k: str(v) for k, v in s.params.items()}
            for s in study.trials
        ],
        infer_schema_length=None,
    ).write_csv(out / "trials.csv")
    done = [s for s in study.trials if s.state == optuna.trial.TrialState.COMPLETE]
    if not done:
        logger.warning("no completed trial, no best.yaml")
        return study
    best = study.best_trial
    ov = best.user_attrs["overrides"]
    (out / "best.yaml").write_text(OmegaConf.to_yaml(ov))
    logger.info(
        f"best trial {best.number}: eval_loss {best.value:.4f} -> {out / 'best.yaml'}"
    )
    if final:
        logger.info(f"training the best config into {out / 'best'}")
        decoder.train(tokenized_output, out / "best", config, **ov)
        free()
    return study


app = typer.Typer(add_completion=False)


@app.command()
def cli(
    tokenized_output: Annotated[
        pathlib.Path, typer.Argument(help="tokenized output folder (icutwin-tokenize)")
    ],
    output: Annotated[
        pathlib.Path,
        typer.Option("--output", "-o", help="study.db, trials, best.yaml, best/"),
    ] = pathlib.Path("model_output/tune"),
    config: Annotated[
        Optional[pathlib.Path],
        typer.Option("--config", "-c", help="decoder.yaml overrides for every trial"),
    ] = None,
    n_trials: Annotated[int, typer.Option("--n-trials", "-n")] = 20,
    study_name: Annotated[str, typer.Option(help="study name in study.db")] = "icutwin",
    final: Annotated[
        bool,
        typer.Option("--final/--no-final", help="train the best config at the end"),
    ] = True,
):
    """Search size and training settings with optuna, then train the best model."""
    tune(tokenized_output, output, config, n_trials, study_name, final)


def main():
    app()


if __name__ == "__main__":
    main()

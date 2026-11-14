import optuna
from omegaconf import OmegaConf

from icutwin.model.decoder import load_config
from icutwin.model.tune import suggest

P = {
    "size": "l",
    "tnt.weight": 0.3,
    "learning_rate": 1e-3,
    "weight_decay": 0.1,
    "lr_scheduler_type": "linear",
}


def test_suggest_size_tnt_weight_and_merges(tmp_path):
    ov = suggest(optuna.trial.FixedTrial(P), load_config(None))
    assert ov["size"] == "l" and ov["losses"] == {"tnt": {"weight": 0.3}}
    f = tmp_path / "best.yaml"
    f.write_text(OmegaConf.to_yaml(ov))
    cfg = load_config(f)  # best.yaml is a valid -c override
    assert cfg.size == "l" and cfg.losses.tnt.use and cfg.losses.tnt.weight == 0.3
    assert cfg.training_args.lr_scheduler_type == "linear"

    off = tmp_path / "off.yaml"
    off.write_text("losses: {tnt: {use: false}}")
    assert suggest(optuna.trial.FixedTrial(P), load_config(off))["losses"] == {}

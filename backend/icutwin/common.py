#!/usr/bin/env python3

"""
helpers shared by every model and scoring stage: the logger, the tokenized
output's vocabulary, layered yaml configs, and the local live metrics page
"""

import functools
import http.server
import importlib.resources as resources
import json
import pathlib
import shutil
import threading
import time

import yaml
from omegaconf import OmegaConf
from transformers import TrainerCallback

from icutwin.tokenizer.helpers import Logger

logger = Logger("icutwin")


def load_vocab(root: pathlib.Path) -> dict:
    """the vocab.yaml of a tokenized output folder, after checking that the
    train and tuning tokens are there"""
    root = pathlib.Path(root)
    for f in ("tokens_train.parquet", "tokens_tuning.parquet", "vocab.yaml"):
        if not (root / f).is_file():
            raise FileNotFoundError(f"{root / f} missing (run icutwin-tokenize)")
    return yaml.safe_load((root / "vocab.yaml").read_text())


class JsonlLog(TrainerCallback):
    """every Trainer log line → metrics.jsonl (rank 0), read by the live page"""

    def __init__(self, path: pathlib.Path):
        self.path = path

    def on_log(self, args, state, control, logs=None, **kwargs):
        if state.is_world_process_zero:
            row = {"step": state.global_step, "epoch": state.epoch, "time": time.time()}
            with open(self.path, "a") as f:
                f.write(json.dumps(row | (logs or {})) + "\n")


def trim_metrics(path: pathlib.Path, checkpoint_step: int):
    """Drop logs newer than a resume checkpoint so replayed steps stay unique."""
    if not path.is_file():
        return
    kept = []
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("step", 0) <= checkpoint_step:
            kept.append(line)
    path.write_text("".join(line + "\n" for line in kept))


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(out: pathlib.Path, port: int):
    """live page on 127.0.0.1 only (remote: ssh -L PORT:localhost:PORT)"""
    shutil.copy(resources.files("icutwin") / "dashboard.html", out / "index.html")
    try:
        srv = http.server.ThreadingHTTPServer(
            ("127.0.0.1", port), functools.partial(QuietHandler, directory=str(out))
        )
    except OSError as e:
        logger.warning(f"live page off, port {port}: {e}")
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    logger.info(f"live metrics: http://localhost:{port}")


def merge_config(default_file: str, config: pathlib.Path | None, **overrides):
    """shipped config/<default_file> <- user file (known keys only) <- non-None
    CLI options"""
    cfg = OmegaConf.load(resources.files("icutwin.config") / default_file)
    layers = [cfg]
    if config is not None:
        user = OmegaConf.load(config)
        if unknown := set(user) - set(cfg):
            raise ValueError(f"unknown option(s) {sorted(unknown)} in {config}")
        layers.append(user)
    layers.append({k: v for k, v in overrides.items() if v is not None})
    return OmegaConf.merge(*layers)

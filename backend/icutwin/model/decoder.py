#!/usr/bin/env python3

"""
train the ICU Twin decoder: Nemotron 3.5 Bolt E4B layers (Gemma4 text, decoder
only) on the tokenized output folder; stays packed into 4096-token rows with
positions restarting per stay, next-token loss plus the TNT (tnt.py) loss;
multi-GPU through torchrun / accelerate (HF Trainer DDP); metrics go to
metrics.jsonl and a local live page
"""

import bisect
import functools
import math
import os
import pathlib
import shutil
from dataclasses import dataclass
from typing import Annotated, Optional

import numpy as np
import polars as pl
import torch as t
import typer
from omegaconf import OmegaConf
from transformers import Gemma4ForCausalLM, Gemma4TextConfig, Trainer, TrainingArguments
from transformers.modeling_outputs import CausalLMOutputWithPast
from transformers.trainer_utils import get_last_checkpoint

from icutwin.common import (
    JsonlLog,
    load_vocab,
    logger,
    merge_config,
    serve,
    trim_metrics,
)
from icutwin.model import tnt


def load_split(root: pathlib.Path, split: str):
    """flat token ids, flat time targets and stay lengths, stays contiguous;
    time target = log1p(minutes to the next token) within the stay, NaN at its end;
    only narrow columns kept, so peak memory stays small"""
    d = (
        pl.scan_parquet(root / f"tokens_{split}.parquet")
        .select("hospitalization_id", "event_time", "token_id", "position_id")
        .sort("hospitalization_id", "position_id")
        .select(
            pl.col("token_id").cast(pl.Int32),
            dt=(pl.col("event_time").shift(-1) - pl.col("event_time"))
            .over("hospitalization_id")
            .dt.total_seconds()
            .clip(0)
            .cast(pl.Float32)
            / 60,
            new_stay=pl.col("hospitalization_id")
            .ne_missing(pl.col("hospitalization_id").shift())
            .fill_null(True),
        )
        .collect(engine="streaming")
    )
    ids = d["token_id"].to_numpy()
    dt = np.log1p(d["dt"].fill_null(np.nan).to_numpy())
    starts = np.flatnonzero(d["new_stay"].to_numpy())
    return ids, dt.astype(np.float32), np.diff(starts, append=len(ids))


def stay_offsets(root: pathlib.Path, split: str) -> pl.DataFrame:
    """hospitalization_id -> (start, n) in the order load_split lays them out, so a
    probe can take exactly the tokens a training window would have seen"""
    d = (
        pl.scan_parquet(root / f"tokens_{split}.parquet")
        .select("hospitalization_id", "position_id")
        .sort("hospitalization_id", "position_id")
        .select("hospitalization_id", new_stay=pl.col("hospitalization_id").ne_missing(
            pl.col("hospitalization_id").shift()).fill_null(True))
        .collect(engine="streaming")
    )
    starts = np.flatnonzero(d["new_stay"].to_numpy())
    n = np.diff(starts, append=d.height)
    return pl.DataFrame(
        {
            "hospitalization_id": d["hospitalization_id"].gather(starts),
            "start": starts.astype(np.int64),
            "n": n.astype(np.int64),
        }
    )


def pack(lens: np.ndarray, width: int, rng) -> list[list[tuple[int, int]]]:
    """rows of (start, end) segments, each row ≤ width tokens; stays longer than
    width are cut into width-sized windows; best-fit decreasing, so rows are full"""
    starts = np.cumsum(lens) - lens
    segs = [
        (a, min(a + width, s + n))
        for s, n in zip(starts.tolist(), lens.tolist())
        for a in range(s, s + n, width)
    ]
    rng.shuffle(segs)  # random order among equal lengths
    segs.sort(key=lambda ab: ab[0] - ab[1])  # longest first
    rows, free = [], []  # free: sorted (space left, row index)
    for a, b in segs:
        i = bisect.bisect_left(free, (b - a, -1))  # tightest row it fits in
        if i == len(free):
            rows.append([])
            left, r = width, len(rows) - 1
        else:
            left, r = free.pop(i)
        rows[r].append((a, b))
        if left - (b - a):
            bisect.insort(free, (left - (b - a), r))
    return rows


class Packed(t.utils.data.Dataset):
    """one packed row per item; the tail is padded as one more pseudo-stay with its
    own positions, so the block mask built from position_ids keeps it apart;
    `passes` packings from one rng, each epoch grouped apart"""

    def __init__(self, ids, dt, lens, width: int, seed: int, passes: int = 1):
        self.ids, self.dt, self.width = ids, dt, width
        rng = np.random.default_rng(seed)
        self.rows = [r for _ in range(passes) for r in pack(lens, width, rng)]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        idx = np.concatenate([np.arange(a, b) for a, b in self.rows[i]])
        pos = np.concatenate([np.arange(b - a) for a, b in self.rows[i]])
        pad = self.width - len(idx)
        ids = self.ids[idx].astype(np.int64)
        pos = np.concatenate([pos, np.arange(pad)])
        # first token of a stay is not predicted from the previous stay
        labels = np.where(pos[: len(ids)] == 0, -100, ids)
        return {
            "input_ids": t.from_numpy(np.pad(ids, (0, pad))),
            "position_ids": t.from_numpy(pos),
            "labels": t.from_numpy(np.pad(labels, (0, pad), constant_values=-100)),
            "dt": t.from_numpy(np.pad(self.dt[idx], (0, pad), constant_values=np.nan)),
        }


def collate(rows, flat: bool):
    """stack rows; flash_attention_2 only unpacks a single row, so flatten for it"""
    batch = {k: t.stack([r[k] for r in rows]) for k in rows[0]}
    return {k: v.reshape(1, -1) for k, v in batch.items()} if flat else batch


class ExactPrefix(t.utils.data.Dataset):
    """the last `width` tokens of one stay ending at a given cut, so a probe sees
    the same kind of window training did (training only ever sees 4096-token
    windows); rows: (hospitalization_id, start, n, cut) with cut - start <= width"""

    def __init__(self, ids, stays: pl.DataFrame, cuts: pl.DataFrame, width: int):
        self.ids, self.width = np.asarray(ids), width
        joined = (
            cuts.select("hospitalization_id", "cut")
            .join(stays, on="hospitalization_id", how="inner")
            .with_columns(
                seq_start=pl.max_horizontal(pl.col("start"), pl.col("cut") - width)
            )
            .sort("hospitalization_id", "cut")
        )
        self.keys = joined.select("hospitalization_id")
        self.table = joined.select("seq_start", "cut").to_numpy()

    def __len__(self):
        return len(self.table)

    def __getitem__(self, i):
        a, b = self.table[i]
        ids = self.ids[a:b].astype(np.int64)
        pos = np.arange(b - a)
        return {"input_ids": t.from_numpy(ids), "position_ids": t.from_numpy(pos)}


@dataclass
class IcuTwinOutput(CausalLMOutputWithPast):
    tnt_loss: t.FloatTensor | None = None


class IcuTwin(Gemma4ForCausalLM):
    """Gemma4ForCausalLM + a TNT head on the last hidden state when `losses.tnt` is
    on (saved beside the final model, so inference takes token ids only unless a
    task attaches it); with it off it trains as a plain Gemma4ForCausalLM"""

    accepts_loss_kwargs = False  # losses are per-micro-batch means; Trainer scales GA

    def __init__(self, config, tnt_head: bool = True):
        super().__init__(config)
        self.tnt_head = tnt.TntHead(config.hidden_size) if tnt_head else None

    def forward(self, dt=None, **kwargs):
        timed = self.tnt_head is not None and dt is not None
        out = super().forward(**kwargs, output_hidden_states=timed)
        parts = {}
        if timed:
            pred = self.tnt_head(out.hidden_states[-1]).float()
            ok = dt.isfinite()
            parts["tnt_loss"] = (
                t.nn.functional.mse_loss(pred[ok], dt[ok])
                if ok.any()
                else pred.sum() * 0
            )
        return IcuTwinOutput(**out, **parts) if parts else out


def layer_types(n: int, full_every: int) -> list[str]:
    """Bolt E4B pattern: every full_every-th layer full attention, the rest
    sliding window; the last layer is always full"""
    return [
        "full_attention"
        if (i + 1) % full_every == 0 or i == n - 1
        else "sliding_attention"
        for i in range(n)
    ]


def build_model(cfg, lookup: dict) -> IcuTwin:
    model = OmegaConf.to_container(cfg.model)
    size = OmegaConf.to_container(cfg.sizes[cfg.size])
    full_every = model.pop("full_every")
    conf = Gemma4TextConfig(
        vocab_size=len(lookup),
        vocab_size_per_layer_input=len(lookup),
        pad_token_id=lookup["UNK"],
        bos_token_id=lookup["BOS"],
        eos_token_id=lookup["EOS"],
        max_position_embeddings=cfg.max_seq_len,
        use_cache=False,
        layer_types=layer_types(size["num_hidden_layers"], full_every),
        **model,
        **size,
    )
    conf._attn_implementation = cfg.attn_implementation
    return IcuTwin(conf, tnt_head=cfg.losses.tnt.use)


def sync_loss_parts(parts: dict[str, t.Tensor], n_parts: int) -> dict[str, float]:
    """Average custom loss components over every micro-batch on every DDP rank."""
    keys = sorted(parts)
    values = t.stack(
        [parts[k] for k in keys] + [parts[keys[0]].new_tensor(float(n_parts))]
    )
    if t.distributed.is_available() and t.distributed.is_initialized():
        t.distributed.all_reduce(values)
    count = values[-1].item()
    return {k: values[i].item() / count for i, k in enumerate(keys)}


class LossTrainer(Trainer):
    """train loss = token CE + Σ weight·part over the switched-on losses (all
    logged); eval loss = token CE only, so tuning loss compares across losses and
    sizes"""

    def __init__(self, *args, weights: dict[str, float] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.weights, self.parts, self.n_parts = weights or {}, {}, 0

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None, **kwargs):
        out = model(**inputs)
        loss = out.loss
        if model.training:
            parts = {"token_loss": out.loss} | {k: getattr(out, k) for k in self.weights}
            loss = loss + sum(w * parts[k] for k, w in self.weights.items())
            # per-token means (transformers divides by num_items_in_batch too)
            weight = num_items_in_batch if isinstance(num_items_in_batch, int) else 1
            for k, v in parts.items():
                self.parts[k] = self.parts.get(k, 0.0) + v.detach().float() * weight
            self.n_parts += weight
        return (loss, out) if return_outputs else loss

    def log(self, logs, *args, **kwargs):
        if "loss" in logs and self.n_parts:
            synced = sync_loss_parts(self.parts, self.n_parts)
            logs |= {k: round(v, 4) for k, v in synced.items()}
            self.parts, self.n_parts = {}, 0
        super().log(logs, *args, **kwargs)


def load_config(config: pathlib.Path | None, **overrides):
    cfg = merge_config("decoder.yaml", config, **overrides)
    if cfg.size not in cfg.sizes:
        raise ValueError(f"size {cfg.size!r} must be one of {list(cfg.sizes)}")
    return cfg


def train(
    tokenized_output, output, config=None, resume=False, callbacks=(), **overrides
):
    cfg = load_config(config, **overrides)
    out = pathlib.Path(output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    vocab = load_vocab(root)

    # every epoch packed apart, then trained as one HF epoch over all the passes
    epochs = cfg.training_args.num_train_epochs
    passes = {"train": math.ceil(epochs), "tuning": 1}
    # ponytail: every DDP rank loads and packs on its own; cache rows on disk if slow
    data = {
        split: Packed(*load_split(root, split), cfg.max_seq_len, cfg.seed, n)
        for split, n in passes.items()
    }
    logger.info(", ".join(f"{s}: {len(d):,} packed rows" for s, d in data.items()))

    t.manual_seed(cfg.seed)
    model = build_model(cfg, vocab["lookup"])
    n_param = sum(p.numel() for n, p in model.named_parameters() if "tnt_head" not in n)
    logger.info(f"size {cfg.size}: {n_param:,} params")

    main = int(os.environ.get("RANK", 0)) == 0
    metrics_path = out / "metrics.jsonl"
    if main:
        if resume and (checkpoint := get_last_checkpoint(str(out))):
            checkpoint_step = int(pathlib.Path(checkpoint).name.rsplit("-", 1)[1])
            trim_metrics(metrics_path, checkpoint_step)
        elif not resume:
            metrics_path.unlink(missing_ok=True)
    if main and cfg.port:
        serve(out, cfg.port)

    bf16 = t.cuda.is_available() and t.cuda.is_bf16_supported()
    args = {"bf16": bf16, **OmegaConf.to_container(cfg.training_args)}
    args["num_train_epochs"] = epochs / passes["train"]
    trainer = LossTrainer(
        model=model,
        args=TrainingArguments(
            output_dir=str(out), run_name=cfg.run_name, seed=cfg.seed, **args
        ),
        train_dataset=data["train"],
        eval_dataset=data["tuning"],
        data_collator=functools.partial(
            collate, flat=cfg.attn_implementation == "flash_attention_2"
        ),
        callbacks=[JsonlLog(metrics_path), *callbacks],
        weights={f"{k}_loss": v.weight for k, v in cfg.losses.items() if v.use},
    )
    trainer.train(resume_from_checkpoint=resume or None)

    if trainer.is_world_process_zero():  # mdl-<run>/ + its yaml
        final = Gemma4ForCausalLM(trainer.model.config)
        final.load_state_dict(
            {k: v for k, v in trainer.model.state_dict().items() if "tnt_head" not in k}
        )
        mdl_dir = out / f"mdl-{cfg.run_name}"
        final.save_pretrained(mdl_dir)
        if trainer.model.tnt_head is not None:
            tnt.save(trainer.model.tnt_head, mdl_dir)
        shutil.copy(root / "vocab.yaml", mdl_dir / "vocab.yaml")
        (out / f"mdl-{cfg.run_name}-training.yaml").write_text(OmegaConf.to_yaml(cfg))
        logger.info(f"saved {mdl_dir}")
    return trainer


app = typer.Typer(add_completion=False)


@app.command()
def cli(
    tokenized_output: Annotated[
        pathlib.Path, typer.Argument(help="tokenized output folder (icutwin-tokenize)")
    ],
    output: Annotated[
        pathlib.Path, typer.Option("--output", "-o", help="checkpoints, model, metrics")
    ] = pathlib.Path("model_output"),
    config: Annotated[
        Optional[pathlib.Path],
        typer.Option("--config", "-c", help="decoder.yaml overrides"),
    ] = None,
    size: Annotated[Optional[str], typer.Option(help="s | m | l")] = None,
    port: Annotated[Optional[int], typer.Option(help="live page port, 0 = off")] = None,
    resume: Annotated[
        bool, typer.Option("--resume", "-r", help="resume from the last checkpoint")
    ] = False,
):
    """Train the ICU Twin decoder on tokens_train.parquet."""
    train(tokenized_output, output, config, resume, size=size, port=port)


def main():
    app()


if __name__ == "__main__":
    main()

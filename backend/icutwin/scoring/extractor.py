#!/usr/bin/env python3

"""
extract representations (last hidden layer at the last prompt token) up to the
prediction time set by icutwin-winnow; writes features-{split}-<model>.parquet
for icutwin-rep-score

The probe sees the window the model was trained on: the 4096 tokens ending at
the stay's cut, laid out exactly as icutwin-train lays stays out, so the prompt
is never a short left-padded stub. The probe length is `cut_token_lengths`,
which is the winnower's own cut (`last_valid` in <split>_for_inference.parquet), so
any threshold rule matches; for older files without it, it is recomputed from
the raw token file with the duration rule (the last token strictly before the
cut).

Based on cotorra's extractor (github.com/bbj-lab/cotorra); see ACKNOWLEDGMENTS.md.
"""

import pathlib
from typing import Annotated, Optional

import numpy as np
import polars as pl
import torch as t
import typer
from torch.nn.utils.rnn import pad_sequence
from transformers import AutoModelForCausalLM

from icutwin.common import logger, merge_config
from icutwin.model.decoder import ExactPrefix, load_split, stay_offsets

SPLITS = ("train", "tuning", "held_out")


def cut_token_lengths(root: pathlib.Path, split: str, cut_s: float) -> pl.DataFrame:
    """hospitalization_id -> tokens before the cut, counted from the token file
    with icutwin-winnow's rule: positions at or after `cut_s` are the future"""
    return (
        pl.scan_parquet(root / f"tokens_{split}.parquet")
        .select("hospitalization_id", "event_time", "token_id")
        .sort("hospitalization_id", "event_time", "token_id")
        .with_columns(first=pl.col("event_time").min().over("hospitalization_id"))
        .filter(pl.col("event_time") < pl.col("first") + pl.duration(seconds=cut_s))
        .group_by("hospitalization_id")
        .agg(n=pl.len())
        .collect(engine="streaming")
    )


def merge_features(
    out: pathlib.Path, new: pl.DataFrame, keep_ids: list[str]
) -> pl.DataFrame:
    """HARDWARE/DEMO PIVOT (for Vaishvik): a `--stay-ids` run re-extracts only some
    stays; keep the other stays' rows from the existing features file so the cohort's
    features stay whole (rows replaced by id, order: kept rows then new rows)"""
    if not out.is_file():
        return new
    old = pl.read_parquet(out).filter(
        ~pl.col("hospitalization_id").is_in(new["hospitalization_id"].to_list())
    )
    # diagonal: rows kept from a file made before cuts were stored get null cuts,
    # which the scorers read as stale
    return pl.concat([old, new], how="diagonal_relaxed") if old.height else new


class Extractor:
    """load a model and extract representations from it"""

    def __init__(self, model_home: pathlib.Path, cfg):
        self.model_home, self.cfg = model_home, cfg
        self.device = (
            "cuda"
            if t.cuda.is_available()
            else "mps"
            if t.backends.mps.is_available()
            else "cpu"
        )
        self.model = AutoModelForCausalLM.from_pretrained(self.model_home)
        self.model.to(self.device).eval()
        if not isinstance(self.model.config.pad_token_id, int):
            self.model.config.pad_token_id = self.model.config.eos_token_id

    def collate_fn(self, batch):
        pad = self.model.config.pad_token_id
        return {
            "input_ids": pad_sequence(
                [x["input_ids"] for x in batch], batch_first=True, padding_value=pad
            ).to(self.device),
            "position_ids": pad_sequence(
                [x["position_ids"] for x in batch], batch_first=True, padding_value=0
            ).to(self.device),
        }

    def extract_final(self, batch) -> np.ndarray:
        """the last hidden state at each stay's last real token"""
        collated = self.collate_fn(batch)
        last = t.tensor([len(x["input_ids"]) for x in batch], device=self.device) - 1
        with t.inference_mode():
            hidden = self.model(**collated, output_hidden_states=True).hidden_states
        return hidden[-1][t.arange(len(last)), last].half().cpu().numpy()

    def extract(self, root: pathlib.Path, stay_ids: list[str] | None = None):
        bs, width = self.cfg.extract.batch_size, self.cfg.extract.max_len
        cut_s = float(merge_config("winnowing.yaml", None).threshold.duration_s)
        for split in SPLITS:
            src = root / f"{split}_for_inference.parquet"
            if not src.is_file():
                raise FileNotFoundError(f"{src} missing; run icutwin-winnow first")
            ids, _, _ = load_split(root, split)
            stays = stay_offsets(root, split)
            # the winnower stores each stay's cut (`last_valid`, tokens before it in
            # position order); use it so any threshold rule (e.g. 24 h after ICU
            # arrival, D3) gives the same cut here. Older files lack it.
            schema = pl.read_parquet_schema(src)
            if "last_valid" in schema:
                lengths = pl.read_parquet(
                    src, columns=["hospitalization_id", "last_valid"]
                ).rename({"last_valid": "n"})
            else:
                lengths = cut_token_lengths(root, split, cut_s)
            # each row's cut goes into the features file (HARDWARE/DEMO PIVOT, for
            # Vaishvik): icutwin-rep-score --apply-probes and app/rooms.py refuse
            # rows whose stored cut is not the labels' cut (a demo-clock move, or a
            # one-room re-extract that left other rows at the old cut)
            stored = lengths.rename({"n": "last_valid"})
            if "cut_s" in schema:
                stored = stored.join(
                    pl.read_parquet(src, columns=["hospitalization_id", "cut_s"]),
                    on="hospitalization_id",
                    how="left",
                )
            # cut offsets: the stay's start + the tokens before its cut
            cuts = (
                lengths.join(stays, on="hospitalization_id", how="inner")
                .with_columns(cut=pl.col("start") + pl.col("n"))
                .select("hospitalization_id", "cut")
            )
            wanted = pl.read_parquet(src, columns=["hospitalization_id"])
            if stay_ids is not None:  # demo pivot: one room, not the whole ward
                wanted = wanted.filter(pl.col("hospitalization_id").is_in(stay_ids))
            ds = ExactPrefix(ids, stays, cuts, width)
            order = (
                wanted.with_row_index("row")
                .join(
                    ds.keys.with_row_index("ds_row"),
                    on="hospitalization_id",
                    how="inner",
                )
                .sort("row")
            )
            feats = np.vstack(
                [
                    self.extract_final(
                        [ds[j] for j in order["ds_row"][i : i + bs].to_list()]
                    )
                    for i in range(0, order.height, bs)
                ]
                or [np.empty((0, self.model.config.hidden_size), np.float16)]
            )
            out = root / f"features-{split}-{self.model_home.name}.parquet"
            new = (
                order.select("hospitalization_id")
                .with_columns(features=pl.Series(list(feats)))
                .join(stored, on="hospitalization_id", how="left")
            )
            if stay_ids is not None:
                new = merge_features(out, new, stay_ids)
            new.write_parquet(out)
            logger.info(
                f"{split}: {order.height:,} stays, {width}-token windows, "
                f"median probe {cuts['cut'].median() if cuts.height else 0:.0f} "
                f"-> {out.name}"
            )


def extract(tokenized_output, model_home, config=None, stay_ids=None):
    cfg = merge_config("extraction.yaml", config)
    extractor = Extractor(pathlib.Path(model_home).expanduser().resolve(), cfg)
    extractor.extract(pathlib.Path(tokenized_output).expanduser().resolve(), stay_ids)


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
        typer.Option("--config", "-c", help="extraction.yaml overrides"),
    ] = None,
    stay_ids: Annotated[
        Optional[pathlib.Path],
        typer.Option(
            "--stay-ids",
            help="demo pivot: csv of hospitalization_id to (re-)extract; other "
            "stays keep their rows in the features file",
        ),
    ] = None,
):
    """Extract last-layer features at the prediction time."""
    keep = None
    if stay_ids:
        keep = pl.read_csv(
            stay_ids, schema_overrides={"hospitalization_id": pl.String}
        )["hospitalization_id"].to_list()
    extract(tokenized_output, model_home, config, keep)


def main():
    app()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

"""
the task: cut each stay at a prediction time and flag outcomes before / after it;
writes {split}_for_inference.parquet for icutwin-extract and the scorers

Based on cocoa's winnower (github.com/bbj-lab/cocoa); see ACKNOWLEDGMENTS.md.
"""

import fnmatch
import operator
import pathlib
from typing import Annotated, Optional

import polars as pl
import typer

from icutwin.common import load_vocab, logger, merge_config

OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le}


class Winnower:
    def __init__(self, root: pathlib.Path, cfg, lookup: dict):
        self.root, self.cfg, self.lookup = root, cfg, lookup
        self.grokked_outcome_tokens = [
            x
            for x in lookup
            if any(fnmatch.fnmatch(x, p) for p in self.cfg.outcome_tokens)
        ]
        logger.info(f"outcomes {self.grokked_outcome_tokens}")
        self.labels = {n: self.label_expr(c) for n, c in cfg.get("labels", {}).items()}

    def label_expr(self, conds) -> pl.Expr:
        """per-token hit of a derived label: any [token pattern, op, value]"""
        hit = pl.lit(False)
        for pat, *thr in conds:
            ids = [i for w, i in self.lookup.items() if fnmatch.fnmatch(w, pat)]
            c = pl.col("token_id").is_in(ids)
            if thr:
                c = c & OPS[thr[0]](pl.col("value"), thr[1])
            hit = hit | c.fill_null(False)
        return hit

    def load_frame(self, split="held_out") -> pl.LazyFrame:
        """one row per stay with `tokens` and `times` lists, plus elapsed-time
        columns"""
        return (
            pl.scan_parquet(self.root / f"tokens_{split}.parquet")
            .select(
                "hospitalization_id", "event_time", "token_id", "value", "position_id"
            )
            .sort("hospitalization_id", "position_id")
            .group_by("hospitalization_id", maintain_order=True)
            .agg(
                tokens=pl.col("token_id").cast(pl.Int64),
                times="event_time",
                **{f"{n}_hit": e for n, e in self.labels.items()},
            )
            .with_columns(
                s_elapsed=pl.col("times").list.eval(
                    (pl.element() - pl.element().first()).dt.total_seconds()
                )
            )
            .with_columns(s_total_duration=pl.col("s_elapsed").list.last())
        )

    def run_thresholding(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        evaluates configurable criteria for establishing a cut-point "last_valid";
        drops timelines that do not reach that point
        """
        th = self.cfg.get("threshold", {})
        if th.get("after_first_occurrence"):
            # D3: cut `duration_s` after the first `token` (e.g. 24 h after ICU
            # arrival); keep stays that are still running at the cut and, when
            # `stay_until_cut` is set, have no other matching token (e.g. a transfer
            # out of the ICU) between arrival and the cut.
            # Demo clock (docs/LIVE_DEMO.md): `offset_s` (default 0) is added to
            # `duration_s` to move the cut later; the cut must stay after ICU arrival.
            spec = th.after_first_occurrence
            after_s = spec.duration_s + spec.get("offset_s", 0)
            if after_s <= 0:
                raise ValueError(
                    f"threshold duration_s + offset_s = {after_s} s: the cut must "
                    "fall after ICU arrival (a demo-clock offset cannot undo the 24 h)"
                )
            toi = self.lookup[spec.token]
            leave = [
                i
                for w, i in self.lookup.items()
                if spec.get("stay_until_cut")
                and fnmatch.fnmatch(w, spec.stay_until_cut)
                and i != toi
            ]
            first = pl.col("tokens").list.eval(pl.element() == toi).list.arg_max()
            df = (
                df.filter(pl.col("tokens").list.contains(toi))
                .with_columns(first_i=first)
                .with_columns(
                    cut_s=pl.col("s_elapsed").list.get(pl.col("first_i")) + after_s
                )
                .filter(pl.col("s_total_duration") > pl.col("cut_s"))
                .with_columns(
                    last_valid=(pl.col("s_elapsed") - pl.col("cut_s"))
                    .list.eval(pl.element() < 0)
                    .list.sum()
                )
            )
            if leave:
                left = (
                    pl.col("tokens")
                    .list.slice(
                        pl.col("first_i") + 1,
                        pl.col("last_valid") - pl.col("first_i") - 1,
                    )
                    .list.eval(pl.element().is_in(leave))
                    .list.any()
                )
                df = df.filter(~left)
            # `cut_s` (seconds from the first token) stays in the output: app/rooms.py
            # reads it to place recent events relative to the cut
            return df.drop("first_i")
        if "horizon_s" in self.cfg or "duration_s" in th:
            # run duration-based thresholding
            horizon_s = self.cfg.get("horizon_s", self.cfg.threshold.duration_s)
            return df.filter(pl.col("s_total_duration") > horizon_s).with_columns(
                last_valid=pl.col("s_elapsed")
                .list.eval(pl.element() < horizon_s)
                .list.sum(),
                cut_s=pl.lit(float(horizon_s)),
            )
        elif "first_occurrence" in self.cfg.get("threshold", {}):
            # run first-occurrence-based thresholding
            toi = self.lookup[self.cfg.threshold.first_occurrence]
            return (
                df.filter(pl.col("tokens").list.contains(toi))
                .with_columns(
                    last_valid=pl.col("tokens")
                    .list.eval(pl.element() == toi)
                    .list.arg_max()
                    + pl.lit(1)
                    # place the triggering token into the past; it is known
                )
                .with_columns(
                    cut_s=pl.col("s_elapsed").list.get(pl.col("last_valid") - 1)
                )
            )
        else:
            raise NotImplementedError("Please check the thresholding configuration.")

    def add_outcome_flags(self, df: pl.LazyFrame) -> pl.LazyFrame:
        """
        adds boolean flags for each outcome token and tense,
        e.g. HOSP//discharge_category//expired_past, ..._future
        """
        df = df.with_columns(
            tokens_past=pl.col("tokens").list.head("last_valid"),
            s_elapsed_past=pl.col("s_elapsed").list.head("last_valid"),
            tokens_future=pl.col("tokens").list.tail(
                pl.col("tokens").list.len() - pl.col("last_valid")
            ),
        )  # split into past and future
        if "horizon_after_threshold_s" in self.cfg:
            # the window is [cut, cut + horizon): counted from the cut itself (e.g.
            # 07:00 to 07:00), not from the last token before it
            end = pl.col("cut_s") + self.cfg.horizon_after_threshold_s
            df = df.with_columns(
                valid_future_count=(pl.col("s_elapsed") - end)
                .list.eval(pl.element() < 0)
                .list.sum()
                - pl.col("last_valid")
            ).with_columns(
                tokens_future=pl.col("tokens_future").list.head("valid_future_count")
            )
        # derived labels, cut exactly as the tokens they come from
        hit = lambda n: pl.col(f"{n}_hit")
        future = lambda n: hit(n).list.tail(hit(n).list.len() - pl.col("last_valid"))
        if "horizon_after_threshold_s" in self.cfg:
            future = lambda n, f=future: f(n).list.head("valid_future_count")
        return df.with_columns(
            **{
                f"{t}_{tense}": pl.col(f"tokens_{tense}").list.contains(self.lookup[t])
                for t in self.grokked_outcome_tokens
                for tense in ("past", "future")
            },
            **{
                f"{n}_past": hit(n).list.head("last_valid").list.any()
                for n in self.labels
            },
            **{f"{n}_future": future(n).list.any() for n in self.labels},
        ).drop(f"{n}_hit" for n in self.labels)

    def ids_of(self, patterns) -> list[int]:
        return [
            i
            for w, i in self.lookup.items()
            if any(fnmatch.fnmatch(w, p) for p in patterns)
        ]

    def add_at_cut_flags(self, df: pl.LazyFrame, split: str) -> pl.LazyFrame:
        """HARDWARE/DEMO PIVOT (for Vaishvik): `<name>` boolean columns saying what is
        actually running at the cut, from the records before it (config `at_cut`),
        unlike `<token>_past` (started at any time before the cut). Three rules:
          last_of:   the last token among `last_of` patterns is one of `running_if`
                     (IMV: the last device_category record is imv);
          dose_gt:   for each pattern in `groups` take its last non-null dose; running
                     when it is > `dose_gt` (vasopressor: last dose of any drug > 0;
                     a null dose is unknown, so the previous dose carries);
          within_s:  any `any_of` token in the `within_s` seconds before the cut
                     (CRRT: the tokens have no stop signal, only a charted-row flag).
        Needs the winnower's `last_valid` (and `cut_s` when present)."""
        specs = self.cfg.get("at_cut") or {}
        if not specs:
            return df
        names = df.collect_schema().names()
        cut = (
            pl.col("cut_s")
            if "cut_s" in names
            else pl.col("el").max().over("hospitalization_id")  # last past token
        )
        long = (
            pl.scan_parquet(self.root / f"tokens_{split}.parquet")
            .select(
                "hospitalization_id", "event_time", "token_id", "value", "position_id"
            )
            .sort("hospitalization_id", "position_id")
            .with_columns(
                idx=pl.int_range(pl.len()).over("hospitalization_id"),
                el=(
                    pl.col("event_time")
                    - pl.col("event_time").first().over("hospitalization_id")
                ).dt.total_seconds(),
            )
            .join(
                df.select(
                    "hospitalization_id",
                    "last_valid",
                    *(["cut_s"] if "cut_s" in names else []),
                ),
                on="hospitalization_id",
            )
            .filter(pl.col("idx") < pl.col("last_valid"))
            # a join does not promise row order, and `.last()` below needs it
            .sort("hospitalization_id", "idx")
            .with_columns(age=cut - pl.col("el"))
        )
        ids = df.select("hospitalization_id")
        out = []
        for name, spec in specs.items():
            if "last_of" in spec:
                run = set(self.ids_of(spec["running_if"]))
                f = (
                    long.filter(pl.col("token_id").is_in(self.ids_of(spec["last_of"])))
                    .group_by("hospitalization_id")
                    .agg(v=pl.col("token_id").last().is_in(list(run)))
                )
            elif "dose_gt" in spec:
                f = (
                    pl.concat(
                        [
                            long.filter(pl.col("token_id").is_in(self.ids_of([g])))
                            .group_by("hospitalization_id")
                            # a null dose is unknown, not zero: carry the last
                            # non-null dose (all null: not running)
                            .agg(
                                v=pl.col("value").drop_nulls().last() > spec["dose_gt"]
                            )
                            for g in spec["groups"]
                        ]
                    )
                    .group_by("hospitalization_id")
                    .agg(v=pl.col("v").fill_null(False).any())
                )
            elif "within_s" in spec:
                f = (
                    long.filter(pl.col("token_id").is_in(self.ids_of(spec["any_of"])))
                    .filter(pl.col("age") <= spec["within_s"])
                    .group_by("hospitalization_id")
                    .agg(v=pl.lit(True))
                )
            else:
                raise ValueError(f"at_cut.{name}: need last_of, dose_gt or within_s")
            out.append(f.rename({"v": name}))
        for f in out:
            ids = ids.join(f, on="hospitalization_id", how="left")
        flags = ids.with_columns(*(pl.col(n).fill_null(False) for n in specs))
        return df.join(flags, on="hospitalization_id", how="left")

    def prepare_winnowed_frame(self, split="held_out") -> pl.LazyFrame:
        """loads a split, splits at time threshold, and prepares labels"""
        return (
            self.load_frame(split=split)
            .pipe(self.run_thresholding)
            .pipe(self.add_outcome_flags)
            .pipe(self.add_at_cut_flags, split)
        )

    def save_all(self, counts_only: bool = False):
        """saves each split and logs outcome rates (aggregates only). counts_only: log
        the number of stays and nothing else; for a small ward (25 stays) a rate is a
        clinical value about a few patients, and workflow logs hold counts only."""
        for split in self.cfg.splits:
            out = self.root / f"{split}_for_inference.parquet"
            self.prepare_winnowed_frame(split=split).drop("times").sink_parquet(
                out, engine="streaming"
            )
            df = pl.scan_parquet(out)
            if counts_only:
                n = df.select(pl.len()).collect().item()
                logger.info(f"{split}: {n} stays")
                continue
            rates = df.select(
                pl.len().alias("stays"),
                *(
                    pl.col(f"{t}_{s}").mean().round(4)
                    for t in [*self.grokked_outcome_tokens, *self.labels]
                    for s in ("past", "future")
                ),
            ).collect()
            logger.info(f"{split}: {rates.to_dicts()[0]}")


def winnow(tokenized_output, config=None, demo_clock_hours=None, counts_only=False):
    cfg = merge_config("winnowing.yaml", config)
    if demo_clock_hours:  # demo pivot: move the cut later (or earlier) by N hours
        spec = cfg.threshold.get("after_first_occurrence")
        if not spec:
            raise ValueError(
                "--demo-clock-hours needs threshold.after_first_occurrence"
            )
        spec.offset_s = int(round(float(demo_clock_hours) * 3600))
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    Winnower(root, cfg, load_vocab(root)["lookup"]).save_all(counts_only)


app = typer.Typer(add_completion=False)


@app.command()
def cli(
    tokenized_output: Annotated[
        pathlib.Path, typer.Argument(help="tokenized output folder (icutwin-tokenize)")
    ],
    config: Annotated[
        Optional[pathlib.Path],
        typer.Option("--config", "-c", help="winnowing.yaml overrides"),
    ] = None,
    demo_clock_hours: Annotated[
        Optional[float],
        typer.Option(
            "--demo-clock-hours",
            help="demo pivot: hours added to the 24 h after ICU arrival (the cut)",
        ),
    ] = None,
    counts_only: Annotated[
        bool,
        typer.Option(
            "--counts-only",
            help="log the number of stays per split, not the outcome rates "
            "(a small ward: rates are clinical values, logs hold counts only)",
        ),
    ] = False,
):
    """Cut the stays at the prediction time and flag outcomes."""
    winnow(tokenized_output, config, demo_clock_hours, counts_only)


def main():
    app()


if __name__ == "__main__":
    main()

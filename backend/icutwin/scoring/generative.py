#!/usr/bin/env python3

"""
generative predictions on held-out data: MC (M0), SCOPE (M1) and REACH (M2)
from sampled futures; writes scores-generative-<model>.parquet
(NVIDIA + sglang only: `uv sync --extra model --extra gen`)

Based on cotorra's generative scorer (github.com/bbj-lab/cotorra) and the SCOPE /
REACH estimators of Solo et al. 2026 (arXiv:2602.03730, quick_sco_re/); see
ACKNOWLEDGMENTS.md.
"""

import asyncio
import dataclasses
import fnmatch
import math
import pathlib
from typing import Annotated, Optional

import numpy as np
import polars as pl
import polars.selectors as cs
import tqdm
import typer

from icutwin.common import load_vocab, logger, merge_config
from icutwin.scoring.metrics import summarize_preds
from icutwin.scoring.quick_sco_re import (
    GenerationConfig,
    PatientResults,
    TrajectoryType,
    create_engine,
    generate_m2_from_m1_trajectory,
    generate_trajectories,
    score_trajectory,
)


def build_generation_config(
    cfg, vocab: dict[str, int], tracked_names: list[str], tracked_ids: list[int]
) -> GenerationConfig:
    """Build a GenerationConfig for inline multi-outcome SCOPE/REACH scoring.

    `tracked_names`/`tracked_ids` are the outcome tokens discovered from
    `score.target_tokens`; all other generation settings come from `cfg.generation`
    (and the shared `cfg.score.end_tokens`/`suppressed_tokens`).
    """
    score_cfg = cfg.score
    gen_cfg = cfg.get("generation", {})

    end_ids: set[int] = {
        tid
        for name in score_cfg.get("end_tokens", [])
        if (tid := vocab.get(name)) is not None
    }
    for prefix in gen_cfg.get("end_tokens", {}).get("prefixes", []):
        end_ids |= {tid for name, tid in vocab.items() if name.startswith(prefix)}

    suppressed_ids = [
        tid
        for name in score_cfg.get("suppressed_tokens", [])
        if (tid := vocab.get(name)) is not None
    ]

    ts = gen_cfg.get("time_stopping", {})
    trunc_id: int | None = None
    token_id_to_minutes: dict[int, float] = {}
    max_time = None
    time_check_interval = ts.get("time_check_interval", 100)

    if ts.get("enabled", False):
        trunc_name = ts.get("trunc_token", "TRUNC")
        trunc_id = vocab.get(trunc_name)
        if trunc_id is None:
            raise ValueError(
                f"time_stopping.trunc_token '{trunc_name}' not found in vocabulary"
            )
        max_time = ts.get("max_time_minutes")
        for tok_name, bounds in ts.get("time_token_bounds", {}).items():
            if (tid := vocab.get(tok_name)) is not None:
                lo, hi = bounds
                token_id_to_minutes[tid] = math.sqrt(lo * hi)
        if trunc_id in suppressed_ids:
            suppressed_ids.remove(trunc_id)

    return GenerationConfig(
        max_len=score_cfg.max_len,
        n_samp=score_cfg.n_samp,
        target_event_id=tracked_ids[0],
        end_token_ids=end_ids,
        suppressed_ids=suppressed_ids,
        temperature=gen_cfg.get("temperature", 1.0),
        trunc_id=trunc_id,
        token_id_to_minutes=token_id_to_minutes,
        max_time=max_time,
        time_check_interval=time_check_interval,
        tracked_ids=tracked_ids,
        tracked_names=tracked_names,
    )


def outcome_configs(
    gen_config: GenerationConfig, outcome_ids: list[int]
) -> list[GenerationConfig]:
    """one config per outcome, tracking and targeting only that outcome: a shared
    config would put every outcome's occurred flag and SCOPE/REACH estimate in
    the same sample list, mixing the outcomes together"""
    names = gen_config.tracked_names or [None] * len(gen_config.tracked_ids)
    name_of = dict(zip(gen_config.tracked_ids, names))
    return [
        dataclasses.replace(
            gen_config,
            target_event_id=oid,
            tracked_ids=[oid],
            tracked_names=[name_of.get(oid)],
        )
        for oid in outcome_ids
    ]


def within_clocks(output_ids, target_id: int, clock_ids: set[int], n: int) -> bool:
    """team7 hardware pivot: did target_id appear before the n-th clock token?

    The tokenizer puts a CLCK//HH token in every timeline at fixed local hours
    (every 4 h with the shipped spec), events or not, so the n-th clock of a
    sampled future marks n x 4 h. That gives a time horizon without a TRUNC token.
    """
    seen = 0
    for tok in output_ids:
        if tok == target_id:
            return True
        if tok in clock_ids:
            seen += 1
            if seen >= n:
                return False
    return False


def aggregate_inline_results(
    trajectories: list,
    num_patients: int,
    config: GenerationConfig,
    horizon_clocks: dict[int, int] | None = None,
    clock_ids: set[int] | None = None,
) -> list[PatientResults]:
    """Build per-patient results from inline SCOPE/REACH estimates on trajectories.

    Looks up the target_event_id in each trajectory's inline_tracked_ids to
    locate the SCOPE/REACH index. M0 is derived from timeline_terminating_id.
    """
    target_id = config.target_event_id
    results = {i: PatientResults() for i in range(num_patients)}

    for traj in trajectories:
        if traj.inline_tracked_ids is None:
            continue
        try:
            k = traj.inline_tracked_ids.index(target_id)
        except ValueError:
            continue

        if traj.traj_type == TrajectoryType.M1:
            if traj.occurred_flag is not None:
                m0 = bool(traj.occurred_flag[k])
            else:
                m0 = traj.timeline_terminating_id == target_id
            results[traj.patient_idx].m0_samples.append(m0)
            for hours, n in (horizon_clocks or {}).items():
                hit = within_clocks(traj.output_ids, target_id, clock_ids or set(), n)
                results[traj.patient_idx].horizon_samples.setdefault(hours, []).append(
                    hit
                )
            scope = (
                float(traj.scope_estimates[k])
                if traj.scope_estimates is not None
                else 0.0
            )
            results[traj.patient_idx].m1_samples.append(scope)
        else:
            reach = (
                float(traj.reach_estimates[k])
                if traj.reach_estimates is not None
                else 0.0
            )
            results[traj.patient_idx].m2_samples.append(reach)

    return [results[i] for i in range(num_patients)]


class GenerativeScorer:
    def __init__(self, cfg, lookup: dict, model_home: pathlib.Path):
        self.cfg, self.model_home = cfg, pathlib.Path(model_home).expanduser().resolve()
        self.vocab: dict[str, int] = {
            str(name): int(tid) for name, tid in lookup.items()
        }

        self.grokked_outcome_tokens = [
            x
            for x in self.vocab
            if any(fnmatch.fnmatch(x, p) for p in self.cfg.score.target_tokens)
        ]
        if not self.grokked_outcome_tokens:
            raise ValueError(
                "No vocabulary tokens matched score.target_tokens="
                f"{list(self.cfg.score.target_tokens)!r}"
            )
        logger.info(f"Processed expressions to generate {self.grokked_outcome_tokens=}")
        tracked_ids = [self.vocab[name] for name in self.grokked_outcome_tokens]

        self.gen_config = build_generation_config(
            self.cfg, self.vocab, self.grokked_outcome_tokens, tracked_ids
        )
        gen_cfg = self.cfg.get("generation", {})
        self.methods = gen_cfg.get("methods", ["M1", "M2"])
        engine_cfg = self.cfg.get("engine", {})
        self.chunk_size = engine_cfg.get("patient_chunk_size", 64)
        # team7: optional time horizons (hours) counted on CLCK tokens
        self.clock_ids = {i for n, i in self.vocab.items() if n.startswith("CLCK//")}
        hours = list(self.cfg.score.get("horizons_hours", []) or [])
        if hours and not self.clock_ids:
            raise ValueError("score.horizons_hours needs CLCK// tokens in the vocab")
        per_clock = 24 / len(self.clock_ids) if self.clock_ids else 0
        self.horizon_clocks = {int(h): max(1, math.ceil(h / per_clock)) for h in hours}

        self.engine = create_engine(
            model_path=str(self.model_home),
            max_len=self.gen_config.max_len,
            use_time_horizon=self.gen_config.max_time is not None
            and self.gen_config.trunc_id is not None,
            mem_fraction=engine_cfg.get("mem_fraction", 0.85),
        )

    shard: tuple[int, int] | None = None  # (i, n): score every n-th stay from i

    def load(self, root: pathlib.Path):
        """the held-out prompts"""
        self.ds = pl.read_parquet(root / "held_out_for_inference.parquet")
        if self.shard:  # team7 hardware pivot: split stays across GPUs (task array)
            i, n = self.shard
            self.ds = (
                self.ds.with_row_index("_r").filter(pl.col("_r") % n == i).drop("_r")
            )
        subject_ids = self.ds.select("hospitalization_id").to_series().to_list()
        self.tokens_past = self.ds.select("tokens_past").to_series().to_list()

        self.overflow = self.cfg.get("prompt_overflow", "truncate_left")
        max_len = self.gen_config.max_len
        self.final_tokens = []
        self.final_ids = []
        self.keep_mask = []
        n_dropped = 0
        n_truncated = 0
        for sid, toks in zip(subject_ids, self.tokens_past):
            if len(toks) > max_len:
                if self.overflow == "drop":
                    n_dropped += 1
                    self.keep_mask.append(False)
                    continue
                elif self.overflow == "truncate_left":
                    toks = toks[-max_len:]
                    n_truncated += 1
            self.final_tokens.append(toks)
            self.final_ids.append(sid)
            self.keep_mask.append(True)
        if n_dropped:
            logger.info(f"Dropped {n_dropped} stays with prompts > {max_len} tokens")
        if n_truncated:
            logger.info(f"Left-truncated {n_truncated} prompts to {max_len} tokens")

        kept = np.array(self.keep_mask)
        self.outcome_past_masks: list[np.ndarray] = []
        # team7 hardware pivot: outcomes listed in score.repeat_ok are scored even
        # when they already happened before the cut (e.g. a second ward transfer:
        # a patient who came from the ward can still leave the ICU for it)
        repeat_ok = list(self.cfg.score.get("repeat_ok", []) or [])
        for evt_name in self.grokked_outcome_tokens:
            past_col = f"{evt_name}_past"
            if any(fnmatch.fnmatch(evt_name, p) for p in repeat_ok):
                mask = np.zeros(len(self.final_ids), dtype=bool)
            elif past_col in self.ds.columns:
                mask = self.ds[past_col].to_numpy().astype(bool)[kept]
            else:
                mask = np.zeros(len(self.final_ids), dtype=bool)
            self.outcome_past_masks.append(mask)

    async def sco_re(self) -> list[list[PatientResults]]:
        """Run one inline generation pass over the whole cohort, tracking every
        outcome in `self.grokked_outcome_tokens` simultaneously."""
        outcome_ids = self.gen_config.tracked_ids
        per_outcome = outcome_configs(self.gen_config, outcome_ids)
        n_patients = len(self.final_ids)
        n_outcomes = len(self.grokked_outcome_tokens)
        all_results: list[list[PatientResults]] = [[] for _ in range(n_outcomes)]
        per_outcome_m2_tokens: list[int] = [0] * n_outcomes
        per_outcome_m2_count: list[int] = [0] * n_outcomes

        with tqdm.tqdm(total=n_patients, desc="Generating") as pbar:
            for chunk_start in range(0, n_patients, self.chunk_size):
                chunk_end = min(chunk_start + self.chunk_size, n_patients)
                chunk_tokens = self.final_tokens[chunk_start:chunk_end]

                # Generate the initial M1 chunk
                chunk_m1 = await generate_trajectories(
                    self.engine,
                    self.gen_config,
                    chunk_tokens,
                    ["M1"],
                    stop_at_tracked_events=False,
                )

                outcome_m1_results_list = [
                    aggregate_inline_results(
                        chunk_m1,
                        len(chunk_tokens),
                        oc,
                        self.horizon_clocks,
                        self.clock_ids,
                    )
                    for oc in per_outcome
                ]
                for k, om1r in enumerate(outcome_m1_results_list):
                    all_results[k].extend(om1r)

                # M2 regen within this batch — avoids accumulating all regen
                # requests and triggering them in one giant post-loop gather.
                if "M2" in self.methods:
                    chunk_regen: list[tuple] = []
                    for traj in chunk_m1:
                        global_idx = chunk_start + traj.patient_idx
                        if (
                            traj.inline_tracked_ids is None
                            or traj.reach_estimates is None
                        ):
                            continue
                        for k, (evt_id, oc) in enumerate(zip(outcome_ids, per_outcome)):
                            # skip regenning this outcome if it occurred in the prefix
                            if self.outcome_past_masks[k][global_idx]:
                                continue
                            try:
                                ki = traj.inline_tracked_ids.index(evt_id)
                            except ValueError:
                                continue
                            # Prefer occurred_flag (O(1), correct for time-truncated
                            # trajectories where output_ids is already trimmed).
                            if traj.occurred_flag is not None:
                                evt_occurred = bool(traj.occurred_flag[ki])
                            else:
                                evt_occurred = evt_id in traj.output_ids
                            if evt_occurred:
                                chunk_regen.append((traj, global_idx, k, oc))
                            else:
                                all_results[k][global_idx].m2_samples.append(
                                    float(traj.reach_estimates[ki])
                                )

                    if chunk_regen:
                        m2_trajs = list(
                            await asyncio.gather(
                                *[
                                    generate_m2_from_m1_trajectory(
                                        self.engine,
                                        oc,
                                        traj,
                                        self.final_tokens[global_idx],
                                    )
                                    for traj, global_idx, _, oc in chunk_regen
                                ]
                            )
                        )
                        scored_m2 = list(
                            await asyncio.gather(
                                *[
                                    score_trajectory(
                                        self.engine,
                                        oc,
                                        m2_traj,
                                        self.final_tokens[global_idx],
                                    )
                                    for (_, global_idx, _, oc), m2_traj in zip(
                                        chunk_regen, m2_trajs
                                    )
                                ]
                            )
                        )
                        for (traj, global_idx, k, oc), st in zip(
                            chunk_regen, scored_m2
                        ):
                            all_results[k][global_idx].m2_samples.append(st.score)
                            per_outcome_m2_tokens[k] += st.trajectory.n_new_tokens or 0
                            per_outcome_m2_count[k] += 1

                pbar.update(len(chunk_tokens))

        return all_results

    async def score(self):
        all_results = await self.sco_re()
        orig_idx = np.flatnonzero(self.keep_mask)
        n = len(self.tokens_past)
        res = {}

        for k, tt in enumerate(tqdm.tqdm(self.grokked_outcome_tokens)):
            results_k = all_results[k]
            # Patients where this outcome already occurred in the past are
            # excluded from that outcome's scores (NaN).
            for i, is_past in enumerate(self.outcome_past_masks[k]):
                if is_past:
                    results_k[i] = PatientResults()

            m0 = np.nan * np.ones(n)
            m1 = np.nan * np.ones(n)
            m2 = np.nan * np.ones(n)
            m0[orig_idx] = [
                np.mean(r.m0_samples) if r.m0_samples else np.nan for r in results_k
            ]
            m1[orig_idx] = [
                np.mean(r.m1_samples) if r.m1_samples else np.nan for r in results_k
            ]
            m2[orig_idx] = [
                np.mean(r.m2_samples) if r.m2_samples else np.nan for r in results_k
            ]

            res[f"{tt}_mc_score"] = m0
            for hours in self.horizon_clocks:
                mh = np.nan * np.ones(n)
                mh[orig_idx] = [
                    np.mean(r.horizon_samples[hours])
                    if r.horizon_samples.get(hours)
                    else np.nan
                    for r in results_k
                ]
                res[f"{tt}_mc{hours}h_score"] = mh
            res[f"{tt}_scope_score"] = m1
            res[f"{tt}_reach_score"] = m2

        return res

    def save_all(self, root: pathlib.Path, verbose: bool = True):
        self.load(root)
        res = asyncio.run(self.score())
        tag = f"-shard{self.shard[0]}of{self.shard[1]}" if self.shard else ""
        out = root / f"scores-generative-{self.model_home.name}{tag}.parquet"
        (
            df_res := self.ds.select(~cs.by_dtype(pl.List)).with_columns(
                pl.from_dict(res)
            )
        ).write_parquet(out)
        logger.info(out.name)
        if verbose:
            summarize_preds(logger, df_res, self.grokked_outcome_tokens)


def parse_shard(shard: str | None) -> tuple[int, int] | None:
    """'0/2' -> (0, 2); None -> None (score every stay)."""
    if not shard:
        return None
    i, n = (int(x) for x in shard.split("/"))
    if not 0 <= i < n:
        raise ValueError(f"shard {shard!r}: need 0 <= i < n")
    return i, n


def gen_score(tokenized_output, model_home, config=None, shard=None):
    cfg = merge_config("scoring.yaml", config)
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    scorer = GenerativeScorer(cfg, load_vocab(root)["lookup"], model_home)
    scorer.shard = parse_shard(shard)
    scorer.save_all(root)


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
    shard: Annotated[
        Optional[str],
        typer.Option("--shard", help="i/n: score every n-th stay from i (one per GPU)"),
    ] = None,
):
    """MC / SCOPE / REACH scores on held_out (needs sglang)."""
    gen_score(tokenized_output, model_home, config, shard)


def main():
    app()


if __name__ == "__main__":
    main()

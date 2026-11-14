# From quick_sco_re, SCOPE and REACH optimized inference (Luke Solo et al.),
# github.com/lukesolo-ml/SCOPE_REACH_optimized_inference @ 1b0af76, file quick_sco_re/scheduler.py;
# the estimators of Solo et al. 2026, arXiv:2602.03730, as used by cotorra. See ACKNOWLEDGMENTS.md.
# Change from upstream: sglang is imported lazily, so the module loads without it (Mac/CPU tests).
"""
Interleaved scheduler for SCOPE/REACH timeline generation and scoring.

Orchestrates two-phase processing:
  Phase 1: Generate M1 and M2 trajectories interleaved by patient for
           radix cache locality.
  Phase 2: Score trajectories via prefill-only logprob extraction.
TODO: Re-implement a new version of generate and score interleaved
The scheduler supports three modes of operation:
  - generate_only: Generate trajectories and return/save them without scoring.
  - generate_and_score: Generate then immediately score (keeps radix cache hot).
  - score_only: Score previously-saved trajectories loaded from disk.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Sequence


from .generation import generate_trajectory, generate_m2_from_m1_trajectory
from .scoring import score_trajectory
from .structures import (
    GeneratedTrajectory,
    GenerationConfig,
    PatientResults,
    ScoredTrajectory,
    TrajectoryType,
)

logger = logging.getLogger(__name__)

from transformers import AutoConfig  # noqa: E402

_orig_from_pretrained = AutoConfig.from_pretrained


def _from_pretrained(*a, **kw):
    """load an HF config, letting SGLang read global values for per-layer keys

    SGLang has no notion of transformers 5 per-layer configs: it reads
    config.head_dim / heads straight off the config for every layer. Our Gemma4
    checkpoints are heterogeneous (full attention: head_dim 512 on 16 heads;
    sliding: 64 on 6), so this returns the global head_dim and leaves Gemma4's
    per-layer choice (swa_head_dim for sliding) intact via create_engine().
    """
    config = _orig_from_pretrained(*a, **kw)
    if getattr(config, "is_heterogeneous", False):
        config.allow_global_per_layer_attribute_access = True
    return config


AutoConfig.from_pretrained = _from_pretrained
_PERSISTENT_PATCH = True


def create_engine(model_path, max_len, use_time_horizon = False, mem_fraction = 0.8):
    import sglang as sgl

    # SGLang's Gemma4 layer takes config.head_dim for full attention and
    # swa_head_dim for sliding attention, with one head count for both. This
    # checkpoint widens head_dim instead of the head count: sliding layers are
    # 6 heads x 64 (= hidden 384), full-attention layers are 6 x 512 (q_proj
    # 3072). So point the two globals at those values; heads stay as shipped.
    import json, pathlib

    cfg_path = pathlib.Path(model_path) / "config.json"
    if cfg_path.is_file():
        raw = json.loads(cfg_path.read_text())
        per = raw.get("per_layer_config") or {}
        if per:
            full = [
                i for i, t in enumerate(raw["layer_types"]) if t == "full_attention"
            ]
            # keys are zero-padded strings ("05"), so match on the int value
            by_idx = {int(k): v for k, v in per.items()}
            fdims = {(by_idx.get(i) or {}).get("head_dim") for i in full} - {None}
            if full and len(fdims) == 1:
                fd = fdims.pop()
                base = _orig_from_pretrained

                def patched(*a, **kw):
                    obj = base(*a, **kw)
                    if getattr(obj, "is_heterogeneous", False):
                        obj.allow_global_per_layer_attribute_access = True
                    obj.head_dim, obj.swa_head_dim = fd, raw["head_dim"]
                    return obj

                AutoConfig.from_pretrained = patched

    return sgl.Engine(
        model_path=model_path,
        skip_tokenizer_init=True,
        disable_overlap_schedule=use_time_horizon,
        enable_custom_logit_processor=use_time_horizon,
        context_length=max_len,
        attention_backend='triton',
        disable_cuda_graph=use_time_horizon,
        disable_prefill_cuda_graph=True,  # prefill graph capture trips on Gemma4's per-layer head_dim
        sampling_backend="pytorch",
        mem_fraction_static=mem_fraction,
        log_level='warning',
    )

async def generate_trajectories(
    engine: sgl.Engine,
    config: GenerationConfig,
    patient_tokens: Sequence[list[int]],
    methods: list[str] = ["M1", "M2"],
    stop_at_tracked_events: bool = True,
) -> list[GeneratedTrajectory]:
    """Generate all M1 and M2 trajectories for a batch of patients.

    Trajectories are interleaved by patient (M1_p0_s0, M2_p0_s0, M1_p0_s1,
    M2_p0_s1, ..., M1_p1_s0, ...) to maximize SGLang radix cache hits on
    shared patient prefixes.

    Args:
        engine: SGLang inference engine.
        config: Generation configuration.
        patient_tokens: List of tokenized patient timelines (one per patient).
        stop_at_tracked_events: If False, M1 trajectories run to their natural
            end token rather than stopping early when a tracked event occurs.

    Returns:
        List of all generated trajectories.
    """
    gen_tasks = []
    for patient_idx, tokens in enumerate(patient_tokens):
        for sample_idx in range(config.n_samp):
            if "M1" in methods:
                gen_tasks.append(
                    generate_trajectory(
                        engine, config, tokens, patient_idx, sample_idx, TrajectoryType.M1,
                        stop_at_tracked_events=stop_at_tracked_events,
                    )
                )
            if "M2" in methods:
                gen_tasks.append(
                    generate_trajectory(
                        engine, config, tokens, patient_idx, sample_idx, TrajectoryType.M2
                    )
                )

    logger.info(f"Generating {len(gen_tasks)} trajectories...")
    start = time.time()
    trajectories = await asyncio.gather(*gen_tasks)
    elapsed = time.time() - start
    logger.info(f"Generation completed in {elapsed:.2f}s")

    return list(trajectories)

async def generate_m2_from_m1_trajectories(
    engine: sgl.Engine,
    config: GenerationConfig,
    m1_trajectories: Sequence[GeneratedTrajectory],
    patient_tokens: Sequence[list[int]],
) -> list[GeneratedTrajectory]:
    """Derive M2 trajectories from completed M1 trajectories.

    For each M1 trajectory: if the target event was not generated, wraps the
    output as M2. If the target event was generated, truncates before it and
    regenerates the continuation with the event suppressed.

    Args:
        engine: SGLang inference engine.
        config: Generation configuration.
        m1_trajectories: Completed M1 trajectories.
        patient_tokens: Original patient prompts indexed by patient_idx.

    Returns:
        List of M2 trajectories, one per input M1 trajectory.
    """
    tasks = [
        generate_m2_from_m1_trajectory(
            engine, config, traj, patient_tokens[traj.patient_idx]
        )
        for traj in m1_trajectories
    ]
    logger.info(f"Deriving {len(tasks)} M2 trajectories from M1...")
    start = time.time()
    m2_trajectories = await asyncio.gather(*tasks)
    elapsed = time.time() - start
    logger.info(f"M2 derivation completed in {elapsed:.2f}s")
    return list(m2_trajectories)


async def score_trajectories(
    engine: sgl.Engine,
    config: GenerationConfig,
    trajectories: Sequence[GeneratedTrajectory],
    patient_tokens: Sequence[list[int]],
    truncate_again: bool = False,
) -> list[ScoredTrajectory]:
    """Score a collection of trajectories by extracting logprobs.

    Args:
        engine: SGLang inference engine.
        config: Generation configuration.
        trajectories: Previously generated trajectories.
        patient_tokens: Original patient prompts (indexed by patient_idx).

    Returns:
        List of scored trajectories.
    """
    score_tasks = [
        score_trajectory(engine, config, traj, patient_tokens[traj.patient_idx], truncate_again=truncate_again)
        for traj in trajectories
    ]

    logger.info(f"Scoring {len(score_tasks)} trajectories...")
    start = time.time()
    scored = await asyncio.gather(*score_tasks)
    elapsed = time.time() - start
    logger.info(f"Scoring completed in {elapsed:.2f}s")

    return list(scored)


def aggregate_results(
    scored_trajectories: Sequence[ScoredTrajectory],
    num_patients: int,
    target_event_id
) -> list[PatientResults]:
    """Aggregate scored trajectories into per-patient results.

    Args:
        scored_trajectories: All scored trajectories.
        num_patients: Total number of patients.

    Returns:
        List of PatientResults, one per patient (indexed by patient_idx).
    """
    results = {i: PatientResults() for i in range(num_patients)}

    for st in scored_trajectories:
        traj = st.trajectory
        if traj.traj_type == TrajectoryType.M1:
            results[traj.patient_idx].m0_samples.append(
                traj.timeline_terminating_id == target_event_id
            )
            results[traj.patient_idx].m1_samples.append(st.score)
        else:  
            results[traj.patient_idx].m2_samples.append(st.score)

    return [results[i] for i in range(num_patients)]

async def generate_and_score(
    engine: sgl.Engine,
    config: GenerationConfig,
    patient_tokens: Sequence[list[int]],
    target_token_id,
    methods: list[str] = ["M1", "M2"]
) -> tuple[list[GeneratedTrajectory], list[PatientResults]]:
    """Generate and immediately score all trajectories.

    This is the recommended mode when you want scores and the engine is
    already running — scoring immediately after generation keeps the radix
    cache hot for the prefill scoring pass.

    Args:
        engine: SGLang inference engine.
        config: Generation configuration.
        patient_tokens: List of tokenized patient timelines.

    Returns:
        Tuple of (all generated trajectories, per-patient aggregated results).
    """
    total_start = time.time()

    m1_trajectories = await generate_trajectories(engine, config, patient_tokens, ["M1"])

    if "M2" in methods:
        m2_trajectories = await generate_m2_from_m1_trajectories(
            engine, config, m1_trajectories, patient_tokens
        )
        trajectories = m1_trajectories + list(m2_trajectories)
    else:
        trajectories = m1_trajectories

    scored = await score_trajectories(engine, config, trajectories, patient_tokens)
    results = aggregate_results(scored, num_patients=len(patient_tokens), target_event_id=target_token_id)

    total_time = time.time() - total_start
    logger.info(f"Total generate-and-score time: {total_time:.2f}s")

    return trajectories, results

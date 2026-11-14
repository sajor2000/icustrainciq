#!/usr/bin/env python3
"""Prepare or check a restricted 25-room cache from existing held-out tokens.

This is a CPU-only selection step, not raw-CLIF ETL, training or probe fitting.
It never prints identifiers or token rows. Do not run against patient data from
an agent session; an authorized operator runs it within restricted storage.
"""

import argparse
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.demo_context import ContextUnavailable, read_roster  # noqa: E402

SPLITS = ("train", "tuning", "held_out")


def roster_digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_cache(root: pathlib.Path, roster: pathlib.Path) -> dict:
    """Refuse changed rosters and caches containing any other hospitalization."""
    import polars as pl

    ids = set(read_roster(roster))
    try:
        marker = json.loads((root / "lookahead_cohort.json").read_text())
        if (
            marker["schema_version"] != 1
            or marker["roster_size"] != 25
            or marker["split"] != "held_out"
            or marker["roster_sha256"] != roster_digest(roster)
        ):
            raise ValueError
        for split in SPLITS:
            got = set(
                pl.scan_parquet(root / f"tokens_{split}.parquet")
                .select("hospitalization_id")
                .unique()
                .collect()["hospitalization_id"]
                .to_list()
            )
            if got != (ids if split == "held_out" else set()):
                raise ValueError
        if (
            hashlib.sha256((root / "vocab.yaml").read_bytes()).hexdigest()
            != marker["vocab_sha256"]
        ):
            raise ValueError
    except Exception:
        raise ContextUnavailable(
            "Selected-25 cache is missing or inconsistent"
        ) from None
    return {"checked": True, "roster_size": 25, "split": "held_out"}


def prepare(source: pathlib.Path, roster: pathlib.Path, out: pathlib.Path) -> dict:
    import polars as pl

    ids = list(read_roster(roster))
    source, out = source.resolve(), out.resolve()
    if any(
        part.lower() in {"dropbox", "cloudstorage", "mobile documents"}
        for part in out.parts
    ):
        raise ContextUnavailable(
            "Selected-25 cache must remain on restricted unsynced storage"
        )
    if out.exists() or out.is_relative_to(source) or source.is_relative_to(out):
        raise ContextUnavailable("Choose a new cache directory outside the source root")
    # All selected stays must be held out, and must not also occur in training/tuning.
    held = pl.scan_parquet(source / "tokens_held_out.parquet").filter(
        pl.col("hospitalization_id").cast(pl.String).is_in(ids)
    )
    if not {
        "hospitalization_id",
        "event_time",
        "token_id",
        "value",
        "position_id",
    }.issubset(held.collect_schema().names()):
        raise ContextUnavailable(
            "Prepared held-out tokens lack required tokenizer columns"
        )
    got = set(
        held.select("hospitalization_id")
        .unique()
        .collect()["hospitalization_id"]
        .to_list()
    )
    if got != set(ids):
        raise ContextUnavailable("Selected roster is not complete in held-out tokens")
    for split in ("train", "tuning"):
        overlap = (
            pl.scan_parquet(source / f"tokens_{split}.parquet")
            .filter(pl.col("hospitalization_id").cast(pl.String).is_in(ids))
            .select(pl.len())
            .collect()
            .item()
        )
        if overlap:
            raise ContextUnavailable(
                "Selected roster overlaps training or tuning tokens"
            )
    vocab = (source / "vocab.yaml").read_bytes()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix=".lookahead-cohort-", dir=out.parent))
    try:
        held.sink_parquet(tmp / "tokens_held_out.parquet")
        # Empty splits preserve the tokenizer schema without copying other stays.
        empty = held.limit(0).collect()
        for split in ("train", "tuning"):
            empty.write_parquet(tmp / f"tokens_{split}.parquet")
        (tmp / "vocab.yaml").write_bytes(vocab)
        count = (
            pl.scan_parquet(tmp / "tokens_held_out.parquet")
            .select(pl.len())
            .collect()
            .item()
        )
        (tmp / "lookahead_cohort.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "roster_size": 25,
                    "split": "held_out",
                    "roster_sha256": roster_digest(roster),
                    "vocab_sha256": hashlib.sha256(vocab).hexdigest(),
                    "token_rows": count,
                }
            )
        )
        check_cache(tmp, roster)
        tmp.rename(out)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return {
        "prepared": True,
        "roster_size": 25,
        "split": "held_out",
        "token_rows": count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--source", type=pathlib.Path)
    parser.add_argument("--roster", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.check and args.source is None:
        parser.error("--source is required unless --check is used")
    try:
        result = (
            check_cache(args.out, args.roster)
            if args.check
            else prepare(args.source, args.roster, args.out)
        )
    except Exception:
        # Third-party IO errors may carry identifiers or row fragments: suppress them.
        raise SystemExit(
            "Selected-25 cache preparation/check failed; inspect inputs privately"
        ) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()

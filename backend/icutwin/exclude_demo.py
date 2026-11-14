#!/usr/bin/env python3

"""
keep the MIMIC-IV Demo cohort out of training, tuning and held-out: the demo is
the openly licensed virtual ward replayed on stage and must never be seen by the
model; run after `icutwin-tokenize`. It filters splits.parquet AND the
tokens_{split}.parquet files in place: training and the winnower read the token
files, so filtering the splits alone would leave the demo stays in training
"""

import json
import pathlib
from typing import Annotated

import polars as pl
import typer

from icutwin.tokenizer.helpers import HOSP, PAT, SPLITS, Logger

logger = Logger(
    "icutwin"
)  # not icutwin.common: that pulls in transformers (model extra)


class DemoExcludedError(RuntimeError):
    """the demo cohort cannot be identified, so no split is safe to keep"""


def demo_ids(demo_dir: pathlib.Path) -> tuple[pl.DataFrame, pl.DataFrame]:
    """the demo's hospitalizations and patients, as two one-column frames"""
    files = {f: demo_dir / f"clif_{f}.parquet" for f in ("hospitalization", "patient")}
    for f in files.values():
        if not f.is_file():
            raise DemoExcludedError(
                f"{f} missing; point --demo-dir at CLIF demo tables"
            )
    hosp = pl.read_parquet(files["hospitalization"], columns=[HOSP, PAT])
    pat = (
        pl.read_parquet(files["patient"], columns=[PAT])[PAT]
        .cast(pl.String)
        .unique()
        .to_frame()
    )
    return hosp.select(pl.col(HOSP).cast(pl.String)), pat


def drop_from_tokens(root: pathlib.Path, demo: set[str]) -> tuple[int, list[str]]:
    """remove the demo stays' rows from every tokens_{split}.parquet (written to a
    temporary file, then renamed) and delete the {split}_for_inference.parquet files,
    which were cut from the old token files. Returns (rows removed, files checked)."""
    removed, seen = 0, []
    for s in SPLITS:
        f = root / f"tokens_{s}.parquet"
        if not f.is_file():
            continue
        seen.append(f.stem)
        is_demo = pl.col(HOSP).cast(pl.String).is_in(list(demo))
        n = pl.scan_parquet(f).filter(is_demo).select(pl.len()).collect().item()
        if n:
            tmp = f.with_name(f.name + ".tmp")
            pl.scan_parquet(f).filter(~is_demo).sink_parquet(tmp)
            tmp.replace(f)
            removed += n
            logger.info(f"{f.name}: {n:,} token rows of demo stays removed")
        stale = root / f"{s}_for_inference.parquet"
        if n and stale.is_file():
            stale.unlink()
            logger.warning(f"{stale.name} removed: run icutwin-winnow again")
    if not seen:
        logger.warning("no tokens_{split}.parquet here: only splits.parquet filtered")
    return removed, sorted(seen)


def exclude_demo(tokenized_output, demo_dir) -> dict[str, int]:
    """drop every demo stay, and every stay of a demo patient, from the splits and
    from the token files; rewrites splits.parquet, tokens_{split}.parquet and
    qc_report.json, removes the winnowed files made from the old token files, and
    returns the per-split counts"""
    root = pathlib.Path(tokenized_output).expanduser().resolve()
    demo_hosp, demo_pat = demo_ids(pathlib.Path(demo_dir).expanduser().resolve())
    splits = pl.read_parquet(root / "splits.parquet")
    demo = set(demo_hosp[HOSP].to_list())

    # a demo patient's other stays leave too, when the reference table can be read
    ref = root / "clif_hospitalization.parquet"
    if ref.is_file():
        owner = (
            pl.read_parquet(ref, columns=[HOSP, PAT])
            .select(pl.col(HOSP).cast(pl.String), pl.col(PAT).cast(pl.String))
            .join(demo_pat, on=PAT, how="semi")
        )
        demo |= set(owner[HOSP].to_list())
    else:
        logger.warning(f"{ref} not found: excluding demo stays only, not all stays of")
        logger.warning("a demo patient; copy clif_hospitalization.parquet next to the")
        logger.warning("tokens to exclude by patient")

    hit = splits.filter(pl.col(HOSP).cast(pl.String).is_in(list(demo)))
    # the token files first: a folder whose splits were already filtered by the older
    # version of this script (splits only) still has the demo stays in its tokens
    token_rows, token_files = drop_from_tokens(root, demo)
    if hit.is_empty() and not token_rows:
        raise DemoExcludedError(
            "no demo stay found in splits.parquet or the token files; the demo ids "
            "do not match this tokenized output, so the exclusion would silently do "
            "nothing"
        )
    logger.info(f"{hit.height:,} demo stays out of every split")

    kept = splits.filter(~pl.col(HOSP).cast(pl.String).is_in(list(demo)))
    kept.write_parquet(root / "splits.parquet")
    counts = {s: 0 for s in SPLITS} | dict(kept["split"].value_counts().iter_rows())
    qc_path = root / "qc_report.json"
    if qc_path.is_file():
        qc = json.loads(qc_path.read_text())
        qc["demo_excluded"] = {
            "stays": hit.height,
            "by": "patient" if ref.is_file() else "stay",
            "token_rows": token_rows,
            "token_files": token_files,
        }
        qc["split"] |= {s: counts.get(s, 0) for s in SPLITS}
        qc_path.write_text(json.dumps(qc, indent=2))
    return {s: counts.get(s, 0) for s in SPLITS}


app = typer.Typer(add_completion=False)


@app.command()
def cli(
    tokenized_output: Annotated[
        pathlib.Path, typer.Argument(help="tokenized output folder (icutwin-tokenize)")
    ],
    demo_dir: Annotated[
        pathlib.Path, typer.Argument(help="folder of the CLIF demo tables")
    ] = pathlib.Path("clif_demo"),
):
    """Remove the MIMIC-IV Demo cohort from every split."""
    n = exclude_demo(tokenized_output, demo_dir)
    logger.info(f"kept per split: {n}")


def main():
    app()


if __name__ == "__main__":
    main()

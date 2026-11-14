#!/usr/bin/env python3

"""
the assembler: `icutwin-tokenize pipeline` runs it

1. tables     run_table() for every module in tokenizer/tables/: each is an
              independent pipeline that writes tables/<step>.parquet and its
              summary tables/<step>.json (debug one alone: `icutwin-tokenize table`)
2. assemble   qc_report.json from the tables and their summaries;
              _events.parquet (deduplicated), the hand-off to step 4
3. split      the folds: one random 70/10/20 split of the hospitalizations
              -> splits.parquet
4. tokenize   everything that is not part of one table: header placement,
              BOS/EOS, clock and time-gap tokens, timeline order,
              vocabulary ids, min_tokens; tokens_{train,tuning,held_out}.parquet
              and vocab.yaml
"""

import datetime
import importlib
import json
import math
import pathlib
import pkgutil
import shutil

import numpy as np
import polars as pl

from icutwin.tokenizer import tables as _tables
from icutwin.tokenizer.helpers import (
    EVENTS,
    HOSP,
    SPLITS,
    TABLES,
    ClifData,
    Vocabulary,
    load_spec,
    spec_hash,
)

# step -> module: every file in tokenizer/tables/ is one step, one
# tables/<step>.parquet; a new table is a new file, nothing else (cohort first)
STEPS = {
    name: importlib.import_module(f"icutwin.tokenizer.tables.{name}")
    for name in sorted(
        (m.name for m in pkgutil.iter_modules(_tables.__path__)),
        key=lambda n: (n != "cohort", n),
    )
}
STEP_OF = {t: step for step, m in STEPS.items() for t in m.TABLES}
EVENT_COLS = (HOSP, "time", "code", "token", "value", "unit", "category_value")
QC_WARN_DROP_RATE = 0.05
COUNTS = "token_counts.json"

# stay-level tokens known before the stay starts: tokens.yaml `ordering` between
# BOS and TIME; they sit right after BOS
_ORDER = load_spec().ordering
HEADER = tuple(o for o in _ORDER[: _ORDER.index("TIME")] if o != "BOS")

_orphans = {e.table for e in load_spec().entries} - set(STEP_OF)
if _orphans:  # a spec table no module builds would silently lose its tokens
    raise RuntimeError(f"no tables/ module for spec tables {sorted(_orphans)}")

# ------------------------------------------------------------ 1. tables


def token_counts(lf: pl.LazyFrame) -> dict:
    """{table: {hospitalizations, tokens: {token: {count, hospitalizations}}}};
    `hospitalizations` = stays with at least one such token"""
    lf = lf.filter(pl.col("token").is_not_null())
    stays = lf.group_by("table").agg(pl.col(HOSP).n_unique()).collect()
    out = {t: {"hospitalizations": n, "tokens": {}} for t, n in stays.iter_rows()}
    per = lf.group_by("table", "token").agg(pl.len(), pl.col(HOSP).n_unique())
    for t, w, c, h in per.collect().iter_rows():
        out[t]["tokens"][w] = {"count": c, "hospitalizations": h}
    return out


def step_summary(clif: ClifData, step: str, f: pathlib.Path) -> dict:
    """tokens written, spec codes found, and what the data lacks"""
    entries = [e for e in clif.spec.entries if STEP_OF[e.table] == step]
    tables = {e.table for e in entries}
    n, counts = {}, {}
    if f.exists():
        table_of = {e.code: e.table for e in entries}
        counts = token_counts(
            pl.scan_parquet(f).with_columns(
                table=pl.col("code").replace_strict(table_of, default=step)
            )
        )
        n = dict(
            pl.scan_parquet(f)
            .filter(pl.col("token").is_not_null())
            .group_by("code")
            .len()
            .collect()
            .iter_rows()
        )
    for e in entries:  # every spec token of the table, 0 if the data lacks it
        t = counts.setdefault(e.table, {"hospitalizations": 0, "tokens": {}})
        for w in e.tokens():
            t["tokens"].setdefault(w, {"count": 0, "hospitalizations": 0})
    return {
        "step": step,
        "tokens": sum(n.values()),
        "codes": len(entries),
        "missing": [e.code for e in entries if e.code not in n],
        "missing_tables": sorted(tables & set(clif.missing_tables)),
        "missing_columns": {
            t: c for t, c in clif.missing_columns.items() if c and t in tables
        },
        "token_counts": counts,  # per CLIF table of this step
    }


def qc_report(clif: ClifData, staged: pl.LazyFrame, metas: list[dict]) -> dict:
    """per-variable counts of the tables; `metas` = the tables' json "qc" """
    counts = staged.group_by("code", "qc_reason", "qc_flag").len().collect().to_dicts()
    variables: dict[str, dict] = {}
    for r in counts:
        v = variables.setdefault(
            r["code"], {"rows": 0, "tokenized": 0, "dropped": {}, "flags": {}}
        )
        v["rows"] += r["len"]
        if r["qc_reason"] is None:
            v["tokenized"] += r["len"]
        else:
            v["dropped"][r["qc_reason"]] = (
                v["dropped"].get(r["qc_reason"], 0) + r["len"]
            )
        if r["qc_flag"] is not None:
            v["flags"][r["qc_flag"]] = v["flags"].get(r["qc_flag"], 0) + r["len"]
    for v in variables.values():
        # "ignored" rows are intentional skips (e.g. tracheostomy == 0)
        ignored = v["dropped"].get("ignored", 0)
        denom = v["rows"] - ignored
        v["drop_rate"] = round(1 - v["tokenized"] / denom, 6) if denom else 0.0
    warnings = sorted(
        code for code, v in variables.items() if v["drop_rate"] > QC_WARN_DROP_RATE
    )
    expected = {e.code for e in clif.spec.entries}
    return {
        "spec_version": clif.spec.spec_version,
        "spec_sha256": spec_hash(),
        "created_dttm": datetime.datetime.now(datetime.UTC)
        .replace(microsecond=0)
        .isoformat(),
        "missing_tables": sorted({t for m in metas for t in m["missing_tables"]}),
        "missing_columns": {
            t: sorted({c for m in metas for c in m["missing_columns"].get(t, [])})
            for t in sorted({t for m in metas for t in m["missing_columns"]})
        },
        "variables_without_data": sorted(expected - set(variables)),
        "invalid_stays": clif.stays.filter(~pl.col("_valid"))
        .select(pl.len())
        .collect()
        .item(),
        "elixhauser": next((m["elixhauser"] for m in metas if m["elixhauser"]), {}),
        "split": {},  # filled by split()
        "high_drop_rate": warnings,
        "totals": {
            "rows": sum(v["rows"] for v in variables.values()),
            "tokenized": sum(v["tokenized"] for v in variables.values()),
        },
        "variables": dict(sorted(variables.items())),
    }


def run_table(clif: ClifData, out: pathlib.Path, step: str) -> dict:
    """
    one table pipeline, on its own: tables/<step>.parquet (none if the
    table is missing) and tables/<step>.json, its summary for the qc report
    """
    tables = pathlib.Path(out).expanduser().resolve() / TABLES
    tables.mkdir(parents=True, exist_ok=True)
    f, meta = tables / f"{step}.parquet", tables / f"{step}.json"
    f.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    seen_t = set(clif.missing_tables)
    seen_c = {k: set(v) for k, v in clif.missing_columns.items()}
    clif.elix_counts = {}
    clif.logger.info(f"table {step}")
    frames = [lf for lf in STEPS[step].build(clif) if lf is not None]
    if frames:
        pl.concat(frames, how="vertical_relaxed").sink_parquet(f)
    summary = step_summary(clif, step, f)
    # what this run found missing, for the qc report
    summary["qc"] = {
        "missing_tables": sorted(set(clif.missing_tables) - seen_t),
        "missing_columns": {
            k: c
            for k, v in clif.missing_columns.items()
            if (c := [x for x in v if x not in seen_c.get(k, set())])
        },
        "elixhauser": clif.elix_counts,
    }
    meta.write_text(json.dumps(summary, indent=2, sort_keys=True))
    return summary


# ------------------------------------------------------------ 2. assemble


def assemble(clif: ClifData, out: pathlib.Path) -> dict:
    """
    the tables -> qc_report.json and _events.parquet; needs every step's
    tables/<step>.json, so a table that was not run is never silently missing
    """
    out = pathlib.Path(out).expanduser().resolve()
    tables = out / TABLES
    lost = [s for s in STEPS if not (tables / f"{s}.json").exists()]
    if lost:
        raise FileNotFoundError(
            f"{out}: tables not generated: {', '.join(lost)} "
            "(run `icutwin-tokenize table <config> <step>` or "
            "`icutwin-tokenize pipeline`)"
        )
    metas = [json.loads((tables / f"{s}.json").read_text())["qc"] for s in STEPS]
    files = [tables / f"{s}.parquet" for s in STEPS]
    files = [f for f in files if f.exists()]
    if not files:
        raise RuntimeError("no CLIF tables produced any events")
    staged = pl.scan_parquet(files)
    clif.get_reference_frame()
    qc = qc_report(clif, staged, metas)
    # duplicates come from one source table, so dedupe per table file:
    # a global unique() over all events does not fit in memory
    parts = out / "_events_parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir()
    for f in files:
        ev = pl.scan_parquet(f).filter(pl.col("token").is_not_null())
        ev = ev.select(EVENT_COLS)
        if clif.cfg.drop_duplicate_events:
            ev = ev.unique(maintain_order=False)
        ev.sink_parquet(parts / f.name)
    pl.scan_parquet(sorted(parts.glob("*.parquet"))).sink_parquet(out / EVENTS)
    shutil.rmtree(parts, ignore_errors=True)
    (out / "qc_report.json").write_text(json.dumps(qc, indent=2))
    for code in qc["high_drop_rate"]:
        v = qc["variables"][code]
        clif.logger.warning(f"{code}: {v['drop_rate']:.1%} dropped {v['dropped']}")
    return qc


def collate(clif: ClifData, out: pathlib.Path, report=lambda step: None) -> dict:
    """steps 1-2; report(summary) as each table finishes"""
    for step in STEPS:
        report(run_table(clif, out, step))
    return assemble(clif, out)


# ------------------------------------------------------------ 3. split


def split(clif: ClifData, out: pathlib.Path) -> dict:
    """
    random split per hospitalization, never per patient: the stays are sorted
    by hospitalization_id and shuffled with split.seed; the first train_frac
    are train, the next tuning_frac tuning, the rest held_out
    """
    sp, ref = clif.cfg.split, clif.spec.reference
    pool = (
        clif.get_reference_frame()
        .select(HOSP, ref.start_time, ref.end_time)
        .collect()
        .sort(HOSP)
    )
    n = pool.height
    rank = np.empty(n, dtype=np.int64)
    rank[np.random.default_rng(sp.seed).permutation(n)] = np.arange(n)
    c1, c2 = int(n * sp.train_frac), int(n * (sp.train_frac + sp.tuning_frac))
    r = pl.Series(rank)
    splits = pool.with_columns(
        split=pl.when(r < c1)
        .then(pl.lit(SPLITS[0]))
        .when(r < c2)
        .then(pl.lit(SPLITS[1]))
        .otherwise(pl.lit(SPLITS[2]))
    ).select(HOSP, "split", ref.start_time, ref.end_time)
    splits.write_parquet(out / "splits.parquet")
    counts = dict(splits["split"].value_counts().iter_rows())
    counts = {k: counts.get(k, 0) for k in SPLITS}
    qc = json.loads((out / "qc_report.json").read_text())
    qc["split"] = {"seed": sp.seed} | counts
    (out / "qc_report.json").write_text(json.dumps(qc, indent=2))
    return counts


# ------------------------------------------------------------ 4. tokenize


def place_header(df: pl.LazyFrame) -> pl.LazyFrame:
    """
    header tokens take the time of the stay's first event, whatever it is
    (ADT, vitals, an ED lab before admission...), never admission_dttm;
    a stay with no event has no first time and loses its header
    """
    head = pl.any_horizontal(pl.col("code").str.starts_with(h) for h in HEADER)
    first = pl.col("time").filter(~head).min().over(HOSP)
    return df.with_columns(
        time=pl.when(head).then(first).otherwise(pl.col("time"))
    ).filter(pl.col("time").is_not_null())


def add_ends(df: pl.LazyFrame) -> pl.LazyFrame:
    """BOS / EOS at each hospitalization's first / last event"""
    ends = [
        df.group_by(HOSP)
        .agg(getattr(pl.col("time"), agg)())
        .with_columns(code=pl.lit(w), token=pl.lit(w))
        for agg, w in (("min", "BOS"), ("max", "EOS"))
    ]
    return pl.concat([df, *ends], how="diagonal")


def add_clocks(df: pl.LazyFrame, spec) -> pl.LazyFrame:
    """CLCK//HH tokens on configured local hours"""
    if not spec.time.insert_clocks:
        return df
    clocks = (
        df.group_by(HOSP)
        .agg(
            start=pl.col("time").min().dt.truncate("1h"),
            end=pl.col("time").max().dt.truncate("1h"),
        )
        .with_columns(
            pl.datetime_ranges("start", "end", interval="1h", closed="right")
            .alias("time")
            .list.filter(pl.element().dt.strftime("%H").is_in(spec.time.clocks))
        )
        .explode("time")
        .drop_nulls(subset=["time"])
        .select(
            HOSP,
            "time",
            code=pl.concat_str(pl.lit("CLCK//"), pl.col("time").dt.strftime("%H")),
        )
        .with_columns(token=pl.col("code"))
    )
    return pl.concat([df, clocks], how="diagonal")


def insert_time_spacers(df: pl.LazyFrame, spec) -> pl.LazyFrame:
    """
    TIME//<gap> rows for gaps >= the smallest spacer; one spacer per distinct
    timestamp, placed by `ordering` before everything at that time
    """
    if not spec.time.insert_spacers:
        return df
    spcrs = dict(spec.time.spacers)
    spacers = (
        df.select(HOSP, "time")
        .unique()
        .sort(HOSP, "time")
        .with_columns(
            tdiff_mins=(
                pl.col("time") - pl.col("time").shift(1).over(HOSP)
            ).dt.total_minutes()
        )
        .filter(pl.col("tdiff_mins") >= min(spcrs.values()))
        .select(
            HOSP,
            "time",
            code=pl.lit("TIME"),
            token=pl.concat_str(
                pl.lit("TIME//"),
                pl.col("tdiff_mins")
                .cut(breaks=list(spcrs.values())[1:], labels=list(spcrs))
                .cast(pl.String),
            ),
        )
    )
    return pl.concat([df, spacers], how="diagonal")


def order_and_ids(df: pl.LazyFrame, spec, vocab: Vocabulary) -> pl.LazyFrame:
    """one row per token, in timeline order, with its id and position in the stay"""
    order = {k: i for i, k in enumerate(spec.ordering)}
    level = lambda n: pl.col("code").str.split("//").list.slice(0, n).list.join("//")
    return (
        df.with_columns(  # longest ordering key wins: HOSP//age_charted > HOSP
            priority=pl.coalesce(
                level(2).replace_strict(order, default=None),
                level(1).replace_strict(order, default=None),
                pl.lit(len(order)),
            )
        )
        .sort(  # value columns break ties between equal tokens (determinism)
            HOSP,
            "time",
            "priority",
            "token",
            "category_value",
            "value",
            nulls_last=True,
        )
        # streaming joins do not keep row order; pin each token's position
        .with_row_index("_pos")
        .join(
            vocab.frame().lazy().rename({"word": "token", "token": "token_id"}),
            on="token",
            how="left",
        )
        .with_columns(position_id=(pl.col("_pos") - pl.col("_pos").min().over(HOSP)))
        .sort("_pos")
        .select(
            HOSP,
            pl.col("time").alias("event_time"),
            "token",
            pl.col("token_id").fill_null(0).cast(pl.UInt32),  # 0 = UNK
            pl.col("unit").cast(pl.String),
            pl.col("value").cast(pl.Float64),
            pl.col("category_value").cast(pl.String),
            pl.col("position_id").cast(pl.UInt32),
        )
    )


def timeline(df: pl.LazyFrame, spec, vocab: Vocabulary) -> pl.LazyFrame:
    df = add_ends(place_header(df))
    df = insert_time_spacers(add_clocks(df, spec), spec)
    return order_and_ids(df, spec, vocab)


def tokenize(clif: ClifData, out: pathlib.Path) -> dict:
    """
     tokenize in hospitalization batches so peak memory is bounded by
     max_events_per_batch rather than the size of the data; stays with
     fewer than min_tokens tokens are removed; one tokens file per split
    ; the internal events file is deleted
    """
    out = pathlib.Path(out).expanduser().resolve()
    spec, vocab, cfg = clif.spec, Vocabulary(clif.spec), clif.cfg
    events = pl.scan_parquet(out / EVENTS)
    unknown = (
        events.select(pl.col("token").unique())
        .filter(~pl.col("token").is_in(list(vocab.lookup)))
        .collect()
    )
    if unknown.height:  # cannot happen unless events came from elsewhere
        clif.logger.warning(f"{unknown.height} words not in vocab -> UNK")
    n_rows = events.select(pl.len()).collect().item()
    n = max(1, math.ceil(n_rows / int(cfg.max_events_per_batch)))
    parts = out / "_tokens_parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True)
    short = 0
    for i in range(n):
        batch = events.filter(pl.col(HOSP).hash(seed=0) % n == i)
        clif.logger.info(f"tokenizing batch {i + 1}/{n}")
        tok = timeline(batch, spec, vocab).collect()
        kept = tok.filter(pl.len().over(HOSP) >= cfg.min_tokens)
        short += tok[HOSP].n_unique() - kept[HOSP].n_unique()
        kept.write_parquet(parts / f"part-{i:05d}.parquet")
    tokens = pl.scan_parquet(sorted(parts.glob("*.parquet")))
    # splits.parquet and the QC split counts cover only the tokenized stays
    splits = pl.read_parquet(out / "splits.parquet").join(
        tokens.select(HOSP).unique().collect(), on=HOSP, how="semi"
    )
    splits.write_parquet(out / "splits.parquet")
    for s in SPLITS:
        ids = splits.filter(pl.col("split") == s)[HOSP]
        tokens.filter(pl.col(HOSP).is_in(ids.implode())).sink_parquet(
            out / f"tokens_{s}.parquet"
        )
    # every table's token counts, plus the final timeline (BOS/EOS, TIME, CLCK...)
    counts = {}
    for step in STEPS:
        counts |= json.loads((out / TABLES / f"{step}.json").read_text())[
            "token_counts"
        ]
    counts |= token_counts(tokens.with_columns(table=pl.lit("timeline")))
    (out / COUNTS).write_text(json.dumps(counts, indent=2, sort_keys=True))
    shutil.rmtree(parts, ignore_errors=True)
    (out / EVENTS).unlink(missing_ok=True)
    vocab.save(out / "vocab.yaml")
    qc = json.loads((out / "qc_report.json").read_text())
    qc["short_stays_removed"] = short
    counts = dict(splits["split"].value_counts().iter_rows())
    qc["split"] |= {k: counts.get(k, 0) for k in SPLITS}
    (out / "qc_report.json").write_text(json.dumps(qc, indent=2))
    clif.logger.info(f"{short} stays under {cfg.min_tokens} tokens removed")
    return qc

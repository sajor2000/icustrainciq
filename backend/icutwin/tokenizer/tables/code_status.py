#!/usr/bin/env python3

"""
code status pipeline -> tables/code_status.parquet

1. read       clif_code_status through clifpy io_polars (charted per patient)
2. convert    patient -> each stay: the status active at admission (moved to
              admission) plus every change during the stay; only a
              known status (full, dnr, dni) is carried in, else none
3. tokens     CODE_STATUS//{full,dnr,dni}; anything else (AND, Other,
              unmapped) -> CODE_STATUS//other
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import HOSP, PAT, ClifData, _key_norm, normalize_key

TABLE = "code_status"
TABLES = (TABLE,)


def per_stay(clif: ClifData, cat) -> pl.LazyFrame | None:
    """steps 1-2"""
    t, ref = cat.time_column, clif.spec.reference
    # 1. read
    cs = clif.read(TABLE)
    if cs is None or not clif.has_columns(cs, TABLE, [PAT, t, cat.column]):
        return None
    # 2. convert
    start, end = ref.start_time, ref.end_time
    stays = clif.get_reference_frame().select(HOSP, PAT, start, end)
    # Ignore source hospitalization_id; patient and time select the stay.
    if HOSP in cs.collect_schema().names():
        cs = cs.drop(HOSP)
    cs = cs.join(stays, on=PAT)
    during = cs.filter((pl.col(t) > pl.col(start)) & (pl.col(t) <= pl.col(end)))
    known = [normalize_key(k) for k, v in cat.mapping.items() if v != "other"]
    before = (
        cs.filter(
            (pl.col(t) <= pl.col(start)) & _key_norm(pl.col(cat.column)).is_in(known)
        )
        .sort(t, cat.column)
        .unique(subset=[HOSP], keep="last", maintain_order=True)
        .with_columns(pl.col(start).alias(t))
    )
    return pl.concat([during, before])


def build(clif: ClifData) -> list:
    out = []
    for cat in clif.of("categorical", TABLE):
        df = per_stay(clif, cat)
        out.append(None if df is None else clif.categorical(cat, df))  # 3, 4
    return out

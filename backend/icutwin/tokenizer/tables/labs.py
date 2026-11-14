#!/usr/bin/env python3

"""
labs pipeline -> tables/labs.parquet

1. read       clif_labs through clifpy io_polars, times in the configured timezone
2. convert    LAB_RES: keep the spec labs (lab_category -> code), lab_value_numeric
              is taken as the mCIDE 2.1 unit, raw units are not checked;
              LAB_ORD: spec labs only, other categories are out of scope
3. tokens     LAB_RES//<lab>//B<k>: the PBC bin; outside the plausible
              range -> the bottom or top bin, flagged clipped_low / clipped_high;
              LAB_ORD//<lab> at lab_order_dttm
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import (
    HOSP,
    ClifData,
    match_category,
    tokenize_continuous,
)

TABLE = "labs"
TABLES = (TABLE,)


def values(clif: ClifData) -> pl.LazyFrame | None:
    """LAB_RES, steps 1-4"""
    entries = clif.of("continuous", TABLE)
    if not entries:
        return None
    e = entries[0]  # lab_result_dttm, lab_category, lab_value_numeric

    # 1. read
    df = clif.read(TABLE, [HOSP, e.time_column, e.category_column, e.value_column])
    if df is None:
        return None

    # 2. convert
    df = match_category(df, entries, e.category_column)
    df = df.rename({e.value_column: "value"})

    # 3. tokens
    df = tokenize_continuous(df, entries)

    # 4. table
    return clif.token_table(df, e.time_column)


def build(clif: ClifData) -> list:
    orders = [clif.categorical(c) for c in clif.of("categorical", TABLE)]  # LAB_ORD
    return [values(clif), *orders]

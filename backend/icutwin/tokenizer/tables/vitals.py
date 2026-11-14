#!/usr/bin/env python3

"""
vitals pipeline -> tables/vitals.parquet: VITAL//<vital_category>//B<k>

1. read       clif_vitals through clifpy io_polars, times in the configured timezone
2. convert    keep the spec vitals (vital_category -> code); vital_value is
              taken as the spec unit: CLIF vitals have no unit column
3. tokens     the PBC bin; outside the plausible range -> the bottom
              or top bin, flagged clipped_low / clipped_high
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import (
    HOSP,
    ClifData,
    match_category,
    tokenize_continuous,
)

TABLE = "vitals"
TABLES = (TABLE,)


def values(clif: ClifData) -> pl.LazyFrame | None:
    entries = clif.of("continuous", TABLE)
    if not entries:
        return None
    e = entries[0]  # recorded_dttm, vital_category, vital_value

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
    return [values(clif)]

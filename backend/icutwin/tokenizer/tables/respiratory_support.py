#!/usr/bin/env python3

"""
respiratory support pipeline -> tables/respiratory_support.parquet

1. read       clif_respiratory_support through clifpy io_polars
2. convert    settings: one column per setting -> one row per (setting, value);
              a null cell means "not charted", not a drop;
              device_category / mode_category / tracheostomy as charted
3. tokens     RESP//<setting>//B<k>;
              RESP//device_category//<device>, RESP//mode_category//<mode>,
              RESP//tracheostomy_initiated at the stay's first 1/yes only
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import HOSP, ClifData, first_only, tokenize_continuous

TABLE = "respiratory_support"
TABLES = (TABLE,)
TRACH = "RESP//tracheostomy_initiated"


def values(clif: ClifData) -> pl.LazyFrame | None:
    """the settings, steps 1-4"""
    entries = clif.of("continuous", TABLE)
    if not entries:
        return None
    time = entries[0].time_column  # recorded_dttm

    # 1. read
    df = clif.read(TABLE)
    if df is None:
        return None
    present = [e for e in entries if clif.has_columns(df, TABLE, [e.value_column])]
    if not present or not clif.has_columns(df, TABLE, [HOSP, time]):
        return None

    # 2. convert
    df = df.select(
        HOSP,
        time,
        *[
            pl.col(e.value_column).cast(pl.Float64, strict=False).alias(e.code)
            for e in present
        ],
    ).unpivot(index=[HOSP, time], variable_name="code", value_name="value")
    df = df.filter(pl.col("value").is_not_null())

    # 3. tokens
    df = tokenize_continuous(df, present)

    # 4. table
    return clif.token_table(df, time)


def build(clif: ClifData) -> list:
    categories = []
    for c in clif.of("categorical", TABLE):
        t = clif.categorical(c)
        categories.append(first_only(t) if t is not None and c.code == TRACH else t)
    return [values(clif), *categories]

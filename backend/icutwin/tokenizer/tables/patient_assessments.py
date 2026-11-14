#!/usr/bin/env python3

"""
patient assessments pipeline -> tables/patient_assessments.parquet

1. read       clif_patient_assessments through clifpy io_polars
2. convert    keep gcs_total and rass (assessment_category -> code)
3. tokens     PA//gcs_total//<n>, PA//rass//<n>: whole numbers on the spec's
              scale only, otherwise dropped (non_integer, not_in_scale)
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import HOSP, ClifData, Ordinal, match_category

TABLE = "patient_assessments"
TABLES = (TABLE,)


def tokenize_ordinal(df: pl.LazyFrame, entries: list[Ordinal]) -> pl.LazyFrame:
    """df needs `code`, `value`; integer scores restricted to the spec's scale"""
    allowed = pl.DataFrame(
        [(o.code, v) for o in entries for v in o.values],
        schema={"code": pl.String, "score": pl.Int64},
        orient="row",
    ).with_columns(in_scale=pl.lit(True))
    v = pl.col("value").cast(pl.Float64, strict=False)
    return (
        df.with_columns(
            value=v,
            score=pl.when(v.is_finite() & (v == v.round(0))).then(v.cast(pl.Int64)),
            qc_flag=pl.lit(None, pl.String),
        )
        .join(allowed.lazy(), on=["code", "score"], how="left")
        .with_columns(
            qc_reason=pl.when(pl.col("value").is_null())
            .then(pl.lit("null_value"))
            .when(~pl.col("value").is_finite())
            .then(pl.lit("nonfinite"))
            .when(pl.col("score").is_null())
            .then(pl.lit("non_integer"))
            .when(pl.col("in_scale").is_null())
            .then(pl.lit("not_in_scale"))
            .otherwise(None)
        )
        .with_columns(
            token=pl.when(pl.col("qc_reason").is_null()).then(
                pl.concat_str(
                    pl.col("code"), pl.lit("//"), pl.col("score").cast(pl.String)
                )
            )
        )
        .drop("score", "in_scale")
    )


def build(clif: ClifData) -> list:
    entries = clif.of("ordinal", TABLE)
    if not entries:
        return []
    e = entries[0]  # recorded_dttm, assessment_category, numerical_value

    # 1. read
    df = clif.read(TABLE, [HOSP, e.time_column, e.category_column, e.value_column])
    if df is None:
        return []

    # 2. convert
    df = match_category(df, entries, e.category_column)
    df = df.rename({e.value_column: "value"})

    # 3. tokens
    df = tokenize_ordinal(df, entries)

    # 4. table
    return [clif.token_table(df, e.time_column)]

#!/usr/bin/env python3

"""
continuous medication pipeline -> tables/medication_admin_continuous.parquet:
MED_CON//<med_category>//B<k> (//given for a 1-bin drug; MED_CON//unk)

1. read       clif_medication_admin_continuous through clifpy io_polars
2. convert    keep the spec meds; clifpy convert_dose_units_by_med_category
              converts each dose to the med's ELF preferred unit,
              weight-based doses with the patient's weight_kg from vitals
3. tokens     converted dose -> PBC bin; above the plausible max -> the top
              bin, flagged clipped_high; a dose clifpy cannot convert,
              or a null / negative one -> MED_CON//unk, flagged value_to_unk
             ; a 1-bin drug's unconverted dose is //given
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import HOSP, ClifData, convert_doses, tokenize_continuous

TABLE = "medication_admin_continuous"
TABLES = (TABLE,)


def doses(clif: ClifData) -> pl.LazyFrame | None:
    """steps 1-2"""
    entries = clif.of("continuous", TABLE)
    if not entries:
        return None

    # 1. read
    e = entries[0]  # admin_dttm, med_category, med_dose, med_dose_unit
    df = clif.read(
        TABLE, [HOSP, e.time_column, e.category_column, e.value_column, e.unit_column]
    )
    if df is None:
        return None

    # 2. convert
    return convert_doses(clif, df, entries)


def values(clif: ClifData) -> pl.LazyFrame | None:
    """steps 1-4"""
    conv = doses(clif)
    if conv is None:
        return None
    entries = clif.of("continuous", TABLE)
    e, ok = entries[0], pl.col("converted_ok")

    # 3. tokens
    good = conv.filter(ok).select(
        HOSP, e.time_column, "code", value=pl.col("med_dose_converted")
    )
    one = pl.col("code").is_in([x.code for x in entries if len(x.bins) == 1])
    failed = conv.filter(~ok).select(  # still on; raw dose of unknown unit not kept
        HOSP,
        e.time_column,
        "code",
        value=pl.lit(None, pl.Float64),
        token=pl.when(one)
        .then(pl.col("code") + "//given")
        .otherwise(pl.lit("MED_CON//unk")),
        qc_reason=pl.lit(None, pl.String),
        qc_flag=pl.lit("value_to_unk"),
    )
    df = pl.concat([tokenize_continuous(good, entries), failed], how="diagonal_relaxed")

    # 4. table
    return clif.token_table(df, e.time_column)


def build(clif: ClifData) -> list:
    return [values(clif)]

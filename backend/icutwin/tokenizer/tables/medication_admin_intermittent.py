#!/usr/bin/env python3

"""
intermittent medication pipeline -> tables/medication_admin_intermittent.parquet:
MED_INT//<drug>//B<k> or MED_INT//<drug>//given (MED_INT//unk), per drug of the 3 mCIDE
groups (sepsis antibiotics, paralytics, sedation)

1. read       clif_medication_admin_intermittent through clifpy io_polars
2. convert    only doses given (mar_action_category = given); keep the spec
              drugs; clifpy converts each dose to mg (convert_doses)
3. tokens     converted dose -> PBC bin, above the plausible range dropped,
              null / below -> MED_INT//unk; a 1-bin drug is always //given,
              even if clifpy cannot convert it; a binned drug's dose
              clifpy cannot convert (unit `dose`) is MED_INT//unk, flagged
              value_to_unk
4. table      stay checks, fixed columns
"""

import polars as pl

from icutwin.tokenizer.helpers import (
    HOSP,
    ClifData,
    _key_norm,
    convert_doses,
    normalize_key,
    tokenize_continuous,
)

TABLE = "medication_admin_intermittent"
TABLES = (TABLE,)


def doses(clif: ClifData) -> pl.LazyFrame | None:
    """steps 1-2"""
    entries = clif.of("continuous", TABLE)
    if not entries:
        return None
    e = entries[0]  # admin_dttm, med_category, med_dose, med_dose_unit
    where = e.where  # {mar_action_category: given}

    # 1. read
    cols = [HOSP, e.time_column, e.category_column, e.value_column, e.unit_column]
    df = clif.read(TABLE, [*cols, *where])
    if df is None:
        return None

    # 2. convert
    for k, v in where.items():
        df = df.filter(_key_norm(pl.col(k)) == normalize_key(v))
    return convert_doses(clif, df, entries)


def values(clif: ClifData) -> pl.LazyFrame | None:
    """steps 1-4"""
    conv = doses(clif)
    if conv is None:
        return None
    entries = clif.of("continuous", TABLE)
    e, ok = entries[0], pl.col("converted_ok")
    one = pl.col("code").is_in([x.code for x in entries if len(x.bins) == 1])

    # 3. tokens
    good = conv.filter(ok & ~one).select(
        HOSP, e.time_column, "code", value=pl.col("med_dose_converted")
    )
    given = conv.filter(one).select(  # dose ignored, even if not converted
        HOSP,
        e.time_column,
        "code",
        value=pl.when(ok).then(pl.col("med_dose_converted").cast(pl.Float64)),
        token=pl.col("code") + "//given",
    )
    failed = conv.filter(~ok & ~one).select(  # raw dose of unknown unit not kept
        HOSP,
        e.time_column,
        "code",
        value=pl.lit(None, pl.Float64),
        token=pl.lit("MED_INT//unk"),
        qc_flag=pl.lit("value_to_unk"),
    )
    df = pl.concat(
        [tokenize_continuous(good, entries), given, failed], how="diagonal_relaxed"
    )

    # 4. table
    return clif.token_table(df, e.time_column)


def build(clif: ClifData) -> list:
    return [values(clif)]

#!/usr/bin/env python3

"""
cohort pipeline (hospitalization + patient + hospital_diagnosis) ->
tables/cohort.parquet, the stay header and outcome

1. read       clif_hospitalization (valid stays: discharge after admission),
              clif_patient, clif_hospital_diagnosis via clifpy io_polars
2. convert    age_at_admission as charted; patient sex/race/ethnicity joined
              onto every stay of the patient, at admission; the PREVIOUS stay's
              ICD-10-CM codes -> Elixhauser flags with clifpy calculate_elix
              (this stay's codes are assigned at discharge and would leak the
              label)
3. tokens     HOSP//age_charted//B<k>, HOSP//admission_type//<type>,
              HOSP//discharge_category//<disposition>,
              PATIENT//sex|race|ethnicity//<value> (null or unmapped ->
              other_ukn), HOSP_PREV_DX//elixhauser//<flag> or //none
4. table      stay checks, fixed columns; assembly moves the header to the
              stay's first event
"""

import polars as pl

from icutwin.tokenizer.helpers import HOSP, PAT, ClifData, tokenize_continuous

TABLES = ("hospitalization", "patient", "hospital_diagnosis")


def age(clif: ClifData) -> pl.LazyFrame | None:
    """HOSP//age_charted, steps 1-4"""
    entries = clif.of("continuous", clif.spec.reference.table)
    if not entries:
        return None
    hosp, time = entries[0].table, entries[0].time_column  # admission_dttm

    # 1. read
    df = clif.get_reference_frame()
    present = [e for e in entries if clif.has_columns(df, hosp, [e.value_column])]
    if not present:
        return None

    # 2. convert (a null age is "not charted", not a drop)
    df = pl.concat(
        df.select(
            HOSP,
            time,
            code=pl.lit(e.code),
            value=pl.col(e.value_column).cast(pl.Float64, strict=False),
        )
        for e in present
    ).filter(pl.col("value").is_not_null())

    # 3. tokens
    df = tokenize_continuous(df, present)

    # 4. table
    return clif.token_table(df, time)


def patient(clif: ClifData, cat) -> pl.LazyFrame | None:
    """PATIENT//<cat>: patient-level values on every stay of the patient"""
    # 1. read
    pat = clif.read("patient", [PAT, cat.column])
    if pat is None:
        return None
    # 2. convert: one row per patient, joined onto each stay at admission
    df = (
        clif.get_reference_frame()
        .select(HOSP, PAT, clif.spec.reference.start_time)
        .join(
            pat.select(PAT, cat.column).unique(subset=[PAT], keep="first"),
            on=PAT,
            how="left",
        )
    )
    # 3, 4. tokens, table
    return clif.categorical(cat, df)


def elixhauser(clif: ClifData) -> pl.LazyFrame | None:
    """
    not this stay's diagnoses: its codes are assigned at discharge and would
    leak the label. Placed at the stay start by assembly
    """
    from clifpy.utils.comorbidity import calculate_elix

    ex, ref = clif.spec.elixhauser, clif.spec.reference
    # 1. read
    dx = clif.read(ex.table, [HOSP, "diagnosis_code", "diagnosis_code_format"])
    if dx is None:
        return None
    # 2. convert: each stay's previous stay of the same patient
    stays = (
        clif.get_reference_frame()
        .select(HOSP, PAT, ref.start_time, ref.end_time)
        .sort(PAT, ref.start_time)
        .with_columns(
            prev=pl.col(HOSP).shift(1).over(PAT),
            prev_end=pl.col(ref.end_time).shift(1).over(PAT),
        )
        .with_columns(  # an overlapping "previous" stay is not in the past
            ok=pl.col("prev").is_not_null()
            & (pl.col("prev_end") <= pl.col(ref.start_time))
        )
        .collect()
    )
    prev_ids = stays.filter("ok")["prev"].unique().to_list()
    dx = (
        dx.with_columns(pl.col(HOSP).cast(pl.String))
        .filter(pl.col(HOSP).is_in(prev_ids))
        .collect()
    )
    icd10 = dx.filter(pl.col("diagnosis_code_format").str.to_uppercase() == "ICD10CM")[
        HOSP
    ].unique()
    hits = pl.DataFrame(schema={"prev": pl.String, "flag": pl.String})
    if len(dx):  # clifpy maps ICD-10-CM only
        hits = (
            pl.from_pandas(calculate_elix(dx.to_pandas()))
            .unpivot(index=HOSP, on=ex.flags, variable_name="flag")
            .filter(pl.col("value") == 1)
            .select(pl.col(HOSP).cast(pl.String).alias("prev"), "flag")
        )
    # 3. tokens; left join: a stay without flags keeps one null row -> "none"
    tok = (
        stays.join(hits, on="prev", how="left")
        .with_columns(flag=pl.when("ok").then("flag"))
        .unique([HOSP, "flag"])
        .with_columns(
            token=pl.concat_str(
                pl.lit(ex.code + "//"), pl.col("flag").fill_null("none")
            )
        )
    )
    clif.elix_counts = {
        "stays": stays.height,
        "no_prior_stay": stays["prev"].null_count(),
        "prior_overlaps": int((stays["prev"].is_not_null() & ~stays["ok"]).sum()),
        "prior_without_icd10": int(
            (stays["ok"] & ~stays["prev"].is_in(icd10.to_list())).sum()
        ),
        "with_flags": tok.filter(pl.col("flag").is_not_null())[HOSP].n_unique(),
    }
    # 4. table
    return clif.token_table(
        tok.lazy().select(
            HOSP,
            ref.start_time,
            code=pl.lit(ex.code),
            token="token",
            value=pl.lit(None, pl.Float64),
            qc_reason=pl.lit(None, pl.String),
            qc_flag=pl.lit(None, pl.String),
        ),
        ref.start_time,
    )


def build(clif: ClifData) -> list:
    hosp = clif.spec.reference.table
    return [
        age(clif),
        *(clif.categorical(c) for c in clif.of("categorical", hosp)),
        *(patient(clif, c) for c in clif.of("categorical", "patient")),
        elixhauser(clif) if clif.spec.elixhauser else None,
    ]

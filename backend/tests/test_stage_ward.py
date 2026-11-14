"""The stage-ward selection: eligible stays, the 0 to 8 score, the band, determinism."""

import datetime as dt

import polars as pl

from app import stage_ward

T0 = dt.datetime(2150, 1, 1, 12, tzinfo=dt.UTC)
H = lambda x: T0 + dt.timedelta(hours=x)  # noqa: E731


def build(tmp_path, n=40):
    """stay i: ICU at hour 0; sickness points = i % 4; every 10th leaves the ICU
    at hour 10; stays 7 and 8 belong to one patient"""
    adt, hosp, meds, vit, labs, resp = [], [], [], [], [], []
    for i in range(n):
        h = f"h{i:03d}"
        out = H(10) if i % 10 == 0 else H(100)
        adt.append((h, H(0), out, "icu"))
        hosp.append((h, "p7" if i == 8 else f"p{i}", H(120)))
        pts = i % 4
        if pts >= 1:
            meds.append((h, H(2), "norepinephrine", 0.1))
        if pts >= 2:
            resp.append((h, H(3), "IMV", 0.4))
        if pts >= 3:
            vit.append((h, H(4), "map", 60.0))
        # events after the cut must not count
        vit.append((h, H(30), "spo2", 80.0))
        labs.append((h, H(1), H(1), "lactate", 1.0))  # normal
    d = tmp_path / "demo"
    d.mkdir()
    cols = {
        "adt": (
            ["hospitalization_id", "in_dttm", "out_dttm", "location_category"],
            adt,
        ),
        "hospitalization": (
            ["hospitalization_id", "patient_id", "discharge_dttm"],
            hosp,
        ),
        "medication_admin_continuous": (
            ["hospitalization_id", "admin_dttm", "med_category", "med_dose"],
            meds,
        ),
        "vitals": (
            ["hospitalization_id", "recorded_dttm", "vital_category", "vital_value"],
            vit,
        ),
        "labs": (
            [
                "hospitalization_id",
                "lab_collect_dttm",
                "lab_result_dttm",
                "lab_category",
                "lab_value_numeric",
            ],
            labs,
        ),
        "respiratory_support": (
            ["hospitalization_id", "recorded_dttm", "device_category", "fio2_set"],
            resp,
        ),
        "crrt_therapy": (["hospitalization_id", "recorded_dttm"], [("h000", H(5))]),
    }
    for name, (c, rows) in cols.items():
        schema = {k: v for k, v in zip(c, [pl.String] * len(c))}
        df = (
            pl.DataFrame(rows, schema=c, orient="row")
            if rows
            else pl.DataFrame(schema=schema)
        )
        df.write_parquet(d / f"clif_{name}.parquet")
    return d


def test_eligibility_and_points(tmp_path):
    d = build(tmp_path)
    stays = stage_ward.eligible_stays(d)
    assert stays.height == 36  # the 4 stays that left the ICU at hour 10 are out
    scored = stage_ward.score_stays(d, stays).filter(
        pl.col("hospitalization_id") != "x"
    )
    by = {r["hospitalization_id"]: r["score"] for r in scored.iter_rows(named=True)}
    assert by["h001"] == 1 and by["h002"] == 2 and by["h003"] == 3
    assert by["h004"] == 0
    assert all(0 <= s <= 8 for s in by.values())  # spo2 at hour 30 never counted


def test_selection_is_deterministic_one_per_patient_and_counts_only(tmp_path, capsys):
    d = build(tmp_path)
    a = stage_ward.score_stays(d, stage_ward.eligible_stays(d))
    r1, info = stage_ward.select_rooms(a, n=10, seed=20261114)
    r2, _ = stage_ward.select_rooms(a, n=10, seed=20261114)
    r3, _ = stage_ward.select_rooms(a, n=10, seed=1)
    assert r1.equals(r2) and not r1.equals(r3)
    assert r1["room"].to_list() == list(range(1, 11))
    ids = r1["hospitalization_id"].to_list()
    assert len(set(ids)) == 10 and not {"h007", "h008"} <= set(ids)  # one per patient
    assert info["selected"] == 10 and info["band_percentiles"][0] <= 40
    assert stage_ward.digest(r1) == stage_ward.digest(r2)

    out = tmp_path / "vol" / "stage_ward.csv"
    import sys

    sys.argv = ["stage_ward", str(d), "--out", str(out), "--n", "10"]
    stage_ward.main()
    printed = capsys.readouterr().out
    assert "h0" not in printed and "ids_digest" in printed  # counts and a digest only
    assert pl.read_csv(out).columns == ["room", "hospitalization_id", "score"]

"""exclude_demo: the demo cohort leaves every split (synthetic frames only)"""

import json

import polars as pl
import pytest

from icutwin.exclude_demo import DemoExcludedError, exclude_demo


def write_splits(root):
    pl.DataFrame(
        {
            "hospitalization_id": ["h1", "h2", "h3", "h4"],
            "split": ["train", "tuning", "held_out", "train"],
            "start": [None] * 4,
            "end": [None] * 4,
        }
    ).write_parquet(root / "splits.parquet")
    (root / "qc_report.json").write_text(
        json.dumps({"split": {"train": 2, "tuning": 1, "held_out": 1}})
    )


def write_demo(demo, stays, patients):
    demo.mkdir()
    pl.DataFrame({"hospitalization_id": stays, "patient_id": patients}).write_parquet(
        demo / "clif_hospitalization.parquet"
    )
    pl.DataFrame({"patient_id": sorted(set(patients))}).write_parquet(
        demo / "clif_patient.parquet"
    )


def test_demo_stays_leave_every_split(tmp_path):
    write_splits(tmp_path)
    write_demo(tmp_path / "demo", ["h2"], ["p1"])
    n = exclude_demo(tmp_path, tmp_path / "demo")
    assert n == {"train": 2, "tuning": 0, "held_out": 1}
    kept = pl.read_parquet(tmp_path / "splits.parquet")
    assert "h2" not in kept["hospitalization_id"]
    assert json.loads((tmp_path / "qc_report.json").read_text())["split"] == n


def test_a_demo_patients_other_stays_leave_too(tmp_path):
    write_splits(tmp_path)
    pl.DataFrame(
        {
            "hospitalization_id": ["h1", "h2", "h3", "h4"],
            "patient_id": ["p9", "p1", "p9", "p1"],
        }
    ).write_parquet(tmp_path / "clif_hospitalization.parquet")
    write_demo(tmp_path / "demo", ["h2"], ["p1"])
    n = exclude_demo(tmp_path, tmp_path / "demo")
    # p1 owns h2 and h4, so both leave; p9's h1 and h3 stay
    assert n == {"train": 1, "tuning": 0, "held_out": 1}
    kept = pl.read_parquet(tmp_path / "splits.parquet")["hospitalization_id"]
    assert kept.to_list() == ["h1", "h3"]


def test_missing_demo_files_raise(tmp_path):
    write_splits(tmp_path)
    with pytest.raises(DemoExcludedError):
        exclude_demo(tmp_path, tmp_path / "nowhere")


def test_no_demo_stay_in_the_split_raises(tmp_path):
    write_splits(tmp_path)
    pl.DataFrame(
        {
            "hospitalization_id": ["h1", "h2", "h3", "h4"],
            "patient_id": ["a", "b", "c", "d"],
        }
    ).write_parquet(tmp_path / "clif_hospitalization.parquet")
    write_demo(tmp_path / "demo", ["zz"], ["p1"])
    with pytest.raises(DemoExcludedError):
        exclude_demo(tmp_path, tmp_path / "demo")

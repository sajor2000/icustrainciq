"""The publisher's CLI and context loader, using synthetic files only."""

import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import sys
import zoneinfo

import polars as pl
import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
IMV = "RESP//device_category//imv"
VASO = "LABEL//pressor_init"
CRRT = "LABEL//crrt_init"
WARD = "ADT//TRANSFER_IN//ward"
STEP = "ADT//TRANSFER_IN//stepdown"
DEATH = "HOSP//discharge_category//expired"
CUT = "2026-11-14T07:00:00-06:00"
SOURCE_START = dt.datetime(2160, 1, 1, tzinfo=dt.timezone.utc)


@pytest.fixture
def ward_files(tmp_path):
    root, model, clif = (tmp_path / p for p in ("tokens", "mdl-synthetic", "clif"))
    for p in (root, model, clif):
        p.mkdir()
    ids = [f"synthetic-private-{i:02}" for i in range(26)]
    roster = tmp_path / "private-roster.csv"
    pl.DataFrame({"room": range(1, 26), "hospitalization_id": ids[:25]}).write_csv(
        roster
    )
    (model / "model.safetensors").write_bytes(b"synthetic-weights")
    checksum = hashlib.sha256(b"model.safetensorssynthetic-weights").hexdigest()
    scalar = {
        "hospitalization_id": ids,
        "last_valid": [4] * 26,
        "cut_s": [86400.0] * 26,
        **{f"{t}_past": [False] * 26 for t in (IMV, VASO, CRRT, WARD, STEP, DEATH)},
        **{f"LABEL//{s}_at_cut": [False] * 26 for s in ("imv", "pressor", "crrt")},
    }
    scores = root / f"scores-rep-based-{model.name}.parquet"
    pl.DataFrame(
        {
            **scalar,
            f"{IMV}_rep_score": [1.0] + [0.0] * 24 + [1.0],
            f"{VASO}_rep_score": [0.2] * 26,
            f"{CRRT}_rep_score": [0.0] * 26,
            f"{WARD}_rep_score": [0.1] * 26,
            f"{STEP}_rep_score": [0.0] * 26,
            f"{DEATH}_rep_score": [0.05] * 26,
        }
    ).write_parquet(scores)
    scores.with_suffix(".meta.json").write_text(
        json.dumps({"model": model.name, "weights_sha256": checksum})
    )
    labels = root / "held_out_for_inference.parquet"
    pl.DataFrame(
        {
            **scalar,
            "tokens_past": [[1, 4, 2, 3]] * 26,
            "s_elapsed_past": [[0, 0, 72000, 82800]] * 26,
        }
    ).write_parquet(labels)
    features = root / f"features-held_out-{model.name}.parquet"
    pl.DataFrame(
        {k: scalar[k] for k in ("hospitalization_id", "last_valid", "cut_s")}
    ).write_parquet(features)
    features.with_suffix(".meta.json").write_text(  # extracted with these weights
        json.dumps({"model": model.name, "weights_sha256": checksum})
    )
    (root / "vocab.yaml").write_text(
        yaml.safe_dump(
            {
                "lookup": {
                    "BOS": 1,
                    IMV: 2,
                    "LAB_RES//map//L1": 3,
                    "ADT//TRANSFER_IN//icu": 4,
                }
            }
        )
    )
    pl.DataFrame(
        {
            "hospitalization_id": ids,
            "patient_id": [f"p{i}" for i in range(26)],
            "age_at_admission": [55] * 26,
            "discharge_dttm": [SOURCE_START + dt.timedelta(days=5)] * 26,
        }
    ).write_parquet(clif / "clif_hospitalization.parquet")
    pl.DataFrame(
        {"patient_id": [f"p{i}" for i in range(26)], "sex_category": ["Female"] * 26}
    ).write_parquet(clif / "clif_patient.parquet")
    pl.DataFrame(
        {
            "hospitalization_id": ids,
            "in_dttm": [SOURCE_START] * 26,
            "out_dttm": [SOURCE_START + dt.timedelta(days=5)] * 26,
            "location_category": ["icu"] * 26,
        }
    ).write_parquet(clif / "clif_adt.parquet")
    pl.DataFrame(
        {
            "hospitalization_id": ids,
            "recorded_dttm": [SOURCE_START + dt.timedelta(hours=23)] * 26,
            "device_category": ["Room Air"] * 26,
        }
    ).write_parquet(clif / "clif_respiratory_support.parquet")
    pl.DataFrame(
        schema={
            "hospitalization_id": pl.String,
            "admin_dttm": pl.Datetime("us", "UTC"),
            "med_category": pl.String,
            "mar_action_category": pl.String,
            "med_dose": pl.Float64,
        }
    ).write_parquet(clif / "clif_medication_admin_continuous.parquet")
    pl.DataFrame(
        schema={
            "hospitalization_id": pl.String,
            "recorded_dttm": pl.Datetime("us", "UTC"),
            "crrt_mode_category": pl.String,
            "blood_flow_rate": pl.Float64,
        }
    ).write_parquet(clif / "clif_crrt_therapy.parquet")
    return dict(
        root=root,
        model=model,
        clif=clif,
        roster=roster,
        scores=scores,
        labels=labels,
        features=features,
        ids=ids,
        out=tmp_path / "context.json",
    )


def publish(files, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "app/demo_context.py"),
            "--tokenized-output",
            str(files["root"]),
            "--model",
            str(files["model"]),
            "--clif",
            str(files["clif"]),
            "--roster",
            str(files["roster"]),
            "--out",
            str(files["out"]),
            "--cut-time",
            CUT,
            "--real-ward",
            *extra,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def publish_direct(files, **extra):
    from app.demo_context import publish_context

    return publish_context(
        tokenized_output=files["root"],
        model=files["model"],
        roster=files["roster"],
        clif=files["clif"],
        out=files["out"],
        cut_time=CUT,
        real_ward=True,
        **extra,
    )


def test_cli_publishes_one_matched_25_room_snapshot_without_private_ids(ward_files):
    run = publish(ward_files)
    assert run.returncode == 0, run.stderr
    raw = ward_files["out"].read_text()
    doc = json.loads(raw)
    assert doc["roster_size"] == doc["forecast"]["beds"] == 25
    assert [r["room"] for r in doc["rooms"]["rooms"]] == list(range(1, 26))
    assert doc["forecast"]["resources"]["ventilator"] == {
        "team": "respiratory therapy",
        "available": True,
        "p10": 1,
        "p50": 1,
        "p90": 1,
        "expected": 1.0,
    }
    assert doc["forecast"]["resources"]["vasopressor"]["expected"] == 5.0
    assert doc["rooms"]["rooms"][0]["age"] == "55"
    assert doc["rooms"]["rooms"][0]["past_12h"][0]["h"] == 1
    assert doc["source"] == {
        "kind": "mimic-iv",
        "label": "Real MIMIC-IV · local only",
        "dataset_version": None,
    }
    assert doc["clock_mode"] == "research_replay"
    assert (
        doc["snapshot_id"]
        == doc["forecast"]["snapshot_id"]
        == doc["rooms"]["snapshot_id"]
    )
    assert doc["cohort_id"] == doc["forecast"]["cohort_id"] == doc["rooms"]["cohort_id"]
    assert not any(i in raw + run.stdout + run.stderr for i in ward_files["ids"])
    assert json.loads(run.stdout)["rooms_written"] == 25


def test_loader_reads_one_snapshot_and_refuses_mixed_view_identity(ward_files):
    from app.demo_context import ContextUnavailable, load_context

    assert publish(ward_files).returncode == 0
    doc = load_context(ward_files["out"])
    assert doc["forecast"]["beds"] == 25
    doc["rooms"]["snapshot_id"] = "another-snapshot"
    ward_files["out"].write_text(json.dumps(doc))
    with pytest.raises(ContextUnavailable):
        load_context(ward_files["out"])


@pytest.mark.parametrize(
    "bad", ["missing", "duplicate-room", "duplicate-id", "blank-id", "outside-room"]
)
def test_invalid_private_roster_never_replaces_a_published_snapshot(ward_files, bad):
    table = pl.read_csv(ward_files["roster"])
    rows = table.to_dicts()
    if bad == "missing":
        rows.pop()
    elif bad == "duplicate-room":
        rows[1]["room"] = 1
    elif bad == "duplicate-id":
        rows[1]["hospitalization_id"] = rows[0]["hospitalization_id"]
    elif bad == "blank-id":
        rows[1]["hospitalization_id"] = None
    else:
        rows[-1]["room"] = 26
    pl.DataFrame(rows).write_csv(ward_files["roster"])
    ward_files["out"].write_text("previous snapshot")
    run = publish(ward_files)
    assert run.returncode != 0
    assert ward_files["out"].read_text() == "previous snapshot"
    assert "roster" in run.stderr.lower()
    assert not any(i in run.stdout + run.stderr for i in ward_files["ids"])


@pytest.mark.parametrize("artifact", ["scores", "labels", "features"])
@pytest.mark.parametrize("bad", ["missing", "duplicate"])
def test_incomplete_or_duplicate_selected_artifacts_are_not_published(
    ward_files, artifact, bad
):
    path = ward_files[artifact]
    table = pl.read_parquet(path)
    table = table.slice(1) if bad == "missing" else pl.concat([table, table.head(1)])
    table.write_parquet(path)
    ward_files["out"].write_text("previous snapshot")
    run = publish(ward_files)
    assert run.returncode != 0
    assert ward_files["out"].read_text() == "previous snapshot"
    assert not any(i in run.stdout + run.stderr for i in ward_files["ids"])


@pytest.mark.parametrize(
    "column,value", [("cut_s", 90000.0), ("last_valid", 2), ("LABEL//imv_at_cut", True)]
)
def test_scores_from_another_cut_or_support_state_are_refused(
    ward_files, column, value
):
    from app.demo_context import ContextUnavailable

    table = pl.read_parquet(ward_files["scores"])
    table.with_columns(pl.lit(value).alias(column)).write_parquet(ward_files["scores"])
    ward_files["out"].write_text("previous snapshot")
    with pytest.raises(ContextUnavailable, match="cut|labels"):
        publish_direct(ward_files)
    assert ward_files["out"].read_text() == "previous snapshot"


@pytest.mark.parametrize("missing", ["whole-probe", "one-stay", "null-probe"])
def test_unavailable_scores_stay_unknown_in_unit_and_room_context(ward_files, missing):
    table = pl.read_parquet(ward_files["scores"])
    values = (
        [float("nan")] * 26 if missing == "whole-probe" else [float("nan")] + [0.0] * 25
    )
    if missing == "null-probe":
        values = [None] * 26
    table.with_columns(pl.Series(f"{CRRT}_rep_score", values)).write_parquet(
        ward_files["scores"]
    )
    publish_direct(ward_files)
    doc = json.loads(ward_files["out"].read_text())
    assert doc["forecast"]["resources"]["crrt"]["available"] is False
    assert doc["forecast"]["resources"]["crrt"]["expected"] is None
    assert (
        doc["forecast"]["life_support"]["expected_new_patients"]["available"] is False
    )
    room = doc["rooms"]["rooms"][0]
    assert room["p"]["crrt"] is None and room["skipped"]["crrt"] is True
    assert room["any_life_support"] is None
    assert room["on_now"]["crrt"] is False


@pytest.mark.parametrize(
    "bad", ["unrecorded-weights", "another-model", "missing-sidecar"]
)
def test_unverifiable_score_provenance_is_refused(ward_files, bad):
    from app.demo_context import ContextUnavailable

    sidecar = ward_files["scores"].with_suffix(".meta.json")
    meta = json.loads(sidecar.read_text())
    if bad == "unrecorded-weights":
        (ward_files["model"] / "model.safetensors").unlink()
        meta["weights_sha256"] = None
    elif bad == "another-model":
        meta["model"] = "mdl-different"
    else:
        sidecar.unlink()
    if bad != "missing-sidecar":
        sidecar.write_text(json.dumps(meta))
    with pytest.raises(ContextUnavailable, match="provenance"):
        publish_direct(ward_files)
    assert not ward_files["out"].exists()


def test_replay_offset_is_recorded_only_when_it_matches_stored_winnower_cuts(
    ward_files,
):
    from app.demo_context import ContextUnavailable

    for name in ("scores", "labels", "features"):
        path = ward_files[name]
        pl.read_parquet(path).with_columns(
            pl.lit(93600.0).alias("cut_s")
        ).write_parquet(path)
    with pytest.raises(ContextUnavailable, match="cut"):
        publish_direct(ward_files)
    run = publish(ward_files, "--demo-clock-hours", "2")
    assert run.returncode == 0, run.stderr
    doc = json.loads(ward_files["out"].read_text())
    assert doc["forecast"]["demo_clock_hours"] == 2.0
    assert doc["forecast"]["cut_time"] == CUT
    assert "per-stay" in doc["provenance"]["cut_semantics"]


@pytest.mark.parametrize(
    "bad",
    [
        "roster-size",
        "beds",
        "rooms",
        "source",
        "ward",
        "weights",
        "naive-clock",
        "window",
    ],
)
def test_loader_refuses_untrustworthy_envelope_metadata(ward_files, bad):
    from app.demo_context import ContextUnavailable, load_context

    publish_direct(ward_files)
    doc = json.loads(ward_files["out"].read_text())
    if bad == "roster-size":
        doc["roster_size"] = 24
    elif bad == "beds":
        doc["forecast"]["beds"] = 24
    elif bad == "rooms":
        doc["rooms"]["rooms"][1]["room"] = 1
    elif bad == "source":
        doc["source"]["kind"] = "unknown-source"
    elif bad == "ward":
        doc["rooms"]["ward"]["source"] = "open-demo"
    elif bad == "weights":
        doc["provenance"]["weights_sha256"] = None
    elif bad == "naive-clock":
        doc["published_at"] = "2026-11-14T07:00:00"
    else:
        doc["forecast"]["window"]["end"] = CUT
    ward_files["out"].write_text(json.dumps(doc))
    with pytest.raises(ContextUnavailable):
        load_context(ward_files["out"])


@pytest.mark.parametrize("value", [-0.1, 1.1, float("inf"), "0.2"])
def test_invalid_probe_probabilities_are_not_clamped_into_a_forecast(ward_files, value):
    from app.demo_context import ContextUnavailable

    pl.read_parquet(ward_files["scores"]).with_columns(
        pl.lit(value).alias(f"{VASO}_rep_score")
    ).write_parquet(ward_files["scores"])
    with pytest.raises(ContextUnavailable, match="probabilit"):
        publish_direct(ward_files)
    assert not ward_files["out"].exists()


def test_recent_context_never_includes_events_at_or_after_the_stay_cut(ward_files):
    from app.demo_context import ContextUnavailable

    for name in ("scores", "labels", "features"):
        path = ward_files[name]
        table = pl.read_parquet(path).with_columns(pl.lit(6).alias("last_valid"))
        if name == "labels":
            table = table.with_columns(
                pl.Series("tokens_past", [[1, 4, 2, 3, 5, 6]] * 26),
                pl.Series("s_elapsed_past", [[0, 0, 72000, 82800, 86400, 90000]] * 26),
            )
        table.write_parquet(path)
    vocab_path = ward_files["root"] / "vocab.yaml"
    vocab = yaml.safe_load(vocab_path.read_text())
    vocab["lookup"].update({"MED_CON//norepinephrine//H1": 5, "CRRT//crrt_init": 6})
    vocab_path.write_text(yaml.safe_dump(vocab))
    with pytest.raises(ContextUnavailable, match="cut"):
        publish_direct(ward_files)
    assert not ward_files["out"].exists()


@pytest.mark.parametrize(
    "event",
    [
        {"h": 1, "text": "Synthetic observation", "hospitalization_id": "private"},
        {"h": 0, "text": "Synthetic observation"},
        {"h": 1, "text": ["not text"]},
    ],
)
def test_loader_refuses_identifiers_or_invalid_recent_events(ward_files, event):
    from app.demo_context import ContextUnavailable, load_context

    publish_direct(ward_files)
    doc = json.loads(ward_files["out"].read_text())
    doc["rooms"]["rooms"][0]["past_12h"] = [event]
    ward_files["out"].write_text(json.dumps(doc))
    with pytest.raises(ContextUnavailable):
        load_context(ward_files["out"])


def test_missing_selected_clif_hospitalization_is_not_published(ward_files):
    from app.demo_context import ContextUnavailable

    hospital = ward_files["clif"] / "clif_hospitalization.parquet"
    pl.read_parquet(hospital).slice(1).write_parquet(hospital)
    with pytest.raises(ContextUnavailable, match="CLIF"):
        publish_direct(ward_files)


@pytest.mark.parametrize("bad", ["missing", "null", "string"])
def test_unknown_observed_support_is_not_converted_to_off(ward_files, bad):
    from app.demo_context import ContextUnavailable

    for name in ("scores", "labels"):
        path = ward_files[name]
        frame = pl.read_parquet(path)
        column = "LABEL//imv_at_cut"
        frame = (
            frame.drop(column)
            if bad == "missing"
            else frame.with_columns(
                pl.lit(None if bad == "null" else "False").alias(column)
            )
        )
        frame.write_parquet(path)
    with pytest.raises(ContextUnavailable, match="support"):
        publish_direct(ward_files)


def test_cohort_identity_uses_the_roster_mapping_and_source_not_csv_order(ward_files):
    publish_direct(ward_files)
    first = json.loads(ward_files["out"].read_text())
    pl.read_csv(ward_files["roster"]).reverse().write_csv(ward_files["roster"])
    publish_direct(ward_files)
    second = json.loads(ward_files["out"].read_text())
    assert first["cohort_id"] == second["cohort_id"]
    assert first["snapshot_id"] != second["snapshot_id"]
    publish_direct(ward_files, dataset_version="synthetic-v2")
    third = json.loads(ward_files["out"].read_text())
    assert third["cohort_id"] != second["cohort_id"]
    assert third["source"]["dataset_version"] == "synthetic-v2"
    assert ward_files["out"].stat().st_mode & 0o077 == 0
    assert ward_files["out"].stat().st_size < 100_000


def test_failed_atomic_replace_preserves_previous_snapshot_and_cleans_tempfile(
    ward_files, monkeypatch
):
    from app import demo_context

    publish_direct(ward_files)
    previous = ward_files["out"].read_bytes()

    def unavailable_disk(*_):
        raise OSError("synthetic filesystem failure")

    monkeypatch.setattr(demo_context.os, "replace", unavailable_disk)
    with pytest.raises(OSError):
        publish_direct(ward_files)
    assert ward_files["out"].read_bytes() == previous
    assert not list(ward_files["out"].parent.glob(".context-*"))


def test_loader_import_does_not_import_the_data_or_model_stack():
    run = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from app.demo_context import load_context; "
            "assert not ({'polars', 'numpy', 'torch', 'sklearn'} & set(sys.modules))",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr


def test_ready_context_uses_clif_native_current_support_and_exclusion(ward_files):
    path = ward_files["clif"] / "clif_respiratory_support.parquet"
    first = ward_files["ids"][0]
    pl.read_parquet(path).with_columns(
        pl.when(pl.col("hospitalization_id") == first)
        .then(pl.lit("IMV"))
        .otherwise(pl.col("device_category"))
        .alias("device_category")
    ).write_parquet(path)
    publish_direct(ward_files)
    doc = json.loads(ward_files["out"].read_text())
    assert doc["forecast"]["on_now_source"] == doc["rooms"]["on_now_source"] == "clif"
    assert doc["forecast"]["life_support"]["now_by"]["imv"] == 1
    assert doc["rooms"]["rooms"][0]["on_now"]["imv"] is True
    assert doc["rooms"]["rooms"][0]["p"]["imv"] is None
    assert doc["forecast"]["resources"]["ventilator"]["expected"] == 0
    assert "2160" not in ward_files["out"].read_text()


def test_clif_unknown_device_stays_unknown_without_token_fallback(ward_files):
    path = ward_files["clif"] / "clif_respiratory_support.parquet"
    pl.read_parquet(path).slice(1).write_parquet(path)
    publish_direct(ward_files)
    doc = json.loads(ward_files["out"].read_text())
    assert doc["rooms"]["rooms"][0]["on_now"]["imv"] is None
    now = doc["forecast"]["life_support"]
    assert now["now_by"]["imv"] is None
    assert now["now_known_by"]["imv"] == 0 and now["now_unknown_by"]["imv"] == 1
    assert now["now_patients"] is None
    assert now["now_known_patients"] == 0 and now["now_unknown_patients"] == 1


def cohort_tokens(files):
    """A prepared selected-25 token cache, with no model invocation."""
    first = SOURCE_START.astimezone(zoneinfo.ZoneInfo("US/Eastern")).replace(
        tzinfo=None
    )
    data = []
    for sid in files["ids"][:25]:
        for pos, (seconds, token) in enumerate(
            [(0, 1), (0, 4), (82800, 3), (172800, 3)]
        ):
            data.append((sid, first + dt.timedelta(seconds=seconds), token, 80.0, pos))
    frame = pl.DataFrame(
        data,
        schema={
            "hospitalization_id": pl.String,
            "event_time": pl.Datetime("us"),
            "token_id": pl.Int64,
            "value": pl.Float64,
            "position_id": pl.Int64,
        },
        orient="row",
    )
    for split in ("train", "tuning", "held_out"):
        (frame if split == "held_out" else frame.head(0)).write_parquet(
            files["root"] / f"tokens_{split}.parquet"
        )


def run_cohort(files, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/run_cohort.py"),
            str(files["clif"]),
            "--ward-ids",
            str(files["roster"]),
            "--real-ward",
            "--tokenized-output",
            str(files["root"]),
            "--work",
            str(files["out"].parent / "work"),
            "--out",
            str(files["out"].parent / "views"),
            "--context-out",
            str(files["out"]),
            "--cut-time",
            CUT,
            *extra,
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_cohort_cpu_publishes_explicit_pending_model_from_same_ward(ward_files):
    from app.demo_context import load_context, read_roster

    cohort_tokens(ward_files)
    run = run_cohort(ward_files)
    assert run.returncode == 0, run.stderr
    doc = load_context(ward_files["out"])
    assert (
        doc["forecast_state"]
        == doc["forecast"]["forecast_state"]
        == doc["rooms"]["forecast_state"]
        == "pending-model"
    )
    assert (
        doc["provenance"]["model"] is None
        and doc["provenance"]["weights_sha256"] is None
    )
    assert doc["forecast"]["life_support"]["now_patients"] == 0
    assert set(doc["forecast"]["resources"]) == {
        "ventilator",
        "vasopressor",
        "crrt",
        "death",
        "icu_departure",
    }
    assert all(
        x["available"] is False and x["expected"] is None
        for x in doc["forecast"]["resources"].values()
    )
    assert all(
        r["present"] is True and all(p is None for p in r["p"].values())
        for r in doc["rooms"]["rooms"]
    )
    assert not any(
        i in ward_files["out"].read_text() + run.stdout + run.stderr
        for i in ward_files["ids"]
    )
    assert "2160" not in ward_files["out"].read_text()
    assert len(pl.read_csv(ward_files["out"].parent / "work/roster.csv")) == 25
    assert read_roster(ward_files["out"].parent / "work/roster.csv") == read_roster(
        ward_files["roster"]
    )


def test_ended_stay_keeps_its_slot_cleared_and_preserves_cohort_identity(ward_files):
    from app.demo_context import load_context

    cohort_tokens(ward_files)
    assert run_cohort(ward_files).returncode == 0
    before = load_context(ward_files["out"])
    path = ward_files["clif"] / "clif_hospitalization.parquet"
    pl.read_parquet(path).with_columns(
        pl.when(pl.col("hospitalization_id") == ward_files["ids"][0])
        .then(pl.lit(SOURCE_START + dt.timedelta(hours=12)))
        .otherwise(pl.col("discharge_dttm"))
        .alias("discharge_dttm")
    ).write_parquet(path)
    run = run_cohort(ward_files)
    assert run.returncode == 0, run.stderr
    after = load_context(ward_files["out"])
    assert after["cohort_id"] == before["cohort_id"]
    assert after["forecast"]["beds"] == 24 and after["rooms"]["dropped"] == 1
    room = after["rooms"]["rooms"][0]
    assert room["present"] is False and room["age"] is None and room["past_12h"] == []
    assert all(v is None for v in room["on_now"].values())
    assert all(v is None for v in room["p"].values())


@pytest.mark.parametrize("bad", ["weights", "probability", "horizon"])
def test_pending_snapshot_cannot_carry_model_provenance_or_estimates(ward_files, bad):
    from app.demo_context import ContextUnavailable, load_context

    cohort_tokens(ward_files)
    assert run_cohort(ward_files).returncode == 0
    doc = load_context(ward_files["out"])
    if bad == "weights":
        doc["provenance"]["weights_sha256"] = "a" * 64
    elif bad == "probability":
        doc["rooms"]["rooms"][0]["p"]["imv"] = 0.1
    else:
        doc["forecast"]["horizons"]["24h"]["resources"]["ventilator"]["expected"] = 2
    ward_files["out"].write_text(json.dumps(doc))
    with pytest.raises(ContextUnavailable):
        load_context(ward_files["out"])


def test_run_cohort_no_extract_applies_saved_probe_manifest_to_existing_features(
    ward_files,
):
    from app.demo_context import load_context

    cohort_tokens(ward_files)
    assert run_cohort(ward_files).returncode == 0
    labels = pl.read_parquet(ward_files["labels"])
    labels.select("hospitalization_id", "last_valid", "cut_s").with_columns(
        pl.Series("features", [[0.0]] * labels.height)
    ).write_parquet(ward_files["features"])
    probes = ward_files["out"].parent / "probes"
    probes.mkdir()
    tasks = yaml.safe_load((REPO / "examples/probe_tasks.yaml").read_text())["score"][
        "target_tokens"
    ]
    manifest = {
        "model": ward_files["model"].name,
        "features": 1,
        "weights_sha256": json.loads(
            ward_files["scores"].with_suffix(".meta.json").read_text()
        )["weights_sha256"],
        "tokens": {t: {"file": None} for t in tasks},
    }
    (probes / "manifest.json").write_text(json.dumps(manifest))
    reuse = (
        "--model",
        str(ward_files["model"]),
        "--probes",
        str(probes),
        "--no-extract",
    )
    # CodeRabbit PR #16: features that do not say which weights made them (a file
    # from before the digest was recorded), or that name other weights, are not
    # reused: the earlier snapshot stays and the run says to extract again
    from icutwin.scoring import rep_based

    before = ward_files["out"].read_text()
    rep_based.features_meta_path(ward_files["features"]).unlink()
    for digest in (None, "0" * 64):
        if digest:
            rep_based.features_meta_path(ward_files["features"]).write_text(
                json.dumps({"model": manifest["model"], "weights_sha256": digest})
            )
        run = run_cohort(ward_files, *reuse)
        assert run.returncode != 0
        assert ward_files["out"].read_text() == before
    rep_based.write_features_meta(ward_files["features"], ward_files["model"])
    run = run_cohort(ward_files, *reuse)
    assert run.returncode == 0, run.stderr
    doc = load_context(ward_files["out"])
    assert doc["forecast_state"] == "ready"
    assert doc["provenance"]["weights_sha256"] == manifest["weights_sha256"]
    assert (
        doc["provenance"]["probes_sha256"]
        == hashlib.sha256((probes / "manifest.json").read_bytes()).hexdigest()
    )


def test_atomic_context_preserves_fictional_names_and_custom_unit(ward_files):
    from app.demo_context import load_context

    cohort_tokens(ward_files)
    run = run_cohort(ward_files, "--names", "fake", "--unit-name", "Cardiac ICU")
    assert run.returncode == 0, run.stderr
    doc = load_context(ward_files["out"])
    assert doc["forecast"]["unit_name"] == "Cardiac ICU"
    assert doc["rooms"]["names"] == "fictional"
    assert all(r["name"]["fictional"] is True for r in doc["rooms"]["rooms"])
    assert not any(
        r["name"]["display"] in run.stdout + run.stderr for r in doc["rooms"]["rooms"]
    )


@pytest.mark.parametrize("score_files", ["retain", "omit"])
def test_publisher_verifies_scores_for_the_active_census(ward_files, score_files):
    """CodeRabbit PR #16: one roster stay has ended. Scores are verified for the 24
    stays present, whether the score files still hold the ended stay or not; the
    roster keeps all 25 room slots."""
    from app.demo_context import load_context

    ended = ward_files["ids"][0]
    path = ward_files["clif"] / "clif_hospitalization.parquet"
    pl.read_parquet(path).with_columns(
        pl.when(pl.col("hospitalization_id") == ended)
        .then(pl.lit(SOURCE_START + dt.timedelta(hours=12)))
        .otherwise(pl.col("discharge_dttm"))
        .alias("discharge_dttm")
    ).write_parquet(path)
    if score_files == "omit":
        for name in ("scores", "labels", "features"):
            pl.read_parquet(ward_files[name]).filter(
                pl.col("hospitalization_id") != ended
            ).write_parquet(ward_files[name])
    assert publish_direct(ward_files)["rooms_written"] == 25
    context = load_context(ward_files["out"])
    assert context["forecast"]["beds"] == 24 and context["rooms"]["dropped"] == 1
    room = context["rooms"]["rooms"][0]
    assert room["room"] == 1 and room["present"] is False
    assert all(v is None for v in room["p"].values())
    assert sum(r["present"] for r in context["rooms"]["rooms"]) == 24

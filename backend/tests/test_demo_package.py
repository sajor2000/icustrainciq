"""Code-only handoff and synthetic selected-cohort preparation contracts."""

import csv
import datetime as dt
import hashlib
import json
import pathlib
import shlex
import shutil
import sys
import tarfile

import polars as pl
import pytest
import yaml

from app import board
from app.demo_context import ContextUnavailable
from app.dispatcher import render_template
from scripts import package_lookahead_demo as packaging
from scripts import prepare_lookahead_cohort as cohort


@pytest.fixture
def source_repo(tmp_path):
    """Copy eligible code only, then introduce excluded synthetic decoys."""
    root = tmp_path / "source"
    repo = pathlib.Path(__file__).resolve().parents[1]
    for rel in packaging.source_files(repo):
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, target)
    for name in (
        "app/roster.csv",
        "app/context.json",
        "app/data/rows.py",
        "app/credentials.py",
        "icutwin/model/weights.safetensors",
        ".env",
        ".git/config",
        ".venv/private.py",
        "clif_demo/rows.parquet",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("SYNTHETIC DECOY: must not enter deployment archive")
    return root


def test_archive_contains_runtime_code_and_verifiable_manifest_only(
    source_repo, tmp_path
):
    output = tmp_path / "lookahead.tar.gz"
    packaging.package(source_repo, output)
    with tarfile.open(output) as archive:
        names = set(archive.getnames())
        assert "code/app/demo_context.py" in names
        assert "code/scripts/prepare_lookahead_cohort.py" in names
        assert "code/fuzzball/t7-lookahead-chat.fz" in names
        assert "code/fuzzball/t7-lookahead-prepare.fz" in names
        assert "code/scripts/run_cohort.py" in names
        assert "code/app/clif_now.py" in names
        assert "code/app/fake_names.py" in names
        assert "code/requirements/t7-model.txt" in names
        assert "code/docs/CLAUDE_WORKFLOW_ALIGNMENT.md" in names
        assert all(member.isfile() for member in archive.getmembers())
        assert not any(
            "SYNTHETIC DECOY"
            in archive.extractfile(name).read().decode(errors="ignore")
            for name in names
        )
        manifest = json.load(archive.extractfile("code/LOOKAHEAD_PACKAGE.json"))
        assert manifest["kind"] == "lookahead-code-only"
        for entry in manifest["files"]:
            data = archive.extractfile("code/" + entry["path"]).read()
            assert entry["sha256"] == hashlib.sha256(data).hexdigest()
    before = output.read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        packaging.package(source_repo, output)
    assert output.read_bytes() == before


def test_archive_rejects_source_symlinks_and_synced_destination(source_repo, tmp_path):
    link = source_repo / "app" / "linked.py"
    link.symlink_to(tmp_path / "outside.py")
    with pytest.raises(ValueError, match="symlink"):
        packaging.package(source_repo, tmp_path / "linked.tar.gz")
    link.unlink()
    with pytest.raises(ValueError, match="unsynced"):
        packaging.package(source_repo, tmp_path / "Dropbox" / "lookahead.tar.gz")


@pytest.mark.parametrize("folder", ("app", "icutwin", "docs", "fuzzball"))
def test_archive_rejects_symlinked_source_parent(source_repo, tmp_path, folder):
    original = source_repo / folder
    outside = tmp_path / "external" / folder
    outside.parent.mkdir(exist_ok=True)
    original.rename(outside)
    original.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        packaging.package(source_repo, tmp_path / "symlink-parent.tar.gz")


def test_archive_stages_exact_frontend_without_editing_repository(
    source_repo, tmp_path
):
    frontend = tmp_path / "mockups" / "command-center.html"
    frontend.parent.mkdir()
    expected = b"<!doctype html><title>SYNTHETIC APPROVED FRONTEND</title>\n"
    frontend.write_bytes(expected)
    original = (source_repo / "app/static/index.html").read_bytes()
    output = tmp_path / "approved-front.tar.gz"
    packaging.package(source_repo, output, frontend)
    with tarfile.open(output) as archive:
        assert archive.extractfile("code/app/static/index.html").read() == expected
        manifest = json.load(archive.extractfile("code/LOOKAHEAD_PACKAGE.json"))
        assert manifest["frontend"] == {
            "source": "explicit-html",
            "source_name": "command-center.html",
            "sha256": hashlib.sha256(expected).hexdigest(),
            "bytes": len(expected),
        }
    assert (source_repo / "app/static/index.html").read_bytes() == original


def test_frontend_override_rejects_data_path_and_symlink_parent(source_repo, tmp_path):
    data_source = tmp_path / "data" / "page.html"
    data_source.parent.mkdir()
    data_source.write_text("<title>SYNTHETIC NON-SOURCE</title>")
    with pytest.raises(ValueError, match="outside data"):
        packaging.package(source_repo, tmp_path / "data-front.tar.gz", data_source)
    linked = tmp_path / "linked"
    linked.symlink_to(data_source.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        packaging.package(
            source_repo, tmp_path / "linked-front.tar.gz", linked / "page.html"
        )


def test_workflow_board_cli_enables_https_proxy_and_publish_env_is_self_contained(
    monkeypatch,
):
    root = pathlib.Path(__file__).resolve().parents[1]
    chat = yaml.safe_load((root / "fuzzball/t7-lookahead-chat.fz").read_text())
    script = chat["services"]["board"]["script"]
    command = (
        script[script.index("python /store/code/app/board.py") :]
        .replace("\\\n", " ")
        .split("||", 1)[0]
    )
    args = shlex.split(command)[2:]
    # Exercise the real argument parser without starting a socket or reading data.
    got = {}
    monkeypatch.setattr(sys, "argv", ["board.py", *args])
    monkeypatch.setattr(board, "make_handler", lambda *a: got.update(handler=a))

    class NoSocketServer:
        def __init__(self, *a):
            pass

        def serve_forever(self):
            pass

    monkeypatch.setattr(board, "ThreadingHTTPServer", NoSocketServer)
    board.main()
    assert got["handler"][4] is True
    assert got["handler"][5] == pathlib.Path("/context/context.json")
    assert got["handler"][6] is True
    forecast = yaml.safe_load(
        render_template(
            (root / "fuzzball/t7-lookahead-forecast.fz").read_text(),
            cut="2026-11-14T07:00:00-06:00",
            real_ward=True,
            clif_dir="/context/clif",
            ward_ids="/context/cohort_ids.csv",
            names="fake",
        )
    )
    env = dict(item.split("=", 1) for item in forecast["jobs"]["publish"]["env"])
    assert env["PYTHONPATH"] == "/store/py:/store/code"
    assert env["TMPDIR"] == "/tmp"
    assert env["TZ"] == "America/Chicago"
    assert env["CLIF_DIR"] == "/context/clif"
    assert "HOME" not in env
    assert "--no-extract" in forecast["jobs"]["publish"]["script"]
    assert "--ward-ids /context/cohort_ids.csv" in forecast["jobs"]["publish"]["script"]
    assert "--names fake" in forecast["jobs"]["publish"]["script"]
    assert not forecast["jobs"]["extract"]["resource"].get("exclusive")
    assert forecast["jobs"]["extract"]["resource"]["cpu"]["cores"] == 8


def test_initial_context_preparation_is_cpu_only_and_separate_from_chat():
    root = pathlib.Path(__file__).resolve().parents[1]
    prepare = yaml.safe_load((root / "fuzzball/t7-lookahead-prepare.fz").read_text())
    chat = yaml.safe_load((root / "fuzzball/t7-lookahead-chat.fz").read_text())
    assert not chat.get("jobs")
    assert not prepare.get("services")
    job = prepare["jobs"]["prepare-context"]
    assert not job["resource"].get("devices")
    assert "--model" not in job["script"] and "--probes" not in job["script"]
    assert "--ward-ids /context/cohort_ids.csv" in job["script"]
    assert "--context-out /context/context.json" in job["script"]
    assert not {"clif", "rows"}.intersection(prepare["volumes"])


@pytest.fixture
def prepared_tokens(tmp_path):
    source = tmp_path / "prepared"
    source.mkdir()
    ids = [f"synthetic-{i}" for i in range(25)]
    roster = tmp_path / "roster.csv"
    with roster.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["room", "hospitalization_id"])
        writer.writerows((i + 1, sid) for i, sid in enumerate(ids))
    frame = pl.DataFrame(
        {
            "hospitalization_id": ids + ["synthetic-unselected"],
            "token_id": list(range(26)),
            "position_id": [0] * 26,
            "event_time": [dt.datetime(2020, 1, 1)] * 26,
            "value": [0.0] * 26,
        }
    )
    frame.write_parquet(source / "tokens_held_out.parquet")
    for split in ("train", "tuning"):
        frame.filter(
            pl.col("hospitalization_id") == "synthetic-unselected"
        ).write_parquet(source / f"tokens_{split}.parquet")
    (source / "vocab.yaml").write_text("lookup: {SYNTHETIC: 1}\n")
    return source, roster, ids


def test_selected_cache_excludes_other_stays_and_detects_changed_roster(
    prepared_tokens, tmp_path
):
    source, roster, ids = prepared_tokens
    out = tmp_path / "context" / "tokenized_output"
    receipt = cohort.prepare(source, roster, out)
    assert receipt == {
        "prepared": True,
        "roster_size": 25,
        "split": "held_out",
        "token_rows": 25,
    }
    selected = pl.read_parquet(out / "tokens_held_out.parquet")
    assert set(selected["hospitalization_id"]) == set(ids)
    assert all(
        pl.read_parquet(out / f"tokens_{split}.parquet").is_empty()
        for split in ("train", "tuning")
    )
    assert not list(out.glob("features*")) and not list(out.glob("scores*"))
    cohort.check_cache(out, roster)
    # A valid replacement roster cannot silently reuse the previous selection.
    roster.write_text(
        roster.read_text().replace("synthetic-0\n", "synthetic-replacement\n")
    )
    with pytest.raises(ContextUnavailable, match="inconsistent"):
        cohort.check_cache(out, roster)


def test_selected_cache_refuses_training_overlap_and_incomplete_selection(
    prepared_tokens, tmp_path
):
    source, roster, ids = prepared_tokens
    train = source / "tokens_train.parquet"
    pl.DataFrame(
        {"hospitalization_id": [ids[0]], "token_id": [0], "position_id": [0]}
    ).write_parquet(train)
    with pytest.raises(ContextUnavailable, match="overlaps"):
        cohort.prepare(source, roster, tmp_path / "overlap")
    pl.read_parquet(train).head(0).write_parquet(train)
    held = source / "tokens_held_out.parquet"
    pl.read_parquet(held).filter(pl.col("hospitalization_id") != ids[0]).write_parquet(
        held
    )
    with pytest.raises(ContextUnavailable, match="not complete"):
        cohort.prepare(source, roster, tmp_path / "incomplete")

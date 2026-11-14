# ruff: noqa: E501
"""Made-up names on the room tiles: generator, names file, rooms.json, chat, logs."""

import json
import logging
import re

import polars as pl
import pytest
import test_chat_agent as tca
import test_cohort as tc
import test_lookahead as tl

from app import aggregate, fake_names, rooms, ward_check
from app import dispatcher as d

HOSP = "hospitalization_id"
SHAPE = re.compile(r"[A-Za-z][A-Za-z '-]*, [A-Z]\.")


def _names_file(path, rows, source="fictional"):
    pl.DataFrame(
        {
            HOSP: [r[0] for r in rows],
            "patient_id": [f"p{i}" for i in range(len(rows))],
            "first_name": [r[1] for r in rows],
            "last_name": [r[2] for r in rows],
            "display_name": [f"{r[2]}, {r[1][:1]}." for r in rows],
            "name_source": [source] * len(rows),
        }
    ).write_parquet(path)
    return path


def test_generator_is_seeded_sex_aware_and_needs_no_id():
    a = [fake_names.fake_name(r, "F") for r in range(1, 26)]
    assert a == [fake_names.fake_name(r, "F") for r in range(1, 26)]  # same every run
    assert all(n["fictional"] is True and SHAPE.fullmatch(n["display"]) for n in a)
    assert all(n["first"] in fake_names.FIRST_F for n in a)
    assert all(
        fake_names.fake_name(r, "M")["first"] in fake_names.FIRST_M
        for r in range(1, 26)
    )
    assert fake_names.fake_name(3)["first"] in fake_names.FIRST_F + fake_names.FIRST_M
    assert (
        len({fake_names.fake_name(r)["last"] for r in range(1, 51)}) == 50
    )  # no twins
    assert fake_names.fake_name(4, "F", seed=1) != fake_names.fake_name(4, "F", seed=2)
    assert all(fake_names.valid(x) for x in fake_names.LAST + fake_names.FIRST_F)
    ward = fake_names.for_ward({"x": 1, "y": 2}, {"x": "M"})
    assert ward["x"] == fake_names.fake_name(1, "M") and set(ward) == {"x", "y"}


def test_only_clean_strings_are_names():
    for ok in ("Rivera, J.", "O'Neil", "Anne-Marie", "de la Cruz", "Zoë"):
        assert fake_names.valid(ok), ok
    for bad in ("", "x" * 41, "<b>Rivera</b>", "Rivera; DROP", "R1vera", "a\nb", " lead",
                "Rivera_J", 'Ri"vera', "{{x}}", None, 7):  # fmt: skip
        assert not fake_names.valid(bad), bad


def test_names_file_loads_and_bad_rows_or_real_names_are_refused(tmp_path):
    f = _names_file(
        tmp_path / "n.parquet", [("s0", "Jo", "Rivera"), ("s1", "Al", "Novak")]
    )
    got = fake_names.load(f)
    assert got["s0"] == {
        "display": "Rivera, J.",
        "first": "Jo",
        "last": "Rivera",
        "fictional": True,
    }
    bad = _names_file(
        tmp_path / "bad.parquet", [("s0", "Jo", "<script>"), ("s1", "Al", "Novak")]
    )
    with pytest.raises(SystemExit) as e:
        fake_names.load(bad)
    assert "1 of 2 rows" in str(e.value) and "script" not in str(e.value)
    real = _names_file(
        tmp_path / "real.parquet", [("s0", "Jo", "Rivera")], source="adt"
    )
    with pytest.raises(SystemExit, match='not name_source "fictional"'):
        fake_names.load(real)
    pl.DataFrame({HOSP: ["s0"]}).write_parquet(tmp_path / "cols.parquet")
    with pytest.raises(SystemExit, match="lacks column"):
        fake_names.load(tmp_path / "cols.parquet")
    with pytest.raises(SystemExit, match="not found"):
        fake_names.load(tmp_path / "nope.parquet")
    names, counts = fake_names.names_for(str(f), {"s0": 1, "s9": 2})
    assert set(names) == {"s0"} and counts == {
        "names": "fictional",
        "named": 1,
        "unnamed": 1,
    }
    assert fake_names.names_for(None, {"s0": 1}) == (None, {"names": "off"})


def test_rooms_json_has_names_only_when_asked_and_stdout_has_none(
    tmp_path, monkeypatch, capsys
):
    ids = [f"pat-{i}" for i in range(4)]
    demo = tmp_path / "demo_hosp.parquet"  # stands in for the open demo's stay list
    pl.DataFrame({HOSP: ids}).write_parquet(demo)
    monkeypatch.setattr(aggregate, "DEMO_HOSP", demo)
    root = tl._stage(tmp_path, ids)
    doc = tl._run(monkeypatch, tmp_path, root)
    assert "names" not in doc and all("name" not in r for r in doc["rooms"])
    f = _names_file(
        tmp_path / "n.parquet",
        [("pat-0", "Jo", "Quillfeather"), ("pat-2", "Al", "Marrowby")],
    )
    capsys.readouterr()
    doc = tl._run(monkeypatch, tmp_path, root, "--names", str(f))
    out = capsys.readouterr().out
    assert doc["names"] == "fictional"
    by = {r["room"]: r for r in doc["rooms"]}
    assert by[1]["name"] == {
        "display": "Quillfeather, J.",
        "first": "Jo",
        "last": "Quillfeather",
        "fictional": True,
    }
    assert (
        "name" not in by[2] and by[3]["name"]["last"] == "Marrowby"
    )  # no row: no name
    assert '"named": 2' in out and '"unnamed": 2' in out  # counts, never the id
    assert "Quillfeather" not in out and "Marrowby" not in out and "pat-" not in out
    assert "pat-" not in json.dumps(doc)
    # the generator: every room named, the same on every run
    gen = tl._run(monkeypatch, tmp_path, root, "--names", "fake")
    again = tl._run(monkeypatch, tmp_path, root, "--names", "fake")
    assert [r["name"] for r in gen["rooms"]] == [r["name"] for r in again["rooms"]]
    assert all(r["name"]["fictional"] is True for r in gen["rooms"])
    assert gen["rooms"][0]["name"] == fake_names.fake_name(1, gen["rooms"][0]["sex"])
    # a room update keeps the other rooms' names; without --names that room has none
    one = tl._run(monkeypatch, tmp_path, root, "--room", "2")
    assert "name" not in one["rooms"][1] and "name" in one["rooms"][0]
    assert one["names"] == "fictional"
    # a bad names file stops the run before anything is written
    bad = _names_file(tmp_path / "bad.parquet", [("pat-0", "Jo", "x<y")])
    with pytest.raises(SystemExit):
        tl._run(monkeypatch, tmp_path, root, "--names", str(bad))


def test_room_entries_take_names_by_stay_and_keep_the_key_out_otherwise():
    import datetime as dt

    cut = dt.datetime(2026, 11, 14, 7, tzinfo=dt.timezone.utc)
    room_of = {f"s{i}": i + 1 for i in range(3)}
    got = rooms.room_entries(
        tl.scores(3),
        room_of,
        {},
        cut,
        "now",
        names={"s1": fake_names.entry("Jo", "Novak")},
    )
    assert [("name" in r) for r in got] == [False, True, False]
    assert got[1]["name"]["display"] == "Novak, J."


def test_cohort_script_names_and_unit_name(demo_run, capsys):
    tmp, args, ids = demo_run
    capsys.readouterr()
    tc.run_cohort.main(
        [
            *args,
            "--reuse-tokens",
            "--out",
            str(tmp / "named"),
            "--names",
            "fake",
            "--unit-name",
            "Cardiac ICU",
        ]  # fmt: skip
    )
    out = capsys.readouterr().out
    r, f = tc._docs(tmp / "named")
    assert r["names"] == "fictional" and all(x["name"]["fictional"] for x in r["rooms"])
    assert f["unit_name"] == "Cardiac ICU"
    assert tc._docs(tmp / "out")[1]["unit_name"] == "Medical ICU"  # the default
    assert "names" not in tc._docs(tmp / "out")[0]
    shown = {x["name"]["last"] for x in r["rooms"]} | {
        x["name"]["first"] for x in r["rooms"]
    }
    assert not any(n in out for n in shown)  # stdout: counts only
    assert f'"named": {len(r["rooms"])}' in out
    assert not any(n in json.dumps(f) for n in {x["name"]["last"] for x in r["rooms"]})


demo_run = tc.demo_run


def test_unit_name_default_and_cli(tmp_path):
    assert aggregate.build_forecast(tl.scores(3), "m")["unit_name"] == "Medical ICU"
    fc = aggregate.build_forecast(tl.scores(3), "m", unit_name="Surgical ICU")
    assert fc["unit_name"] == "Surgical ICU"


def test_ward_check_counts_the_names_file(tmp_path):
    ids = pl.read_parquet(
        tc.DEMO / "clif_hospitalization.parquet", columns=[HOSP]
    ).head(5)
    f = tmp_path / "ids.parquet"
    ids.write_parquet(f)
    n = _names_file(tmp_path / "n.parquet", [(ids[HOSP][0], "Jo", "Novak")])
    import unittest.mock as mock

    with mock.patch.object(
        aggregate, "DEMO_HOSP", tc.DEMO / "clif_hospitalization.parquet"
    ):
        rep = ward_check.check(tc.DEMO, f, names=str(n))
    assert (rep["names"], rep["named"], rep["unnamed"]) == ("fictional", 1, 4)
    assert "Novak" not in json.dumps(rep)


def test_chat_get_room_carries_the_made_up_name_and_the_log_does_not(
    env, tmp_path, caplog
):
    doc = {
        "ward": {"source": "open-demo", "label": "Open MIMIC-IV Demo"},
        "names": "fictional",
        "rooms": [
            {
                "room": 7,
                "level": "high",
                "p": {"imv": 0.3},
                "name": fake_names.entry("Jo", "Quillfeather"),
            }  # fmt: skip
        ],
    }
    (tmp_path / "rooms.json").write_text(json.dumps(doc))
    f, a = env(
        [tca.tc("get_room", {"room": 7}), tca.text("Room 7 (Quillfeather, J.): ok")]
    )
    with caplog.at_level(logging.INFO):
        out = a.ask("how is room 7?", "ICU nurse", 7)
    assert "Quillfeather, J." in tca.tool_msgs(f)[0]["content"]  # the model may say it
    assert "Quillfeather" in out["answer"]
    assert "Quillfeather" not in caplog.text and "get_room" in caplog.text


env = tca.env


def test_names_token_renders_off_by_default_and_never_reaches_the_run_log(tmp_path):
    import yaml

    for name in ("t7-forecast", "t7-ward"):
        assert "--names" not in "".join(
            j["script"] for j in yaml.safe_load(tc_render(name))["jobs"].values()
        )
    on = dict(names="/data/dashboard_data/name.parquet")
    s = yaml.safe_load(tc_render("t7-forecast", **on))["jobs"]["score"]["script"]
    assert "$WARD --names /data/dashboard_data/name.parquet" in s
    w = yaml.safe_load(tc_render("t7-ward", **on))["jobs"]["load"]["script"]
    assert "--names /data/dashboard_data/name.parquet --expect-ids 25" in w
    assert d.render_ward("[@NAMES@]", names="fake") == "[--names fake]"
    with pytest.raises(ValueError):
        d.render_ward("@NAMES@", names="/x; cat /etc/passwd")
    from test_dispatcher import FakeCli

    f = FakeCli(tmp_path)
    f.names = "/data/dashboard_data/name.parquet"
    f.start("ICU nurse", "room", 3)
    log_text = (tmp_path / "runs.jsonl").read_text()
    row = json.loads(log_text.splitlines()[-1])
    assert set(row) <= {
        "at",
        "trigger",
        "scope",
        "room",
        "started",
        "workflow",
        "name",
        "ward",
    }
    assert row["name"].startswith(
        "t7-lookahead-forecast-room3-"
    )  # the run's name, not a person's


def tc_render(name, **ward):
    from test_dispatcher import render_any

    return render_any(name, **ward)

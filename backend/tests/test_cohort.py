"""A given ward end to end: the room map from an id file, the laptop pipeline on the
open MIMIC-IV Demo (never real patients), the pending-model files, the shared demo
day, the board's --host. Synthetic frames or backend/clif_demo only."""

import datetime as dt
import importlib.util
import json
import pathlib
import re
import threading
import urllib.request

import numpy as np
import polars as pl
import pytest
import test_lookahead as tl

from app import aggregate, board, rooms, stage_ward, ward_check

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DEMO = BACKEND / "clif_demo"
HOSP = "hospitalization_id"
YEAR_2100_UP = re.compile(r"(?<!\d)2[1-9]\d{2}(?!\d)")

spec = importlib.util.spec_from_file_location(
    "run_cohort", BACKEND / "scripts" / "run_cohort.py"
)
run_cohort = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_cohort)


# ---- the room map from an id file ---------------------------------------------


def _hosp(tmp_path, ids):
    d = tmp_path / "clif"
    d.mkdir(exist_ok=True)
    pl.DataFrame({HOSP: ids}).write_parquet(d / "clif_hospitalization.parquet")
    return d


def test_rooms_from_ids_is_a_stable_shuffle_not_the_id_order():
    ids = [f"id{i:03d}" for i in range(25)]
    a = stage_ward.rooms_from_ids(ids)
    b = stage_ward.rooms_from_ids(list(reversed(ids)))  # input order does not matter
    assert a.equals(b)
    assert a.columns == ["room", HOSP, "score"]
    assert a["room"].to_list() == list(range(1, 26))
    assert sorted(a[HOSP]) == ids and a[HOSP].to_list() != ids
    assert stage_ward.rooms_from_ids(ids, seed=1)[HOSP].to_list() != a[HOSP].to_list()


def test_ward_ids_need_real_ward_outside_the_open_demo(tmp_path, monkeypatch, capsys):
    ids = [f"zq-{i}" for i in range(5)]
    clif = _hosp(tmp_path, ids)
    f = tmp_path / "ids.parquet"
    pl.DataFrame({HOSP: ids}).write_parquet(f)
    with pytest.raises(SystemExit) as e:
        stage_ward.ward_from_ids(clif, f)
    assert "5 of 5" in str(e.value) and "zq-" not in str(e.value)
    out = tmp_path / "ward.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "stage_ward",
            str(clif),
            "--ward-ids",
            str(f),
            "--real-ward",
            "--out",
            str(out),
        ],
    )
    stage_ward.main()
    printed = capsys.readouterr().out
    assert "'ward': 'mimic-iv'" in printed and "zq-" not in printed
    assert "ids_digest" not in printed  # no digest of real ids
    room_of = aggregate.read_room_map(out)  # the csv the rest of the code reads
    assert sorted(room_of) == ids and sorted(room_of.values()) == [1, 2, 3, 4, 5]
    assert aggregate.check_ward(room_of, True)["source"] == "mimic-iv"


def test_ward_ids_csv_and_refusals(tmp_path, monkeypatch):
    ids = ["a", "b"]
    monkeypatch.setattr(
        aggregate, "DEMO_HOSP", _hosp(tmp_path, ids) / "clif_hospitalization.parquet"
    )
    clif = tmp_path / "clif"
    f = tmp_path / "ids.csv"
    f.write_text("hospitalization_id\nb\na\na\n")
    rooms_df, info = stage_ward.ward_from_ids(clif, f)
    assert rooms_df.height == 2 and info["ward"] == "open-demo" and "ids_digest" in info
    bad = tmp_path / "bad.csv"
    bad.write_text("stay\na\n")
    with pytest.raises(SystemExit, match="no hospitalization_id column"):
        stage_ward.read_ward_ids(bad)
    other = tmp_path / "other.csv"
    other.write_text("hospitalization_id\na\nzz\n")
    monkeypatch.setattr(
        aggregate, "check_ward", lambda *a, **k: {"source": "open-demo"}
    )
    with pytest.raises(SystemExit, match="1 of 2 ward ids are not in"):
        stage_ward.ward_from_ids(clif, other)
    monkeypatch.setattr(
        "sys.argv", ["stage_ward", str(clif), "--real-ward", "--out", "x"]
    )
    with pytest.raises(SystemExit, match="needs --ward-ids"):
        stage_ward.main()


# ---- folders with extra or missing tables ---------------------------------------


def test_table_report_ignores_unknown_tables_and_names_a_missing_required_one(tmp_path):
    d = tmp_path / "clif"
    d.mkdir()
    for t in ("hospitalization", "patient", "adt", "vitals", "ecmo_mcs", "input"):
        pl.DataFrame({HOSP: ["x"]}).write_parquet(d / f"clif_{t}.parquet")
    pl.DataFrame({HOSP: ["x"]}).write_parquet(d / "dashboard_patients.parquet")
    rep = ward_check.table_report(d)
    assert rep["ignored"] == ["ecmo_mcs", "input"]  # ECMO never reaches the tokens
    assert "vitals" in rep["read"] and "labs" in rep["missing_optional"]
    assert rep["on_now_from_clif"] is False
    (d / "clif_adt.parquet").unlink()
    with pytest.raises(SystemExit, match="required CLIF table.*clif_adt.parquet"):
        ward_check.table_report(d)
    with pytest.raises(SystemExit, match="CLIF folder not found"):
        ward_check.table_report(tmp_path / "nope")


def test_ward_check_counts_and_expected_ids(capsys):
    ids = pl.read_parquet(DEMO / "clif_hospitalization.parquet", columns=[HOSP])
    rep = ward_check.check(DEMO)
    assert rep["hospitalizations"] == ids[HOSP].n_unique()
    assert rep["tables"]["missing_optional"] == []
    assert not YEAR_2100_UP.search(json.dumps(rep))


def test_ward_check_refuses_a_ward_file_of_the_wrong_size(tmp_path, capsys):
    f = tmp_path / "ids.parquet"
    pl.read_parquet(DEMO / "clif_hospitalization.parquet", columns=[HOSP]).head(
        7
    ).write_parquet(f)
    assert ward_check.check(DEMO, f, expect_ids=7)["ward_ids"] == 7
    with pytest.raises(SystemExit, match="holds 7 stays, expected 25"):
        ward_check.main([str(DEMO), "--ward-ids", str(f), "--expect-ids", "25"])
    ward_check.main([str(DEMO), "--ward-ids", str(f)])
    out = capsys.readouterr().out
    assert json.loads(out)["ward"] == "open-demo"


# ---- pending-model files ---------------------------------------------------------


def _pending_df(n=4, vaso_on=(0,)):
    df = tl.scores(n)
    on = np.isin(np.arange(n), vaso_on)
    return df.with_columns(
        *(
            pl.lit(float("nan")).alias(c)
            for c in df.columns
            if c.endswith("_rep_score")
        ),
        pl.Series(aggregate.AT_CUT_COL["vasopressor"], on),
        pl.Series(f"{tl.VASO}_past", on),
    )


def test_pending_forecast_keeps_now_real_and_every_count_null():
    fc = aggregate.build_forecast(
        _pending_df(), "pending", beds=4, forecast_state=aggregate.PENDING
    )
    assert fc["forecast_state"] == "pending-model"
    assert fc["life_support"]["now_patients"] == 1
    assert fc["life_support"]["now_by"]["vasopressor"] == 1
    null = {"available": False, "p10": None, "p50": None, "p90": None, "expected": None}
    assert fc["life_support"]["expected_new_patients"] == null
    assert set(fc["resources"]) == set(aggregate.RESOURCES_REP)
    for r in fc["resources"].values():
        assert {k: r[k] for k in null} == null and r["team"]
    for s in aggregate.SUPPORTS:
        assert fc["life_support"]["expected_by"][s] == null
    assert fc["yardstick"] is None and fc["check_first"] == [] and "strain" not in fc
    assert (
        aggregate.build_forecast(tl.scores(4), "m", beds=4)["forecast_state"] == "ready"
    )


def test_pending_rooms_have_null_predictions_and_no_level():
    df = _pending_df()
    room_of = {f"s{i}": i + 1 for i in range(4)}
    cut = dt.datetime(2026, 11, 14, 7, tzinfo=dt.timezone.utc)
    got = rooms.room_entries(df, room_of, {}, cut, "now", pending=True)
    assert len(got) == 4
    for r in got:
        assert set(r["p"].values()) == {None}
        assert r["any_life_support"] is None and r["level"] is None
        assert r["out"] is False
        assert r["skipped"]["death"] and r["skipped"]["icu_departure"]
    assert got[0]["on_now"]["vasopressor"] is True
    assert got[0]["skipped"]["vasopressor"] is False  # on now: not "no data"
    assert got[1]["skipped"]["vasopressor"] is True
    ready = rooms.room_entries(tl.scores(4), room_of, {}, cut, "now")
    assert ready[0]["level"] in ("low", "medium", "high")


def test_pending_scores_reads_every_split_and_leaves_lists_out(tmp_path):
    for split, ids in (("train", ["a", "b"]), ("held_out", ["c"])):
        pl.DataFrame(
            {HOSP: ids, "tokens_past": [[1, 2]] * len(ids), "cut_s": [1.0] * len(ids)}
        ).write_parquet(tmp_path / f"{split}_for_inference.parquet")
    df = aggregate.pending_scores(tmp_path, ["a", "c"])
    assert sorted(df[HOSP]) == ["a", "c"] and "tokens_past" not in df.columns
    score_cols = [c for c in df.columns if c.endswith("_rep_score")]
    assert len(score_cols) == len(aggregate.probe_tokens()) == 6
    assert df.select(score_cols).to_numpy().dtype == float
    assert np.isnan(df.select(score_cols).to_numpy()).all()
    with pytest.raises(SystemExit):
        aggregate.pending_scores(tmp_path / "empty")


# ---- the laptop pipeline on the open demo -----------------------------------------


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    """scripts/run_cohort.py on backend/clif_demo with the 25 selected demo stays"""
    tmp = tmp_path_factory.mktemp("cohort")
    sel, _ = stage_ward.select_rooms(
        stage_ward.score_stays(DEMO, stage_ward.eligible_stays(DEMO))
    )
    ids = tmp / "ids.parquet"
    sel.select(HOSP).write_parquet(ids)
    args = [str(DEMO), "--ward-ids", str(ids), "--work", str(tmp / "work")]
    run_cohort.main([*args, "--out", str(tmp / "out")])
    return tmp, args, sel[HOSP].to_list()


def _docs(folder):
    return (
        json.loads((folder / "rooms.json").read_text()),
        json.loads((folder / "forecast.json").read_text()),
    )


def test_cohort_run_writes_valid_pending_files(demo_run):
    tmp, _, ids = demo_run
    r, f = _docs(tmp / "out")
    assert r["forecast_state"] == f["forecast_state"] == "pending-model"
    assert (
        r["ward"] == f["ward"] == {"source": "open-demo", "label": "Open MIMIC-IV Demo"}
    )
    assert r["on_now_source"] == f["on_now_source"] == "clif"
    assert len(r["rooms"]) + r["dropped"] == 25 and len(r["rooms"]) > 0
    assert f["beds"] == len(r["rooms"])
    on_any = sum(any(v for v in x["on_now"].values()) for x in r["rooms"])
    assert f["life_support"]["now_patients"] == on_any  # the Now side is real
    for k in ("imv", "vasopressor", "crrt"):
        n = sum(bool(x["on_now"][k]) for x in r["rooms"])
        assert f["life_support"]["now_by"][k] == n
    assert f["life_support"]["now_by"]["ecmo"] is None
    assert f["life_support"]["expected_new_patients"]["p50"] is None
    assert all(not v["available"] for v in f["resources"].values())
    assert all(set(x["p"].values()) == {None} for x in r["rooms"])
    assert any(x["age"] for x in r["rooms"]) and any(x["past_12h"] for x in r["rooms"])
    assert all(1 <= e["h"] <= 12 for x in r["rooms"] for e in x["past_12h"])
    text = json.dumps(r) + json.dumps(f)
    assert not any(i in text for i in ids)  # room numbers only


def test_no_source_year_reaches_the_files_and_all_rooms_share_one_day(demo_run):
    tmp, _, _ = demo_run
    r, f = _docs(tmp / "out")
    for doc in (r, f):
        assert run_cohort.source_years(doc) == 0  # MIMIC years are 2100+
    # the open demo's own dates are in that range, so the scan would catch a leak
    adm = pl.read_parquet(DEMO / "clif_hospitalization.parquet")["admission_dttm"]
    assert adm.dt.year().min() >= 2100
    cuts = {x["cut_time"] for x in r["rooms"]} | {f["cut_time"]}
    assert len(cuts) == 1  # one shared cut for every room and the unit
    cut = dt.datetime.fromisoformat(cuts.pop())
    assert (cut.hour, cut.minute) == (7, 0) and cut.utcoffset() is not None
    assert cut <= dt.datetime.fromisoformat(
        f["made_at"]
    )  # the last 07:00, not the next
    assert {x["window"]["start"] for x in r["rooms"]} == {cut.isoformat()}
    assert f["window"]["end"] == (cut + dt.timedelta(hours=24)).isoformat()
    assert f["cut_after_arrival_hours"] == 24 and f["demo_clock_hours"] == 0
    with pytest.raises(SystemExit, match="2100 or later"):
        run_cohort.check_no_source_dates({"x.json": {"t": "2150-01-01T07:00"}}, [])
    with pytest.raises(SystemExit, match="stay id"):
        run_cohort.check_no_source_dates(
            {"x.json": {"t": "stay-12345"}}, ["stay-12345"]
        )


def test_shared_cut_is_the_last_0700_plus_the_demo_clock():
    z = dt.timezone(dt.timedelta(hours=-6))
    at = lambda h, m=0: dt.datetime(2026, 11, 14, h, m, tzinfo=z)  # noqa: E731
    cut = run_cohort.shared_cut(at(20), "America/Chicago", 0)
    assert cut.isoformat() == "2026-11-14T07:00:00-06:00"  # not tomorrow's 07:00
    assert run_cohort.shared_cut(at(6, 59), "America/Chicago", 0).day == 13
    later = run_cohort.shared_cut(at(20), "America/Chicago", 4.5)
    assert later.isoformat() == "2026-11-14T11:30:00-06:00"


def test_each_stay_is_cut_on_its_own_clock_and_nothing_comes_from_after_it(demo_run):
    tmp, _, ids = demo_run
    root = tmp / "work" / "tokenized_output"
    room_of = aggregate.read_room_map(tmp / "work" / "stage_ward.csv")
    df, clif, checks = run_cohort.state_at(root, DEMO, room_of, 0, "US/Eastern", True)
    assert checks["future_tokens"] == 0 and checks["unordered"] == 0
    assert checks["cut_clock_differs"] == 0  # tokenizer cut == CLIF cut, per stay
    assert checks["present"] == df.height == len(clif)
    cuts = run_cohort.clif_now.stay_cuts(DEMO, df[HOSP].to_list(), 0)
    assert len(set(cuts.values())) > 1  # every stay has its own date; never compared
    adt = (
        pl.read_parquet(DEMO / "clif_adt.parquet")
        .filter(pl.col("location_category") == "icu")
        .group_by(HOSP)
        .agg(pl.col("in_dttm").min())
    )
    arrival = dict(zip(adt[HOSP], adt["in_dttm"]))
    assert all(cuts[i] - arrival[i] == dt.timedelta(hours=24) for i in cuts)
    assert all(run_cohort.present_at_cut(DEMO, cuts).values())
    # the model's prompt is the past only: last_valid tokens, all before the cut
    for f in root.glob("*_for_inference.parquet"):
        lab = pl.read_parquet(
            f, columns=["tokens_past", "last_valid", "cut_s", "s_elapsed_past"]
        )
        assert (lab["tokens_past"].list.len() == lab["last_valid"]).all()
        assert (lab["s_elapsed_past"].list.max() < lab["cut_s"]).all()


def test_a_stay_that_left_the_icu_or_died_before_the_cut_is_not_present(tmp_path):
    t0 = dt.datetime(2150, 1, 1, tzinfo=dt.timezone.utc)
    h = lambda x: t0 + dt.timedelta(hours=x)  # noqa: E731
    d = tmp_path / "clif"
    d.mkdir()
    pl.DataFrame(
        {
            HOSP: ["stay", "left", "back", "died", "early"],
            "in_dttm": [h(0), h(0), h(0), h(0), h(30)],
            "out_dttm": [h(90), h(20), h(10), None, h(90)],
            "location_category": ["icu"] * 5,
        }
    ).vstack(
        pl.DataFrame(
            {
                HOSP: ["back"],
                "in_dttm": [h(20)],
                "out_dttm": [h(90)],
                "location_category": ["ICU"],
            }
        )
    ).write_parquet(d / "clif_adt.parquet")
    pl.DataFrame(
        {
            HOSP: ["stay", "left", "back", "died", "early"],
            "discharge_dttm": [h(200), h(200), h(200), h(23), None],
        }
    ).write_parquet(d / "clif_hospitalization.parquet")
    cuts = {i: h(24) for i in ("stay", "left", "back", "died", "early")}
    assert run_cohort.present_at_cut(d, cuts) == {
        "stay": True,
        "left": False,  # on a ward at the cut
        "back": True,  # in a later ICU stay at the cut
        "died": False,  # discharged (dead) an hour before the cut
        "early": False,  # the cut is before this ICU arrival
    }
    assert run_cohort.present_at_cut(d, {}) == {}


def test_demo_clock_moves_every_stay_and_drops_ended_ones(demo_run, capsys):
    tmp, args, _ = demo_run
    capsys.readouterr()
    run_cohort.main([*args, "--reuse-tokens", "--cut-table", "0,240"])
    out = capsys.readouterr().out
    assert not YEAR_2100_UP.search(out)
    rows = [json.loads(x) for x in out.splitlines() if '"rooms_present"' in x]
    assert [x["demo_clock_hours"] for x in rows] == [0.0, 240.0]
    for x in rows:
        assert x["rooms_present"] + x["dropped"] == 25
        assert x["any_life_support"] <= x["rooms_present"]
    assert rows[1]["rooms_present"] < rows[0]["rooms_present"]  # stays ended by day 10
    # a later run writes fewer rooms and says how many dropped
    run_cohort.main(
        [
            *args,
            "--reuse-tokens",
            "--out",
            str(tmp / "late"),
            "--demo-clock-hours",
            "240",
        ]
    )
    r, f = _docs(tmp / "late")
    assert (
        len(r["rooms"]) == rows[1]["rooms_present"]
        and r["dropped"] == rows[1]["dropped"]
    )
    assert f["demo_clock_hours"] == 240 and f["beds"] == len(r["rooms"])
    assert run_cohort.source_years(r) == run_cohort.source_years(f) == 0
    # --cut-after-arrival-hours moves the stays, not the shared 07:00
    run_cohort.main(
        [
            *args,
            "--reuse-tokens",
            "--out",
            str(tmp / "day3"),
            "--cut-after-arrival-hours",
            "72",
        ]
    )
    r3, f3 = _docs(tmp / "day3")
    assert f3["cut_after_arrival_hours"] == 72 and f3["demo_clock_hours"] == 0
    assert dt.datetime.fromisoformat(f3["cut_time"]).hour == 7
    assert len(r3["rooms"]) + r3["dropped"] == 25


def test_with_model_and_probes_the_predictions_are_filled(demo_run, monkeypatch):
    """the code path with weights: the extractor is replaced by synthetic features
    (no GPU here); the saved probes are really applied"""
    tmp, args, _ = demo_run
    box = tmp / "model"
    box.mkdir()
    home = tl._model_dir(box)
    _, probes = tl._fit_probes(box, home)

    def fake_extract(root, model_home, config=None, stay_ids=None):
        rng = np.random.default_rng(1)
        for f in pathlib.Path(root).glob("*_for_inference.parquet"):
            lab = pl.read_parquet(f, columns=[HOSP, "last_valid", "cut_s"])
            x = rng.normal(size=(lab.height, 4)).astype(np.float32)
            split = f.name.removesuffix("_for_inference.parquet")
            lab.with_columns(features=pl.Series(list(x))).write_parquet(
                pathlib.Path(root) / f"features-{split}-{tl.MODEL}.parquet"
            )

    from icutwin.scoring import extractor

    monkeypatch.setattr(extractor, "extract", fake_extract)
    out = tmp / "scored"
    run_cohort.main(
        [
            *args,
            "--reuse-tokens",
            "--out",
            str(out),
            "--model",
            str(home),
            "--probes",
            str(probes),
        ]
    )
    r, f = _docs(out)
    assert r["forecast_state"] == f["forecast_state"] == "ready"
    assert f["model"] == tl.MODEL
    assert (
        f["resources"]["death"]["available"]
        and f["resources"]["death"]["p50"] is not None
    )
    assert f["life_support"]["expected_new_patients"]["p50"] is not None
    free = [x for x in r["rooms"] if not x["on_now"]["vasopressor"]]
    # main's task rule: a pressor started (and stopped) before the cut gets no p
    ps = [x["p"]["vasopressor"] for x in free]
    assert any(v is not None for v in ps)
    assert all(v is None or 0 <= v <= 1 for v in ps)
    assert all(x["level"] in ("low", "medium", "high") for x in r["rooms"])
    assert all(x["p"]["imv"] is None for x in r["rooms"] if x["on_now"]["imv"])
    assert run_cohort.source_years(r) == run_cohort.source_years(f) == 0
    # weights or probes missing: still valid files, pending
    empty = tmp / "no-weights"
    empty.mkdir()
    run_cohort.main(
        [
            *args,
            "--reuse-tokens",
            "--out",
            str(tmp / "p2"),
            "--model",
            str(empty),
            "--probes",
            str(probes),
        ]
    )
    assert _docs(tmp / "p2")[1]["forecast_state"] == "pending-model"


def test_a_real_ward_is_refused_without_the_flag(tmp_path):
    ids = tmp_path / "ids.csv"
    ids.write_text("hospitalization_id\nnot-a-demo-stay\n")
    with pytest.raises(SystemExit, match="Re-run with --real-ward"):
        run_cohort.main(
            [str(DEMO), "--ward-ids", str(ids), "--work", str(tmp_path / "w")]
        )
    assert not (tmp_path / "w" / "tokenized_output").exists()


# ---- the board: loopback, and the files as written --------------------------------


def test_board_host_defaults_to_all_interfaces_and_can_bind_loopback(demo_run):
    tmp, _, _ = demo_run
    fc = tmp / "out" / "forecast.json"
    assert board.parse_args(["--forecast", str(fc)]).host == "0.0.0.0"
    a = board.parse_args(["--forecast", str(fc), "--host", "127.0.0.1", "--port", "0"])
    srv = board.serve(a)
    assert srv.server_address[0] == "127.0.0.1"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        with urllib.request.urlopen(base + "/api/forecast") as resp:
            f = json.load(resp)
        with urllib.request.urlopen(base + "/api/rooms") as resp:
            r = json.load(resp)
    finally:
        srv.shutdown()
        srv.server_close()
    assert (
        f["forecast_state"] == r["forecast_state"] == "pending-model"
    )  # passed through
    assert len(r["rooms"]) + r["dropped"] == 25

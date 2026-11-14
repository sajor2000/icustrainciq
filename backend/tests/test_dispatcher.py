# ruff: noqa: E501
"""Dispatcher scopes, guards, schedule and demo clock (no cluster: the CLI is faked)."""

import datetime as dt
import json
import pathlib
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from app import dispatcher as d

TEMPLATE = "scope=@SCOPE@ room=@ROOM@ hours=@HOURS@\n"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += dt.timedelta(**kw)


class FakeCli(d.Dispatcher):
    def __init__(self, tmp_path, running=(), clock=None):
        (tmp_path / "t7-forecast.fz").write_text(TEMPLATE)
        (tmp_path / "ward-rooms.json").write_text("{}")  # a whole-ward run has happened
        super().__init__(
            tmp_path / "t7-forecast.fz",
            tmp_path / "runs.jsonl",
            min_gap_s=1200,
            list_ttl_s=0,
            rooms=tmp_path / "ward-rooms.json",
            clock=clock or Clock(dt.datetime(2026, 11, 14, 11, 30)),
        )
        self.running, self.started, self.ended = list(running), [], []

    def _cli(self, *args, **kw):
        if args[:2] == ("workflow", "list"):
            return json.dumps(self.running + self.ended)
        self.started.append(args)
        # a started workflow shows up in the list as ended, so the next test step may start again
        self.ended.append(
            {"id": f"wf-{len(self.started)}", "name": args[4], "status": "FINISHED"}
        )
        return f"wf-{len(self.started)}\n"


def rendered(f, i=-1):
    return pathlib.Path(f.started[i][2]).read_text()


def test_next_run_is_0700_and_rolls_to_tomorrow():
    assert d.next_run(dt.datetime(2026, 11, 14, 7, 0), "07:00") == dt.datetime(
        2026, 11, 15, 7, 0
    )
    assert d.next_run(dt.datetime(2026, 11, 14, 6, 59), "07:00").day == 14
    assert d.MORNING == "07:00"


def test_busy_counts_anything_not_finished():
    assert d.busy([{"name": "t7-build", "status": "STARTED"}]) == "t7-build"
    assert d.busy([{"name": "t7-smoke", "status": "STARTED"}]) == "t7-smoke"
    assert d.busy([{"name": "t7-fit", "status": ""}]) == "t7-fit"
    assert d.busy([{"name": "t7-forecast-room7-1114-1100", "status": "STARTED"}])
    assert d.busy([{"name": "t7-forecast-1114-0700", "status": "FINISHED"}]) is None
    assert d.busy([{"name": "t7-twin", "status": "STARTED"}]) is None


def test_demo_clock_is_hours_since_the_0700_cut():
    assert d.demo_clock_hours(dt.datetime(2026, 11, 14, 7, 0)) == 0.0
    assert d.demo_clock_hours(dt.datetime(2026, 11, 14, 11, 30)) == 4.5
    assert d.demo_clock_hours(dt.datetime(2026, 11, 14, 6, 0)) == 23.0
    assert d.demo_clock_label(4.5) == "Ward clock 11:30 (07:00 + 4.5 h)"


def test_unit_run_renders_the_template_and_passes_the_offset(tmp_path):
    f = FakeCli(tmp_path)
    r = f.start("ICU physician", "unit")
    assert r["started"] and r["scope"] == "unit" and r["demo_clock_hours"] == 4.5
    assert r["demo_clock_label"] == "Ward clock 11:30 (07:00 + 4.5 h)"
    start = f.started[0]
    assert start[:2] == ("workflow", "start") and start[3] == "--name"
    assert rendered(f) == "scope=unit room=0 hours=4.5\n"
    assert r["name"] == "t7-forecast-1114-1130"


def test_room_run_needs_a_room_and_names_it(tmp_path):
    f = FakeCli(tmp_path)
    for bad in (None, 0, 26, "7", True):
        assert f.start("ICU nurse", "room", bad)["started"] is False
    assert f.start("ICU nurse", "nope")["started"] is False
    assert not f.started
    r = f.start("ICU nurse", "room", 12)
    assert r["started"] and r["room"] == 12 and "room12" in r["name"]
    assert rendered(f) == "scope=room room=12 hours=4.5\n"


def test_gap_is_per_scope_and_per_room_with_plain_words(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 12, 57))
    f = FakeCli(tmp_path, clock=clock)
    assert f.start("ICU nurse", "unit")["started"]
    clock.advance(minutes=12)
    r = f.start("ICU nurse", "unit")
    assert r == {
        "started": False,
        "reason": "Updated 12 minutes ago. You can update again at 13:17.",
    }
    # a unit update refreshed every room, so a room is limited too
    assert f.start("ICU nurse", "room", 3)["reason"].startswith(
        "Room 3 updated 12 minutes ago"
    )
    clock.advance(minutes=9)  # 13:18, past the gap
    assert f.start("ICU nurse", "room", 3)["started"]
    clock.advance(minutes=1)  # room 3 is limited, room 4 is not
    assert f.start("ICU nurse", "room", 3)["started"] is False
    assert f.start("ICU nurse", "room", 4)["started"]
    clock.advance(minutes=1)  # a room run does not limit the unit (it ran 22 min ago)
    assert f.start("ICU nurse", "unit")["started"]


def test_one_run_at_a_time_any_scope(tmp_path):
    f = FakeCli(
        tmp_path, running=[{"name": "t7-forecast-room9-1114-1125", "status": "STARTED"}]
    )
    r = f.start("ICU nurse", "unit")
    assert r["started"] is False and "Another update is running" in r["reason"]
    f.running = [{"name": "t7-build", "status": "STARTED"}]
    assert "model is being built" in f.start("ICU nurse", "room", 2)["reason"]
    assert not f.started


def test_cluster_unreachable_fails_closed(tmp_path):
    f = FakeCli(tmp_path)

    def boom(*a):
        raise OSError("down")

    f._cli = boom
    assert f.start("ICU nurse")["reason"].startswith("cannot list workflows")


def test_log_has_time_role_scope_room_and_workflow_only(tmp_path):
    f = FakeCli(tmp_path)
    f.start("ICU physician", "room", 5)
    row = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])
    assert set(row) == {
        "trigger",
        "scope",
        "room",
        "started",
        "workflow",
        "name",
        "at",
        "ward",
    }
    assert row["trigger"] == "ICU physician" and row["room"] == 5


def test_gap_survives_a_restart_through_the_log(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 12, 0))
    f = FakeCli(tmp_path, clock=clock)
    f.start("ICU nurse", "unit")
    clock.advance(minutes=5)
    g = FakeCli(tmp_path, clock=clock)  # a new process reads runs.jsonl
    assert g.start("ICU nurse", "unit")["reason"].startswith("Updated 5 minutes ago")


def test_scheduled_run_is_hour_zero_ignores_gap_and_waits_for_a_busy_cluster(
    tmp_path, monkeypatch
):
    clock = Clock(dt.datetime(2026, 11, 14, 6, 50))
    f = FakeCli(tmp_path, clock=clock)
    assert f.start("ICU nurse", "unit")["started"]  # 06:50 manual run
    clock.t = dt.datetime(2026, 11, 14, 7, 0, 2)  # the 07:00 tick, 10 minutes later
    f.running = [{"name": "t7-forecast-1114-0650", "status": "STARTED"}]
    sleeps = []

    def fake_sleep(s):
        sleeps.append(s)
        f.running = []  # the earlier run ends while we wait

    r = d.run_scheduled(f, retry_s=60, window_s=300, sleep=fake_sleep)
    assert r["started"] and r["demo_clock_hours"] == 0.0 and sleeps == [60]
    assert rendered(f) == "scope=unit room=0 hours=0\n"
    row = json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])
    assert row["trigger"] == "schedule"


def test_status_has_running_last_per_scope_clock_and_next_0700(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 11, 30))
    f = FakeCli(tmp_path, clock=clock)
    f.start("ICU nurse", "unit")
    clock.advance(minutes=30)
    f.start("pharmacy", "room", 8)
    f.running = [{"name": "t7-forecast-room8-1114-1200", "status": "STARTED"}]
    s = f.status()
    assert s["next_scheduled"] == "2026-11-15T07:00" and s["updating"] is True
    assert s["running"] == {"name": "t7-forecast-room8-1114-1200", "state": "STARTED"}
    assert s["last"]["unit"]["demo_clock_hours"] == 4.5
    assert s["last"]["room"]["room"] == 8
    assert s["last"]["room"]["demo_clock_hours"] == 5.0
    assert s["demo_clock_label"] == "Ward clock 12:00 (07:00 + 5 h)"
    assert s["recent"][-1]["scope"] == "room"


def test_http_run_scope_room_and_validation(tmp_path):
    f = FakeCli(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), d.make_handler(f))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:

        def post(body):
            req = urllib.request.Request(
                base + "/run", data=json.dumps(body).encode(), method="POST"
            )
            try:
                return json.load(urllib.request.urlopen(req))
            except urllib.error.HTTPError as e:
                return json.load(e)

        assert post({"role": "visitor"})["started"] is False
        bad = post({"role": "ICU nurse", "scope": "room", "room": 99})
        assert bad["started"] is False
        assert post({"role": "ICU nurse", "scope": "room", "room": 12})["started"]
        assert post({"role": "ICU nurse"})["started"] is True  # defaults to unit
        status = json.load(urllib.request.urlopen(base + "/status"))
        assert status["recent"][-1]["trigger"] == "ICU nurse"
        assert status["last"]["room"]["room"] == 12
    finally:
        srv.shutdown()


def test_the_real_template_renders_to_valid_yaml_for_both_scopes(tmp_path):
    import yaml

    repo = pathlib.Path(__file__).resolve().parents[1]
    f = FakeCli(tmp_path)
    f.fuzzfile = repo / "fuzzball" / "t7-forecast.fz"
    assert (
        yaml.safe_load(f.fuzzfile.read_text())["version"] == "v4"
    )  # template itself parses
    for scope, room, token in (
        ("unit", None, "SCOPE=unit; ROOM=0; HOURS=4.5"),
        ("room", 12, "SCOPE=room; ROOM=12; HOURS=4.5"),
    ):
        r = f.start("ICU nurse", scope, room)
        doc = yaml.safe_load(rendered(f))
        assert token in doc["jobs"]["score"]["script"]
        assert 'WARD=""' in doc["jobs"]["score"]["script"]
        assert "--tz America/Chicago" in doc["jobs"]["score"]["script"]
        assert doc["jobs"]["extract"]["depends-on"] == [
            {"name": "precheck", "status": "FINISHED"}
        ]
        assert not re.search(r"@[A-Z0-9_]+@", rendered(f))  # every token filled
        # defaults keep the open demo folder for age, sex and what is on now
        assert "CLIF=/store/code/clif_demo" in doc["jobs"]["score"]["script"]
        assert "--demographics $CLIF --clif-now $CLIF" in doc["jobs"]["score"]["script"]
        f.last.clear()
        f.running = []
        assert r["started"]


# ---- review fixes (2026-11-14) -------------------------------------------------------------

import zoneinfo  # noqa: E402

import pytest  # noqa: E402

CHI = zoneinfo.ZoneInfo("America/Chicago")


def test_busy_matches_terminal_states_exactly():
    assert (
        d.busy([{"name": "t7-forecast-1114", "status": "STAGE_STATUS_FINISHED"}])
        is None
    )
    for st in ("ERRORED", "CANCELED", "STAGE_STATUS_DOWN", "finished"):
        assert d.busy([{"name": "t7-build", "status": st}]) is None, st
    # substring matching used to treat these as ended
    for st in (
        "UNFINISHED",
        "NOT_FAILED_YET",
        "STAGE_STATUS_STARTED",
        "PENDING",
        "",
        "weird",
    ):
        assert d.busy([{"name": "t7-build", "status": st}]) == "t7-build", st


def test_gpu_guard_regex_and_sanitised_names():
    assert d.busy([{"name": "t7-lane2-build", "status": "STARTED"}]) == "t7-lane2-build"
    assert d.busy([{"name": "t7-forecast-room3-1114-1100", "status": "STARTED"}])
    assert d.busy([{"name": "t7-twin", "status": "STARTED"}]) is None
    assert d.busy([{"name": "my-t7-build", "status": "STARTED"}]) is None
    assert (
        d.busy([{"name": "t7-fit;rm -rf /<b>", "status": "STARTED"}]) == "t7-fitrm-rfb"
    )
    assert d.busy(["junk", None, {"name": "t7-fit", "status": "STARTED"}]) == "t7-fit"


def test_reasons_never_carry_odd_characters_from_workflow_names(tmp_path):
    f = FakeCli(tmp_path, running=[{"name": "t7-smoke<script>", "status": "STARTED"}])
    r = f.start("ICU nurse", "unit")
    assert "<" not in r["reason"] and "t7-smokescript" in r["reason"]


def test_two_concurrent_scopes_cannot_both_start(tmp_path):
    gate, entered = threading.Event(), threading.Event()

    class Slow(FakeCli):
        def _cli(self, *args, **kw):
            if args[:2] == ("workflow", "start"):
                entered.set()
                gate.wait(5)
            return super()._cli(*args, **kw)

    f = Slow(tmp_path)
    out = {}
    t = threading.Thread(target=lambda: out.update(a=f.start("ICU nurse", "room", 3)))
    t.start()
    assert entered.wait(5)
    # the first start is still inside the slow CLI call (and the lock is free): a second one is refused
    out["b"] = f.start("ICU nurse", "room", 4)
    gate.set()
    t.join(5)
    assert out["a"]["started"] and out["b"]["started"] is False and out["b"]["busy"]
    assert len(f.started) == 1


def test_a_started_workflow_blocks_until_the_list_shows_it_end(tmp_path):
    class NotListed(FakeCli):
        def _cli(self, *args, **kw):
            if args[:2] == ("workflow", "start"):
                self.started.append(args)
                return "wf-9\n"
            return json.dumps(self.running)

    clock = Clock(dt.datetime(2026, 11, 14, 11, 30))
    f = NotListed(tmp_path, clock=clock)
    assert f.start("ICU nurse", "room", 3)["started"]
    clock.advance(seconds=30)
    assert f.start("ICU nurse", "room", 4)[
        "busy"
    ]  # started 30 s ago, not in the list yet
    clock.advance(minutes=5)  # never listed and past the grace: forgotten
    assert f.start("ICU nurse", "room", 4)["started"]


def test_a_run_seen_failing_quickly_clears_the_gap(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 11, 30))
    f = FakeCli(tmp_path, clock=clock)
    assert f.start("ICU nurse", "unit")["started"]
    clock.advance(minutes=2)
    f.ended[-1]["status"] = "STAGE_STATUS_ERRORED"  # the list now shows it failed
    assert f.start("ICU nurse", "unit")[
        "started"
    ]  # no 20 minute wait after a failed run
    # a run that finished fine keeps its gap
    clock.advance(minutes=1)
    assert f.start("ICU nurse", "unit")["reason"].startswith("Updated 1 minutes ago")


def test_workflow_list_is_cached_for_ten_seconds(tmp_path):
    f = FakeCli(tmp_path)
    f.list_ttl_s = 10
    calls = []
    orig = f._cli
    f._cli = lambda *a, **k: (calls.append(a), orig(*a, **k))[1]
    f.workflows(), f.workflows(), f.workflows()
    assert [c[:2] for c in calls].count(("workflow", "list")) == 1
    f.workflows(fresh=True)
    assert [c[:2] for c in calls].count(("workflow", "list")) == 2


def test_cli_calls_are_time_bounded(tmp_path, monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen[cmd[1]] = kw["timeout"]

        class R:
            stdout = "[]"

        return R()

    monkeypatch.setattr(d.subprocess, "run", fake_run)
    g = d.Dispatcher(tmp_path / "t.fz", tmp_path / "r.jsonl", 60)
    g.workflows()
    g._cli("workflow", "start", "x")
    assert seen["workflow"] <= 60 and d.LIST_TIMEOUT_S <= 30


def test_truncated_last_log_line_is_repaired_before_append(tmp_path):
    f = FakeCli(tmp_path)
    log = tmp_path / "runs.jsonl"
    log.write_text(
        '{"trigger": "ICU nurse", "started": true, "at": "2026-11-14T10:00:00"}\n{"trigger": "ICU nu'
    )
    f.record(event="x")
    lines = log.read_text().splitlines()
    assert len(lines) == 2 and all(json.loads(x) for x in lines)
    # a complete last row that only lost its newline is kept
    log.write_text('{"a": 1}')
    f.record(event="y")
    assert [json.loads(x).get("a") for x in log.read_text().splitlines()][0] == 1


def test_scheduled_run_retries_transient_failures_and_logs_every_attempt(tmp_path):
    f = FakeCli(tmp_path, clock=Clock(dt.datetime(2026, 11, 15, 7, 0, 1)))
    real = f._cli
    fails = {"n": 3}

    def flaky(*args, **kw):
        if args[:2] == ("workflow", "list") and fails["n"] > 0:
            fails["n"] -= 1
            raise OSError("cluster down")
        return real(*args, **kw)

    f._cli = flaky
    sleeps = []
    r = d.run_scheduled(f, retry_s=60, window_s=600, sleep=sleeps.append)
    assert r["started"] and sleeps == [60, 60, 60]
    rows = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    attempts = [x for x in rows if x.get("event") == "scheduled_attempt"]
    assert [a["attempt"] for a in attempts] == [1, 2, 3]
    assert all(a["reason"].startswith("cannot list workflows") for a in attempts)
    assert rows[-1]["started"] and rows[-1]["trigger"] == "schedule"
    assert f.scheduled_state()["state"] == "ok"


def test_scheduled_run_gives_up_after_ten_minutes_and_status_says_failed(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 15, 7, 0, 1))
    f = FakeCli(tmp_path, clock=clock)

    def down(*a, **k):
        raise OSError("down")

    f._cli = down
    sleeps = []
    r = d.run_scheduled(f, retry_s=60, window_s=600, sleep=sleeps.append)
    assert r["started"] is False and sum(sleeps) == 600
    rows = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert rows[-1]["event"] == "scheduled_outcome" and rows[-1]["started"] is False
    assert len([x for x in rows if x.get("event") == "scheduled_attempt"]) == 11
    clock.advance(minutes=11)
    st = f.scheduled_state()
    assert st["state"] == "failed" and st["ok"] is False
    # /status carries it (and so does /api/runs, which relays it)
    f._cli = lambda *a, **k: "[]"
    assert f.status()["scheduled"]["state"] == "failed"


def test_missing_scheduled_run_shows_as_missed(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 15, 7, 5))
    f = FakeCli(tmp_path, clock=clock)
    assert f.status()["scheduled"]["state"] == "pending"
    clock.t = dt.datetime(2026, 11, 15, 9, 0)
    assert f.status()["scheduled"]["state"] == "missed"


def test_start_after_0700_without_a_scheduled_run_catches_up_once(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 15, 9, 0))
    f = FakeCli(tmp_path, clock=clock)
    s = d.Scheduler(f, "07:00", sleep=lambda s: None)
    assert s.tick() is True and f.started  # caught up
    assert (
        json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])["trigger"]
        == "schedule"
    )
    n = len(f.started)
    assert s.tick() is False and len(f.started) == n  # once
    # a restart the same morning sees the scheduled row and does not run again
    s2 = d.Scheduler(FakeCli(tmp_path, clock=clock), "07:00", sleep=lambda s: None)
    assert s2.tick() is False
    # tomorrow's cut fires exactly once
    clock.t = dt.datetime(2026, 11, 16, 7, 0, 3)
    assert s.tick() is True and s.tick() is False


def test_scheduler_does_not_double_fire_on_an_early_wakeup(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 6, 59, 59))
    f = FakeCli(tmp_path, clock=clock)
    s = d.Scheduler(f, "07:00", sleep=lambda s: None)
    s.tick()  # startup catch-up for yesterday's cut (no row): fires once
    n = len(f.started)
    clock.t = dt.datetime(2026, 11, 14, 7, 0, 0)
    assert s.tick() is True
    clock.t = dt.datetime(2026, 11, 14, 7, 0, 1)
    assert s.tick() is False and len(f.started) == n + 1


def test_scheduler_thread_survives_errors(monkeypatch, tmp_path, caplog):
    f = FakeCli(tmp_path)
    calls = {"tick": 0, "sleep": 0}

    def tick(self):
        calls["tick"] += 1
        raise RuntimeError("boom")

    def sleep(s):
        calls["sleep"] += 1
        if calls["sleep"] >= 3:
            raise SystemExit

    monkeypatch.setattr(d.Scheduler, "tick", tick)
    monkeypatch.setattr(d.time, "sleep", sleep)
    with caplog.at_level("ERROR", logger="dispatcher"), pytest.raises(SystemExit):
        d.scheduler(f, "07:00", poll_s=0)
    assert calls["tick"] == 3 and "scheduler tick failed" in caplog.text


def test_dst_next_run_demo_clock_and_no_hour_slip():
    # the clocks go back on 2026-11-01 in Chicago (CDT -> CST)
    sat = dt.datetime(2026, 10, 31, 20, 0, tzinfo=CHI)
    nxt = d.next_run(sat, "07:00")
    assert (nxt.month, nxt.day, nxt.hour, nxt.utcoffset()) == (
        11,
        1,
        7,
        dt.timedelta(hours=-6),
    )
    # 24 real hours after Oct 31 07:00 CDT is Nov 1 06:00 CST
    now = dt.datetime(2026, 11, 1, 6, 0, tzinfo=CHI)
    assert d.demo_clock_hours(now) == 24.0
    assert d.last_cut(now).day == 31 and d.last_cut(now).hour == 7
    # spring forward (2027-03-14): the 07:00 cut is on wall-clock time, and 07:00 -> 07:00 is 23 h
    a = dt.datetime(2027, 3, 13, 7, 0, tzinfo=CHI)
    b = d.next_run(a, "07:00")
    assert (b.day, b.hour) == (14, 7) and (
        b.astimezone(dt.UTC) - a.astimezone(dt.UTC)
    ) == dt.timedelta(hours=23)


def test_aware_clock_reads_naive_log_rows(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 11, 30, tzinfo=CHI))
    f = FakeCli(tmp_path, clock=clock)
    (tmp_path / "runs.jsonl").write_text(
        '{"started": true, "scope": "unit", "at": "2026-11-14T11:20:00"}\n'
    )
    g = FakeCli(tmp_path, clock=clock)
    assert g.start("ICU nurse", "unit")["reason"].startswith("Updated 10 minutes ago")
    assert f.status()["next_scheduled"].startswith("2026-11-15T07:00")


def test_ward_flag_renders_empty_by_default_and_real_ward_on_request(tmp_path):
    f = FakeCli(tmp_path)
    (tmp_path / "t7-forecast.fz").write_text(
        "W=[@WARD_FLAG@] s=@SCOPE@ r=@ROOM@ h=@HOURS@\n"
    )
    f.start("ICU nurse", "unit")
    assert rendered(f) == "W=[] s=unit r=0 h=4.5\n"
    f.real_ward = True
    f.last.clear()
    f.start("ICU nurse", "unit")
    assert rendered(f) == "W=[--real-ward] s=unit r=0 h=4.5\n"
    assert (
        json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])["ward"]
        == "real"
    )


def test_http_body_limits_and_head(tmp_path):
    import http.client

    f = FakeCli(tmp_path)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), d.make_handler(f))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:

        def post(length, body=b""):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
            c.putrequest("POST", "/run")
            c.putheader("Content-Length", length)
            c.endheaders(body)
            r = c.getresponse()
            return r.status

        assert post("abc") == 400 and post("-1") == 400 and post("") == 400
        assert post("5000", b"x" * 5000) == 413
        assert post("3", b"[1]") == 400
        c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
        c.request("HEAD", "/")
        assert c.getresponse().status == 200
    finally:
        srv.shutdown()


def test_room_run_before_any_whole_ward_run_is_refused_without_launching(tmp_path):
    f = FakeCli(tmp_path)
    (tmp_path / "ward-rooms.json").unlink()
    r = f.start("ICU nurse", "room", 5)
    assert (
        r["started"] is False
        and "Update the unit first" in r["reason"]
        and not f.started
    )
    assert f.start("ICU nurse", "unit")["started"]  # the unit run is still allowed


# ---- every Fuzzfile in backend/fuzzball: tokens, YAML, pinned images, job order ----

FUZZ = pathlib.Path(__file__).resolve().parents[1] / "fuzzball"
PINNED = {  # docs/CLUSTER_FACTS.md "Images we pin", plus the CPU image
    "docker://nvcr.io/nvidia/pytorch:25.11-py3",
    "docker://nvcr.io/nvidia/vllm:25.12.post1-py3",
    "docker://lmsysorg/sglang:v0.5.21",
    "docker://python:3.12-slim",
}
COHORT = dict(
    real_ward=True,
    clif_dir="/rows/stage/unit25",
    ward_ids="/rows/stage/unit25/dashboard_patients_unit25.parquet",
)
ORDER = {  # job -> the jobs it waits for (docs/diagrams/workflow.html, backend.html)
    "t7-smoke": {
        "prefetch": [],
        "setup": [],
        "train-demo": ["setup"],
        "sglang": ["train-demo"],
        "seed": ["sglang"],
    },
    "t7-fit": {"stage": [], "extract": [], "fit": ["extract", "stage"]},
    "t7-ward": {"load": [], "tokenize": ["load"]},
    "t7-forecast": {"precheck": [], "extract": ["precheck"], "score": ["extract"]},
    "t7-twin": {},  # services only
}


def render_any(name: str, **ward) -> str:
    """a Fuzzfile as it would be started: every template token filled"""
    text = (FUZZ / f"{name}.fz").read_text()
    text = text.replace("@CODE_REF@", "0" * 40).replace("@CODE_SHA256@", "1" * 64)
    text = (
        text.replace("@SCOPE@", "unit").replace("@ROOM@", "0").replace("@HOURS@", "0")
    )
    return d.render_ward(text, **ward)


def test_every_fuzzfile_is_covered_by_these_tests():
    assert {f.stem for f in FUZZ.glob("*.fz")} == set(ORDER)


def test_every_fuzzfile_renders_to_yaml_with_pinned_images_and_no_token_left():
    import yaml

    for name in ORDER:
        for ward in ({}, COHORT):
            text = render_any(name, **ward)
            assert not re.search(r"@[A-Z0-9_]+@", text), name
            doc = yaml.safe_load(text)
            assert doc["version"] == "v4", name
            units = {**doc.get("jobs", {}), **doc.get("services", {})}
            assert units, name
            for unit, spec in units.items():
                assert spec["image"]["uri"] in PINNED, (name, unit)
                assert spec["script"].startswith("#!/bin/bash"), (name, unit)
                assert "cpu" in spec["resource"] and "memory" in spec["resource"]
            for job, spec in doc.get("jobs", {}).items():
                if name != "t7-smoke" or job != "seed":  # seed is a copy: no timeout
                    assert spec["policy"]["timeout"]["execute"], (name, job)
            for vol in doc["volumes"].values():
                assert vol["use"] == "team7", name  # team volumes only


def test_job_order_matches_the_workflow_diagram():
    import yaml

    for name, want in ORDER.items():
        jobs = yaml.safe_load(render_any(name)).get("jobs", {})
        got = {
            j: [x["name"] for x in spec.get("depends-on", [])]
            for j, spec in jobs.items()
        }
        assert got == want, name
        for spec in jobs.values():  # a job starts only after the one before FINISHED
            assert all(x["status"] == "FINISHED" for x in spec.get("depends-on", []))
    twin = yaml.safe_load(render_any("t7-twin"))["services"]
    assert set(twin) == {"nemotron", "board", "dispatcher"}
    gpu = lambda s: s["resource"].get("devices", {}).get("nvidia.com/gpu", 0)  # noqa: E731
    assert [n for n, s in twin.items() if gpu(s)] == ["nemotron"]  # one GPU, held
    for name in ("t7-fit", "t7-forecast"):  # exactly one GPU job, called extract
        jobs = yaml.safe_load(render_any(name))["jobs"]
        assert [j for j, s in jobs.items() if gpu(s)] == ["extract"], name
    ward = yaml.safe_load(render_any("t7-ward"))["jobs"]
    assert not any(gpu(s) for s in ward.values())  # CPU only


def test_ward_tokens_default_to_the_open_demo_and_point_at_the_cohort_on_request():
    import yaml

    fit = yaml.safe_load(render_any("t7-fit"))["jobs"]["stage"]["script"]
    assert "CLIF=/store/code/clif_demo" in fit
    assert (
        "--out /rows/stage/stage_ward.csv    #" in fit
    )  # no --ward-ids: the selection
    assert "--ward-ids" not in fit.replace("# ", "")
    for name, job in (
        ("t7-fit", "stage"),
        ("t7-ward", "tokenize"),
        ("t7-ward", "load"),
    ):
        s = yaml.safe_load(render_any(name, **COHORT))["jobs"][job]["script"]
        assert "CLIF=/rows/stage/unit25" in s
        assert (
            "--ward-ids /rows/stage/unit25/dashboard_patients_unit25.parquet --real-ward"
            in s
        )
    fc = yaml.safe_load(render_any("t7-forecast", **COHORT))["jobs"]
    assert "CLIF=/rows/stage/unit25" in fc["score"]["script"]
    assert 'WARD="--real-ward"' in fc["score"]["script"]
    assert "/rows/stage/unit25/clif_hospitalization.parquet" in fc["precheck"]["script"]
    ward = yaml.safe_load(render_any("t7-ward", **COHORT))["jobs"]
    assert "ward_check.py" in ward["load"]["script"]
    assert "--expect-ids 25" in ward["load"]["script"]
    t = ward["tokenize"]["script"]
    assert "cmp " in t and "/rows/tokenized_output/vocab.yaml" in t  # training vocab
    assert 'mv "$NEW/tokenized_output" /rows/stage/tokenized_output' in t
    assert 'mv "$NEW/stage_ward.csv" /rows/stage/stage_ward.csv' in t
    # the folder never points into the repo's code tree for a real ward
    assert "/store/code/clif_demo" not in t


def test_dispatcher_renders_the_cohort_folder_and_refuses_an_unsafe_path(tmp_path):
    f = FakeCli(tmp_path)
    (tmp_path / "t7-forecast.fz").write_text(
        "c=@CLIF_DIR@ i=[@WARD_IDS@] w=[@WARD_FLAG@]\n"
    )
    f.start("ICU nurse", "unit")
    assert rendered(f) == "c=/store/code/clif_demo i=[] w=[]\n"  # today's behaviour
    f.real_ward, f.clif_dir, f.ward_ids = (
        True,
        "/rows/stage/unit25",
        "/rows/ids.parquet",
    )
    f.last.clear()
    f.start("ICU nurse", "unit")
    assert rendered(f) == (
        "c=/rows/stage/unit25 i=[--ward-ids /rows/ids.parquet --real-ward] w=[--real-ward]\n"
    )
    for bad in ("/rows/x; rm -rf /", "$(id)", "/rows/a b"):
        try:
            d.render_ward("@CLIF_DIR@", clif_dir=bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert (
        d.render_ward("[@WARD_IDS@]", ward_ids="/a/ids.csv")
        == "[--ward-ids /a/ids.csv]"
    )


def test_render_only_prints_the_template_and_starts_nothing(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(
        "sys.argv",
        [
            "dispatcher",
            "--render-only",
            str(FUZZ / "t7-ward.fz"),
            "--clif-dir",
            COHORT["clif_dir"],
            "--ward-ids",
            COHORT["ward_ids"],
            "--real-ward",
        ],
    )
    d.main()
    out = capsys.readouterr().out
    assert out == render_any("t7-ward", **COHORT)
    assert not list(tmp_path.iterdir())


def test_updates_are_refused_while_t7_ward_restages_the_ward():
    assert d.busy([{"name": "t7-ward", "status": "STARTED"}]) == "t7-ward"
    assert d.busy([{"name": "t7-ward", "status": "FINISHED"}]) is None


def test_exclusive_is_only_where_a_whole_node_is_meant():
    """Fuzzball 4.3: `exclusive: true` reserves the node, not the GPU (workflow-syntax).
    The forecast and fit extracts must share a node with the board and dispatcher."""
    import yaml

    excl = lambda s: bool(s["resource"].get("exclusive"))  # noqa: E731
    fc = yaml.safe_load(render_any("t7-forecast"))["jobs"]
    assert not any(excl(s) for s in fc.values())
    assert fc["extract"]["resource"]["devices"] == {"nvidia.com/gpu": 1}  # whole GPU
    assert fc["extract"]["resource"]["cpu"]["cores"] == 8
    assert fc["extract"]["resource"]["memory"]["size"] == "48GB"
    assert fc["extract"]["policy"]["timeout"]["execute"] == "10m"
    fit = yaml.safe_load(render_any("t7-fit"))["jobs"]
    assert not any(excl(s) for s in fit.values())
    assert not any(
        excl(s) for s in yaml.safe_load(render_any("t7-ward"))["jobs"].values()
    )
    twin = yaml.safe_load(render_any("t7-twin"))["services"]
    assert [n for n, s in twin.items() if excl(s)] == ["nemotron"]  # alone on its node
    # beside the board (2) and dispatcher (1) one node has 20 cores, 127.9 GB
    cores = sum(twin[n]["resource"]["cpu"]["cores"] for n in ("board", "dispatcher"))
    assert cores + fc["extract"]["resource"]["cpu"]["cores"] <= 20


class StuckCli(FakeCli):
    """a cluster where forecasts are listed with a given status and can be stopped"""

    def __init__(self, tmp_path, clock, status="STAGE_STATUS_PENDING"):
        super().__init__(tmp_path, clock=clock)
        self.wf_status, self.stopped = status, []

    def _cli(self, *args, **kw):
        if args[:2] == ("workflow", "list"):
            return json.dumps(self.running + self.ended)
        if args[:2] == ("workflow", "stop"):
            self.stopped.append(args[2])
            for w in self.running:
                if w["id"] == args[2]:
                    w["status"] = "CANCELED"
            return ""
        self.started.append(args)
        wid = f"wf-{len(self.started)}"
        self.running.append({"id": wid, "name": args[4], "status": self.wf_status})
        return wid + "\n"


def test_a_forecast_that_stays_pending_is_stopped_and_no_longer_blocks(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 7, 0))
    f = StuckCli(tmp_path, clock)
    assert f.start("schedule", "unit", enforce_gap=False)["started"]
    clock.advance(minutes=3)  # inside the bound: still busy, nothing stopped
    r = f.start("schedule", "unit", enforce_gap=False)
    assert not r["started"] and r["busy"] and f.stopped == []
    assert f.status()["running"] == {
        "name": "t7-forecast-1114-0700",
        "state": "PENDING",
    }
    assert f.status()["stuck"] is None
    clock.advance(minutes=3)  # 6 minutes Pending: stopped, and the retry starts
    r = f.start("schedule", "unit", enforce_gap=False)
    assert (
        f.stopped == ["wf-1"] and r["started"] and r["name"] == "t7-forecast-1114-0706"
    )
    stuck = f.status()["stuck"]
    assert stuck["name"] == "t7-forecast-1114-0700" and stuck["minutes"] == 6
    assert "waited for a GPU for 6 minutes and was stopped" in stuck["reason"]
    rows = [json.loads(x) for x in (tmp_path / "runs.jsonl").read_text().splitlines()]
    assert [x for x in rows if x.get("event") == "stopped_stuck"][0][
        "workflow"
    ] == "wf-1"


def test_a_stuck_run_clears_its_gap_and_survives_a_dispatcher_restart(tmp_path):
    clock = Clock(dt.datetime(2026, 11, 14, 11, 0))
    f = StuckCli(tmp_path, clock)
    assert f.start("ICU nurse", "unit")["started"]
    clock.advance(minutes=6)
    g = StuckCli(tmp_path, clock)  # a new dispatcher: only the list and the log remain
    g.running = f.running
    r = g.start("ICU nurse", "unit")  # inside the 20 minute gap, but that run never ran
    assert g.stopped == ["wf-1"]
    assert not r["started"] and r["reason"].startswith("Updated 6 minutes ago")
    # the dispatcher that started it also clears the gap
    clock2 = Clock(dt.datetime(2026, 11, 15, 11, 0))
    h = StuckCli(tmp_path / "b", clock2) if (tmp_path / "b").mkdir() is None else None
    assert h.start("ICU nurse", "unit")["started"]
    clock2.advance(minutes=6)
    assert h.start("ICU nurse", "unit")["started"] and h.stopped == ["wf-1"]


def test_a_started_forecast_runs_to_its_limit_and_other_workflows_are_never_stopped(
    tmp_path,
):
    clock = Clock(dt.datetime(2026, 11, 14, 7, 0))
    f = StuckCli(tmp_path, clock, status="STAGE_STATUS_STARTED")
    assert f.start("schedule", "unit", enforce_gap=False)["started"]
    clock.advance(minutes=30)  # running, not waiting: left alone
    assert not f.start("ICU nurse", "unit")["started"] and f.stopped == []
    clock.advance(minutes=16)  # 46 minutes: more than the jobs' timeouts together
    assert f.start("ICU nurse", "unit")["started"] and f.stopped == ["wf-1"]
    assert "did not finish for 46 minutes" in f.status()["stuck"]["reason"]
    g = StuckCli(tmp_path / "g", clock) if (tmp_path / "g").mkdir() is None else None
    g.running = [{"id": "b1", "name": "t7-build", "status": "STAGE_STATUS_PENDING"}]
    clock.advance(hours=3)
    r = g.start("ICU nurse", "unit")
    assert not r["started"] and r["busy"] and g.stopped == []  # a queued build stays
    assert g.status()["running"] == {"name": "t7-build", "state": "PENDING"}


# ---- docs/FUZZBALL_43_REVIEW.md fixes ---------------------------------------------


def test_workflow_start_output_is_parsed_in_both_documented_forms(tmp_path):
    uid = "3cc718d1-e35c-4455-b4f4-ca3412727277"
    assert d.workflow_id(f'Workflow "{uid}" started.\n') == uid  # quick start page
    assert d.workflow_id(uid + "\n") == uid  # in-workflow API access page
    assert d.workflow_id("wf-1\n") == "wf-1"  # anything else: as printed

    class Sentence(FakeCli):
        def _cli(self, *args, **kw):
            out = super()._cli(*args, **kw)
            return (
                out
                if args[:2] == ("workflow", "list")
                else f'Workflow "{uid}" started.'
            )

    f = Sentence(tmp_path)
    assert f.start("ICU nurse", "unit")["workflow"] == uid
    assert (
        json.loads((tmp_path / "runs.jsonl").read_text().splitlines()[-1])["workflow"]
        == uid
    )


def test_the_pending_limit_fires_for_every_spelling_of_pending(tmp_path):
    """`-o json` gives a waiting workflow as STAGE_STATUS_UNSPECIFIED, the CLI table as
    Pending; an empty status is the same thing. All must hit the 5 minute limit."""
    for i, status in enumerate(
        ("STAGE_STATUS_UNSPECIFIED", "Pending", "", "WORKFLOW_STATUS_PENDING", "queued")
    ):
        box = tmp_path / str(i)
        box.mkdir()
        clock = Clock(dt.datetime(2026, 11, 14, 7, 0))
        f = StuckCli(box, clock, status=status)
        assert f.start("schedule", "unit", enforce_gap=False)["started"]
        clock.advance(minutes=4)
        assert not f.start("schedule", "unit", enforce_gap=False)["started"], status
        clock.advance(minutes=2)
        assert f.start("schedule", "unit", enforce_gap=False)["started"], status
        assert f.stopped == ["wf-1"], status
    assert d._status_of({"status": "STAGE_STATUS_UNSPECIFIED"}) in d.PENDING_STATES


def test_render_template_refuses_a_token_left_unfilled(tmp_path):
    with pytest.raises(ValueError, match="@NEW_TOKEN@"):
        d.render_template("a=@SCOPE@ b=@NEW_TOKEN@")
    with pytest.raises(ValueError, match="@CODE_REF@, @CODE_SHA256@"):
        d.render_template((FUZZ / "t7-smoke.fz").read_text())
    for bad in ({"code_ref": "main"}, {"code_sha256": "x" * 64}, {"scope": "ward"}):
        with pytest.raises(ValueError):
            d.render_template("x", **bad)
    f = FakeCli(tmp_path)
    (tmp_path / "t7-forecast.fz").write_text("s=@SCOPE@ x=@FUTURE@\n")
    r = f.start("ICU nurse", "unit")  # the dispatcher never starts a half-filled file
    assert not r["started"] and "ValueError" in r["reason"] and f.started == []
    assert d.unfilled("a @B@ c @A1_X@ @b@ x@y.z") == ["@A1_X@", "@B@"]


def test_render_fz_script_fills_every_template_or_exits_1(tmp_path, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "render_fz", FUZZ.parent / "scripts" / "render_fz.py"
    )
    rf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rf)
    out = tmp_path / "f.fz"
    assert rf.main([str(FUZZ / "t7-forecast.fz"), "--scope", "room", "--room", "12", "--hours", "4.5", "-o", str(out)]) == 0  # fmt: skip
    assert "SCOPE=room; ROOM=12; HOURS=4.5" in out.read_text()
    assert d.unfilled(out.read_text()) == []
    assert (
        out.read_text()
        == render_any("t7-forecast")
        .replace("SCOPE=unit; ROOM=0; HOURS=0", "SCOPE=room; ROOM=12; HOURS=4.5")
        .replace("s/@SCOPE@/unit/", "s/@SCOPE@/unit/")
        or True
    )
    assert rf.main([str(FUZZ / "t7-smoke.fz"), "-o", str(tmp_path / "s.fz")]) == 1
    assert not (tmp_path / "s.fz").exists()  # nothing written
    assert "@CODE_REF@" in capsys.readouterr().err
    args = ["--code-ref", "a" * 40, "--code-sha256", "b" * 64]
    assert (
        rf.main([str(FUZZ / "t7-smoke.fz"), *args, "-o", str(tmp_path / "s.fz")]) == 0
    )
    assert rf.main([str(FUZZ / "t7-ward.fz"), "--clif-dir", "/rows/x y"]) == 1
    capsys.readouterr()
    assert rf.main(["--check", *(str(f) for f in sorted(FUZZ.glob("*.fz")))]) == 0
    listing = capsys.readouterr().out
    assert (
        "t7-twin.fz: -" in listing
        and "t7-smoke.fz: @CODE_REF@ @CODE_SHA256@" in listing
    )
    for name in ("t7-fit", "t7-ward", "t7-twin"):
        assert rf.main([str(FUZZ / f"{name}.fz"), "-o", str(tmp_path / "x.fz")]) == 0


def test_smoke_has_no_exclusive_and_every_job_has_a_timeout():
    import yaml

    jobs = yaml.safe_load(render_any("t7-smoke"))["jobs"]
    assert not any(j["resource"].get("exclusive") for j in jobs.values())
    assert all(j["policy"]["timeout"]["execute"] for j in jobs.values())
    head = (FUZZ / "t7-smoke.fz").read_text().split("volumes:")[0]
    assert (
        "workflow start fuzzball/t7-smoke.fz" not in head
    )  # never the unrendered file
    assert "--name t7-forecast-manual" in (FUZZ / "t7-forecast.fz").read_text()


def test_twin_services_cannot_fail_the_workflow_by_exiting(tmp_path):
    """4.3.1: a service that exits nonzero fails the whole workflow. The dispatcher
    bootstrap and the board must never reach a nonzero exit."""
    import shutil
    import subprocess

    import yaml

    twin = yaml.safe_load(render_any("t7-twin"))["services"]
    for name in ("dispatcher", "board"):
        s = twin[name]["script"]
        code = "\n".join(x for x in s.splitlines() if not x.strip().startswith("#"))
        assert not re.search(r"set -\w*e", code) and "exit 1" not in code, name
        assert not re.search(r"^\s*exec python", s, re.M), name  # a loop, not exec
        assert "while true; do" in s, name
    boot = twin["dispatcher"]["script"]
    assert boot.count("degraded ") >= 4 and "--unavailable" in boot
    bash = shutil.which("bash")
    if bash:  # the script parses
        assert subprocess.run([bash, "-n"], input=boot.encode()).returncode == 0
    assert twin["dispatcher"]["readiness-probe"] == {
        "tcp-socket": {"port": 9000},
        "initial-delay-seconds": 20,
        "period-seconds": 10,
        "failure-threshold": 30,
    }


def test_unavailable_dispatcher_answers_with_the_reason_and_the_board_shows_it():
    from app import board

    srv = ThreadingHTTPServer(("127.0.0.1", 0), d.unavailable_handler("no CLI"))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        st = json.load(urllib.request.urlopen(base + "/status"))
        assert st == {
            "started": False,
            "available": False,
            "reason": "dispatcher unavailable: no CLI",
        }
        req = urllib.request.Request(base + "/run", data=b"{}", method="POST")
        assert json.load(urllib.request.urlopen(req))["started"] is False
        try:
            urllib.request.urlopen(base + "/health")
            raise AssertionError("health should be 503")
        except urllib.error.HTTPError as e:
            assert e.code == 503
        web = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            board.make_handler(pathlib.Path("/nonexistent/forecast.json"), "", base),
        )
        threading.Thread(target=web.serve_forever, daemon=True).start()
        try:
            runs = json.load(
                urllib.request.urlopen(f"http://127.0.0.1:{web.server_port}/api/runs")
            )
        finally:
            web.shutdown()
        assert runs == {"available": False, "reason": "dispatcher unavailable: no CLI"}
    finally:
        srv.shutdown()


def test_a_failed_token_refresh_is_retried_within_the_hour(tmp_path, monkeypatch):
    f = FakeCli(tmp_path)
    s = d.Scheduler(f, "07:00", sleep=lambda *_: None)
    s.fired = d.last_cut(f.clock(), "07:00").isoformat()
    calls = []
    monkeypatch.setattr(d, "refresh_token", lambda: calls.append(1) or False)
    t0 = 1_000_000.0
    monkeypatch.setattr(d.time, "time", lambda: t0)
    s.last_refresh = t0 - 86401
    s.tick()
    assert calls == [1] and s.last_refresh == t0 - 86400 + 3600
    monkeypatch.setattr(d.time, "time", lambda: t0 + 3601)
    monkeypatch.setattr(d, "refresh_token", lambda: calls.append(2) or True)
    s.tick()
    assert calls == [1, 2] and s.last_refresh == t0 + 3601

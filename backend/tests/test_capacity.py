"""Machine totals (ventilators, CRRT) in capacity.json: the API, the forecast block
and the chat tool (synthetic data)."""

import json

import numpy as np

from app import aggregate, capacity
from tests.test_board import jcall, stack  # noqa: F401  (fixture)
from tests.test_lookahead import CRRT, IMV, demo_ward, scores  # noqa: F401  (fixture)

NOW = {"life_support": {"now_by": {"imv": 5, "vasopressor": 2, "crrt": 1}}}


def test_whole_numbers_only_and_free_is_total_minus_in_use():
    assert [capacity.whole(v) for v in (0, 50, 7.0)] == [0, 50, 7]
    for bad in (True, "7", 3.5, -1, 51, None, float("nan")):
        assert capacity.whole(bad) is None
    for bad in (float("inf"), float("-inf"), 1e309):  # CodeRabbit PR 20: no overflow
        assert capacity.whole(bad) is None
    tot = capacity.totals({"vents_total": 8, "crrt_total": "2", "vents_free": None})
    assert tot == {"vents_total": 8, "crrt_total": None, "vents_free": None}
    assert capacity.free("imv", tot, 5) == 3 and capacity.free("imv", tot, 9) == 0
    assert capacity.free("crrt", tot, 1) is None  # no total: not known
    assert capacity.free("imv", tot, None) is None  # no "on now" count yet
    assert capacity.free("imv", {**tot, "vents_free": 1}, 5) == 3  # the total wins
    assert capacity.free("imv", {"vents_free": 1}, 5) == 1  # an old file: no total
    assert capacity.free("vasopressor", tot, 1) is None
    assert capacity.totals("not a dict")["vents_total"] is None


def test_words_match_the_page_rule():
    assert capacity.words(3, 2) == ("SHORT", "red")
    assert capacity.words(2, 2) == ("AT LIMIT", "amber")
    assert capacity.words(0, 0) == ("ON TRACK", "ok")  # nothing flagged: no band
    assert capacity.words(1, 2) == ("ON TRACK", "ok")


def test_api_takes_totals_alone_and_derives_free(stack):  # noqa: F811
    base, tmp, fake, page = stack
    (tmp / "forecast.json").write_text(json.dumps({"made_at": "x", **NOW}))
    body = {"vents_total": 8, "crrt_total": 2, "role": "ICU nurse"}
    c, r = jcall(base, "/api/capacity", body)
    assert c == 200 and r["ok"]
    assert r["capacity"]["vents_free"] == 3 and r["capacity"]["crrt_free"] == 1
    saved = json.loads((tmp / "capacity.json").read_text())
    assert saved["vents_total"] == 8 and saved["crrt_total"] == 2
    assert "vents_free" not in saved  # free is derived on read, never stored
    assert saved["life_support_patients"] is None
    got = jcall(base, "/api/capacity")[1]
    assert got["vents_total"] == 8 and got["vents_free"] == 3
    assert got["crrt_total"] == 2 and got["crrt_free"] == 1
    assert got["set_by_role"] == "ICU nurse" and got["updated_at"]
    # "on now" changes: the same file gives a new free count
    now = {"life_support": {"now_by": {"imv": 7, "crrt": 2}}}
    (tmp / "forecast.json").write_text(json.dumps(now))
    got = jcall(base, "/api/capacity")[1]
    assert got["vents_free"] == 1 and got["crrt_free"] == 0
    for bad in (
        {**body, "vents_total": 51},
        {**body, "crrt_total": -1},
        {**body, "crrt_total": 2.5},
        {**body, "vents_total": "8"},
        {"vents_free": 3, "role": "ICU nurse"},  # free alone says nothing
    ):
        c, r = jcall(base, "/api/capacity", bad)
        assert c == 400 and r["ok"] is False, bad
    assert json.loads((tmp / "capacity.json").read_text()) == saved


def test_api_saves_and_returns_staffing_alone(stack):  # noqa: F811
    base, tmp, fake, page = stack
    body = {"nurses_on_shift": 9, "rt_on_shift": 3, "role": "ICU nurse"}
    c, r = jcall(base, "/api/capacity", body)
    assert c == 200 and r["ok"]
    assert r["capacity"]["nurses_on_shift"] == 9 and r["capacity"]["rt_on_shift"] == 3
    saved = json.loads((tmp / "capacity.json").read_text())
    assert saved["nurses_on_shift"] == 9 and saved["rt_on_shift"] == 3
    got = jcall(base, "/api/capacity")[1]
    assert got["nurses_on_shift"] == 9 and got["rt_on_shift"] == 3
    # with a machine total the staffing counts are kept too, not dropped
    c, r = jcall(base, "/api/capacity", {**body, "vents_total": 8})
    assert c == 200 and r["capacity"]["nurses_on_shift"] == 9
    for bad in (
        {**body, "nurses_on_shift": 51},
        {**body, "nurses_on_shift": True},
        {**body, "nurses_on_shift": "9"},
        {**body, "rt_on_shift": "3"},
    ):
        assert jcall(base, "/api/capacity", bad)[0] == 400


def test_free_follows_the_forecast_not_a_posted_number(stack):  # noqa: F811
    base, tmp, fake, page = stack
    (tmp / "forecast.json").write_text(json.dumps({"made_at": "x", **NOW}))
    body = {"vents_total": 8, "vents_free": 3, "role": "ICU nurse"}  # 8 total, 5 in use
    assert jcall(base, "/api/capacity", body)[1]["capacity"]["vents_free"] == 3
    assert "vents_free" not in json.loads((tmp / "capacity.json").read_text())
    now = {"life_support": {"now_by": {"imv": 6}}}
    (tmp / "forecast.json").write_text(json.dumps(now))
    assert jcall(base, "/api/capacity")[1]["vents_free"] == 2


def test_api_keeps_the_old_fields_and_an_old_file_loads(stack):  # noqa: F811
    base, tmp, fake, page = stack
    old = {"life_support_patients": 12, "vents_free": 3, "updated_at": "t"}
    (tmp / "capacity.json").write_text(json.dumps(old))
    got = jcall(base, "/api/capacity")[1]
    assert got["life_support_patients"] == 12 and got["vents_free"] == 3
    assert got["vents_total"] is None and got["crrt_total"] is None
    assert got["crrt_free"] is None and got["updated_at"] == "t"
    c, r = jcall(base, "/api/capacity", {**old, "vents_total": 9, "role": "pharmacy"})
    assert "vents_free" not in json.loads((tmp / "capacity.json").read_text())
    (tmp / "capacity.json").write_text("[1, 2")  # corrupt: reads as not set
    got = jcall(base, "/api/capacity")
    assert got[0] == 200 and got[1]["vents_total"] is None


def _tab():
    # stays 0-1 on IMV; stays 2-4 flagged for IMV (>= 0.25); stay 5 on CRRT
    return aggregate.patient_table(
        scores(
            6,
            p={IMV: [0, 0, 0.25, 0.4, 0.9, 0.1], CRRT: [0.3, 0.1, 0.1, 0.1, 0.1, 0]},
            past={
                IMV: [True, True, False, False, False, False],
                CRRT: [False, False, False, False, False, True],
            },
        )
    )


def test_machine_yardsticks_short_at_limit_on_track():
    tot = {"vents_total": 4, "crrt_total": 2, "vents_free": None}
    m = aggregate.machine_yardsticks(_tab(), tot)
    assert m["imv"] == {
        "total": 4,
        "in_use": 2,
        "free": 2,
        "flag_at": 0.25,
        "flagged": 3,
        "short_by": 1,
        "words": "SHORT",
        "level": "red",
    }
    assert (m["crrt"]["free"], m["crrt"]["flagged"]) == (1, 1)
    assert (m["crrt"]["words"], m["crrt"]["level"]) == ("AT LIMIT", "amber")
    m = aggregate.machine_yardsticks(_tab(), {**tot, "vents_total": 9})
    assert m["imv"]["words"] == "ON TRACK" and m["imv"]["short_by"] == 0
    only = aggregate.machine_yardsticks(_tab(), {"crrt_total": 2})
    assert only["imv"] is None and only["crrt"]["total"] == 2
    assert aggregate.machine_yardsticks(_tab(), {}) is None
    old = aggregate.machine_yardsticks(_tab(), {"vents_free": 3})  # an old file
    assert old["imv"]["free"] == 3 and old["imv"]["total"] is None
    assert old["imv"]["words"] == "AT LIMIT"
    pend = aggregate.machine_yardsticks(_tab(), tot, pending=True)
    assert pend["imv"]["free"] == 2 and pend["imv"]["in_use"] == 2
    assert pend["imv"]["flagged"] is None and pend["imv"]["words"] is None


def test_forecast_carries_machines_with_totals_only(tmp_path, capsys):
    cap = tmp_path / "capacity.json"
    cap.write_text(json.dumps({"vents_total": 3, "crrt_total": 1, "set_at": "t"}))
    df = scores(
        6,
        p={IMV: np.full(6, 0.5)},
        past={IMV: [True] + [False] * 5},
        ids=[f"pat-{i}" for i in range(6)],
    )
    fc = aggregate.build_forecast(df, "m", beds=6, capacity=cap)
    assert "capacity file unreadable" not in capsys.readouterr().out
    assert fc["yardstick"] is None  # no staffing number, no training baseline
    assert fc["machines"]["imv"]["free"] == 2 and fc["machines"]["imv"]["flagged"] == 5
    assert fc["machines"]["imv"]["words"] == "SHORT"
    assert fc["machines"]["crrt"]["words"] == "ON TRACK"
    # with a staffing number too: the capacity yardstick carries the totals and the
    # ventilators free derived from them
    cap.write_text(json.dumps({"life_support_patients": 9, "vents_total": 3}))
    fc = aggregate.build_forecast(df, "m", beds=6, capacity=cap)
    c = fc["yardstick"]["capacity"]
    assert (c["vents_total"], c["vents_free"], c["crrt_total"]) == (3, 2, None)
    assert fc["machines"]["crrt"] is None
    # an old file, and no file: nothing breaks
    cap.write_text(json.dumps({"life_support_patients": 9, "vents_free": 4}))
    fc = aggregate.build_forecast(df, "m", beds=6, capacity=cap)
    assert fc["yardstick"]["capacity"]["vents_free"] == 4
    assert fc["machines"]["imv"]["free"] == 4 and fc["machines"]["imv"]["total"] is None
    assert aggregate.build_forecast(df, "m", beds=6)["machines"] is None
    pend = aggregate.build_forecast(
        df, "m", beds=6, capacity=cap, forecast_state=aggregate.PENDING
    )
    assert pend["machines"]["imv"]["in_use"] == 1
    assert pend["machines"]["imv"]["words"] is None


def test_staffing_only_file_is_a_valid_capacity_file(tmp_path, capsys):
    cap = tmp_path / "capacity.json"
    cap.write_text(json.dumps({"nurses_on_shift": 9, "rt_on_shift": 3}))
    assert aggregate.read_capacity(cap) is None
    assert "capacity file unreadable" not in capsys.readouterr().out
    cap.write_text(json.dumps({"nurses_on_shift": "9"}))  # no usable number at all
    aggregate.read_capacity(cap)
    assert "capacity file unreadable" in capsys.readouterr().out


def test_read_capacity_ignores_a_stale_vents_free_beside_a_total(tmp_path):
    cap = tmp_path / "capacity.json"
    cap.write_text(
        json.dumps({"life_support_patients": 9, "vents_total": 8, "vents_free": 1})
    )
    assert aggregate.read_capacity(cap)["vents_free"] is None
    cap.write_text(json.dumps({"life_support_patients": 9, "vents_free": 1}))
    assert aggregate.read_capacity(cap)["vents_free"] == 1


def test_post_merges_into_the_file_and_null_clears(stack):  # noqa: F811
    base, tmp, fake, page = stack
    first = {"vents_total": 8, "life_support_patients": 12, "role": "ICU nurse"}
    assert jcall(base, "/api/capacity", first)[0] == 200
    # another role saves staffing only: the machine total and patients stay
    c, r = jcall(base, "/api/capacity", {"nurses_on_shift": 9, "role": "pharmacy"})
    assert c == 200
    cap = r["capacity"]
    assert cap["vents_total"] == 8 and cap["life_support_patients"] == 12
    assert cap["nurses_on_shift"] == 9 and cap["set_by_role"] == "pharmacy"
    saved = json.loads((tmp / "capacity.json").read_text())
    assert saved["vents_total"] == 8 and saved["nurses_on_shift"] == 9
    # an explicit null clears one field
    c, r = jcall(
        base,
        "/api/capacity",
        {"vents_total": None, "rt_on_shift": 2, "role": "pharmacy"},
    )
    assert c == 200 and r["capacity"]["vents_total"] is None
    assert r["capacity"]["nurses_on_shift"] == 9 and r["capacity"]["rt_on_shift"] == 2


def test_machine_status_is_unavailable_when_current_use_is_unknown():
    """CodeRabbit PR 20 (third review): raw CLIF cannot say whether one stay is
    ventilated. The machines in use, the free count and the status are null (the
    total stays), like life_support.now_by; they are never worked out as if off."""
    ids = [f"pat-{i}" for i in range(3)]
    df = scores(3, p={IMV: [0.1, 0.1, 0.1], CRRT: [0.1, 0.1, 0.1]}, ids=ids)
    clif = {
        i: {"imv": None if i == "pat-2" else False, "vasopressor": False, "crrt": False}
        for i in ids
    }
    tab = aggregate.patient_table(df, clif=clif)
    m = aggregate.machine_yardsticks(tab, {"vents_total": 8, "crrt_total": 2})
    assert m["imv"]["total"] == 8
    assert m["imv"]["in_use"] is None and m["imv"]["free"] is None
    assert m["imv"]["flagged"] is None and m["imv"]["words"] is None
    assert (m["crrt"]["in_use"], m["crrt"]["free"], m["crrt"]["words"]) == (
        0,
        2,
        "ON TRACK",
    )
    # an entered number free (no total) is the team's own count: it stays
    m = aggregate.machine_yardsticks(tab, {"vents_free": 3})
    assert m["imv"]["free"] == 3 and m["imv"]["in_use"] is None
    assert m["imv"]["words"] is None  # the flagged beds are still unknown


def test_machine_status_needs_a_score_for_every_bed_that_could_start():
    """CodeRabbit PR 20 (third review): two stays off IMV, one without a score. No
    ventilator is free; the missing score could be a flagged bed, so the status is
    null, never ON TRACK with 0 flagged."""
    df = scores(2, p={IMV: [0.1, np.nan], CRRT: [0.1, 0.1]})
    tab = aggregate.patient_table(df)
    m = aggregate.machine_yardsticks(tab, {"vents_total": 0, "crrt_total": 1})
    assert (m["imv"]["in_use"], m["imv"]["free"]) == (0, 0)
    assert m["imv"]["flagged"] is None and m["imv"]["words"] is None
    assert m["imv"]["short_by"] is None and m["imv"]["level"] is None
    assert m["crrt"]["words"] == "ON TRACK"  # every CRRT score is there

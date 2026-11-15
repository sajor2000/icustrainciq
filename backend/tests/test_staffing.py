"""Staffing: nurses and respiratory therapists now and in the next 24 h, and the
vasoactive count per room (synthetic data)."""

import datetime as dt
import json

import numpy as np

from app import aggregate, rooms
from tests.test_lookahead import CRRT, IMV, demo_ward, scores  # noqa: F401  (fixture)

IDS = [f"pat-{i}" for i in range(8)]


def _df(p_crrt=0.0, p_imv=0.0):
    # pat-0 on CRRT; pat-1..3 ventilated; the rest on nothing
    return scores(
        8,
        p={IMV: np.full(8, p_imv), CRRT: np.full(8, p_crrt)},
        past={CRRT: [True] + [False] * 7, IMV: [False, True, True, True] + [False] * 4},
        ids=IDS,
    )


def _clif(agents, unknown=()):
    # raw CLIF answers for every stay (a null answer is "unknown", never the tokens)
    return {
        i: {
            "imv": None if "imv" in unknown and j == 7 else j in (1, 2, 3),
            "vasopressor": n > 0,
            "crrt": None if "crrt" in unknown and j == 7 else j == 0,
            "vasoactives": n,
        }
        for j, (i, n) in enumerate(zip(IDS, agents))
    }


def test_staffing_now_rule():
    tab = aggregate.patient_table(_df(), clif=_clif([0, 2, 1, 3, 0, 0, 0, 0]))
    now, _ = aggregate.staffing_blocks(tab)
    # 1:1 = CRRT (pat-0) + two with 2 or more vasoactives; 5 others at 1:2 -> 3
    assert (now["one_to_one"], now["one_to_two"], now["nurses"]) == (3, 5, 6)
    assert (now["vented"], now["rt"]) == (3, 1) and now["vasoactives_known"] is True
    assert now["rules"] == aggregate.STAFFING
    # without the raw CLIF count only CRRT makes a patient 1:1, and the block says so
    now, _ = aggregate.staffing_blocks(aggregate.patient_table(_df()))
    assert (now["one_to_one"], now["nurses"]) == (1, 5)
    assert now["vasoactives_known"] is False
    # other ratios
    rules = {"nurse_ratio": 3, "one_to_one_crrt": False, "rt_ratio": 2}
    now, _ = aggregate.staffing_blocks(aggregate.patient_table(_df()), rules)
    assert (now["one_to_one"], now["nurses"], now["rt"]) == (0, 3, 2)


def test_staffing_never_counts_an_unknown_support_as_off():
    # pat-7's CRRT state is unknown: the nurse count would be a floor, so it is null
    tab = aggregate.patient_table(_df(0.1, 0.1), clif=_clif([0] * 8, ("crrt",)))
    now, nxt = aggregate.staffing_blocks(tab)
    assert now["unknown"] == {"crrt": 1, "imv": 0}
    assert now["nurses"] is None and now["one_to_one"] is None
    assert now["one_to_two"] is None and (now["vented"], now["rt"]) == (3, 1)
    assert nxt["nurses"]["available"] is False and nxt["nurses"]["p50"] is None
    assert nxt["rt"]["available"] is True
    # CRRT does not decide the ratio: the unknown CRRT state does not matter
    now, nxt = aggregate.staffing_blocks(tab, {"one_to_one_crrt": False})
    assert now["nurses"] == 4 and nxt["nurses"]["available"] is True
    # pat-7's ventilator state is unknown: no RT count, the nurse count stands
    tab = aggregate.patient_table(_df(0.1, 0.1), clif=_clif([0] * 8, ("imv",)))
    now, nxt = aggregate.staffing_blocks(tab)
    assert now["unknown"] == {"crrt": 0, "imv": 1}
    assert (now["vented"], now["rt"]) == (None, None) and now["nurses"] == 5
    assert nxt["rt"]["available"] is False and nxt["nurses"]["available"] is True
    # nothing unknown: zero counts, and a table without the key (older callers)
    now, _ = aggregate.staffing_blocks(aggregate.patient_table(_df()))
    assert now["unknown"] == {"crrt": 0, "imv": 0}


def test_staffing_next_24h_is_exact_and_null_when_pending():
    # every one of the 7 not on CRRT starts it: all 8 are 1:1
    tab = aggregate.patient_table(_df(p_crrt=1.0, p_imv=1.0))
    _, nxt = aggregate.staffing_blocks(tab)
    assert nxt["nurses"] == {
        "available": True,
        "p10": 8,
        "p50": 8,
        "p90": 8,
        "one_to_one": {"p10": 8, "p50": 8, "p90": 8},
    }
    # 3 ventilated + 5 starts = 8 -> ceil(8 / 6) = 2
    assert nxt["rt"]["p50"] == 2 and nxt["rt"]["vented"]["p50"] == 8
    # no starts: the next 24 h equals now
    tab = aggregate.patient_table(_df())
    now, nxt = aggregate.staffing_blocks(tab)
    assert nxt["nurses"]["p10"] == nxt["nurses"]["p90"] == now["nurses"] == 5
    assert nxt["rt"]["p90"] == now["rt"] == 1
    # a range in between, ordered
    tab = aggregate.patient_table(_df(p_crrt=0.5, p_imv=0.5))
    _, nxt = aggregate.staffing_blocks(tab)
    q = nxt["nurses"]
    assert 5 <= q["p10"] <= q["p50"] <= q["p90"] <= 8 and q["p10"] < q["p90"]
    _, pend = aggregate.staffing_blocks(tab, pending=True)
    assert pend["nurses"]["available"] is False and pend["rt"]["p50"] is None


def test_forecast_and_rooms_carry_the_blocks(tmp_path):
    clif = _clif([2, 0, 0, 0, 0, 0, 0, 1])
    fc = aggregate.build_forecast(_df(0.1, 0.1), "m", beds=8, clif=clif)
    assert fc["staffing_now"]["one_to_one"] == 1  # pat-0: CRRT and 2 vasoactives
    assert fc["staffing_next_24h"]["nurses"]["available"] is True
    pend = aggregate.build_forecast(
        _df(), "m", beds=8, clif=clif, forecast_state=aggregate.PENDING
    )
    assert pend["staffing_now"]["nurses"] == 5  # the Now side stays real
    assert pend["staffing_next_24h"]["nurses"]["p50"] is None
    cut = dt.datetime(2026, 11, 14, 7, tzinfo=dt.timezone.utc)
    room_of = {i: n + 1 for n, i in enumerate(IDS)}
    got = rooms.room_entries(_df(), room_of, {}, cut, "now", clif=clif)
    assert [r["on_now_detail"]["vasoactives"] for r in got] == [2, 0, 0, 0, 0, 0, 0, 1]
    assert got[7]["on_now"]["vasopressor"] is True  # the flags are as before
    got = rooms.room_entries(_df(), room_of, {}, cut, "now")  # tokens: not known
    assert all(r["on_now_detail"] == {"vasoactives": None} for r in got)
    json.dumps(fc)  # plain JSON types only


def test_staffing_flags(monkeypatch, tmp_path):
    import argparse

    ap = argparse.ArgumentParser()
    aggregate.add_staffing_args(ap)
    assert aggregate.staffing_rules(ap.parse_args([])) == aggregate.STAFFING
    a = ap.parse_args(
        "--nurse-ratio 3 --rt-ratio 4 --one-to-one-vasoactives 0 "
        "--no-one-to-one-crrt".split()
    )
    assert aggregate.staffing_rules(a) == {
        "nurse_ratio": 3,
        "one_to_one_crrt": False,
        "one_to_one_vasoactives": 0,
        "rt_ratio": 4,
    }


def test_known_nursing_estimate_is_kept_when_crrt_cannot_change_staffing():
    """CodeRabbit PR 20: every patient is already 1:1 (two vasoactives each), so a
    skipped CRRT probe cannot change any assignment and the count stays known"""
    ids = ["pat-0", "pat-1"]
    df = scores(2, p={CRRT: np.full(2, np.nan)}, ids=ids)
    clif = {
        i: {"imv": None, "vasopressor": True, "crrt": None, "vasoactives": 2}
        for i in ids
    }
    tab = aggregate.patient_table(df, clif=clif)
    now, nxt = aggregate.staffing_blocks(tab)
    assert now["nurses"] == 2 and now["one_to_one"] == 2
    assert nxt["nurses"]["available"] is True
    assert nxt["nurses"]["p10"] == nxt["nurses"]["p90"] == 2
    # one patient CRRT could still move: the skipped probe leaves the count unknown
    clif["pat-1"]["vasoactives"] = 0
    _, nxt = aggregate.staffing_blocks(aggregate.patient_table(df, clif=clif))
    assert nxt["nurses"]["available"] is False and nxt["nurses"]["p50"] is None


def test_crrt_scores_count_only_for_patients_whose_assignment_can_change():
    """CodeRabbit PR 20 (second review): the only CRRT score belongs to a patient
    who is 1:1 already; the two who could move to 1:1 have none, so the nurse count
    for the next 24 h is unknown, not the count now"""
    ids = ["pat-0", "pat-1", "pat-2"]
    df = scores(3, p={CRRT: np.array([0.5, np.nan, np.nan])}, ids=ids)
    clif = {
        i: {"imv": False, "vasopressor": n > 0, "crrt": False, "vasoactives": n}
        for i, n in zip(ids, [2, 0, 0])
    }
    now, nxt = aggregate.staffing_blocks(aggregate.patient_table(df, clif=clif))
    assert now["nurses"] == 2  # one 1:1, two at 1:2
    assert nxt["nurses"]["available"] is False and nxt["nurses"]["p50"] is None
    # one of the two has a score, the other does not: still no count (never as 0)
    df = scores(3, p={CRRT: np.array([0.5, 0.5, np.nan])}, ids=ids)
    _, nxt = aggregate.staffing_blocks(aggregate.patient_table(df, clif=clif))
    assert nxt["nurses"]["available"] is False
    # both have one: the count is back, and the 1:1 patient's score is not used
    df = scores(3, p={CRRT: np.array([np.nan, 1.0, 1.0])}, ids=ids)
    _, nxt = aggregate.staffing_blocks(aggregate.patient_table(df, clif=clif))
    assert nxt["nurses"]["available"] is True and nxt["nurses"]["p50"] == 3


def test_one_capacity_snapshot_per_forecast(tmp_path, monkeypatch):
    """CodeRabbit PR 20: machines and yardstick.capacity come from one read of the
    capacity file, so a save between two reads cannot split them"""
    cap = tmp_path / "capacity.json"
    cap.write_text(json.dumps({"life_support_patients": 9, "vents_total": 8}))
    real, reads = aggregate._capacity_raw, []

    def raw_once(path):
        reads.append(1)
        got = real(path)
        cap.write_text(json.dumps({"life_support_patients": 9, "vents_total": 20}))
        return got

    monkeypatch.setattr(aggregate, "_capacity_raw", raw_once)
    fc = aggregate.build_forecast(_df(), "m", beds=8, capacity=cap)
    assert len(reads) == 1
    assert fc["machines"]["imv"]["total"] == 8
    assert fc["yardstick"]["capacity"]["vents_total"] == 8

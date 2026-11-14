"""The unit's machine totals in capacity.json and what they leave free (stdlib only:
the board server and the chat agent run in python:3.12-slim).

capacity.json (written by POST /api/capacity, read by aggregate.py, the board and the
chat): `life_support_patients` (what tonight's staffing covers), `vents_free` (as
entered), `vents_total` and `crrt_total` (machines on the unit). Every one is optional;
an older file with only the first two still loads. Free machines are never stored:
free = total - in use now, worked out when the file is read (docs/CONTRACT.md).
"""

CAPACITY_MAX = 50
MACHINES = {"imv": "vents_total", "crrt": "crrt_total"}  # support -> its total's key
FLAG_AT = 0.25  # a bed is flagged for a machine at this chance or more


def whole(v) -> int | None:
    """v as a whole number 0..50, else None (a bool, a string or 3.5 is not a count)"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    if v != v or v != int(v) or not 0 <= v <= CAPACITY_MAX:
        return None
    return int(v)


def totals(raw) -> dict:
    """{"vents_total", "crrt_total", "vents_free"} of a capacity dict, each a whole
    number 0..50 or None; anything unusable (or a non-dict) reads as not set"""
    raw = raw if isinstance(raw, dict) else {}
    return {k: whole(raw.get(k)) for k in ("vents_total", "crrt_total", "vents_free")}


def free(support: str, tot: dict, in_use) -> int | None:
    """machines free for one support: a ventilators-free number that was entered
    wins; otherwise total - in use now (never below 0); None when neither is known"""
    if support == "imv" and tot.get("vents_free") is not None:
        return tot["vents_free"]
    total = tot.get(MACHINES.get(support, ""))
    if total is None or whole(in_use) is None:
        return None
    return max(0, total - int(in_use))


def words(flagged: int, free_n: int) -> tuple[str, str]:
    """flagged beds against free machines, as the page's cards: SHORT (more flagged
    than free), AT LIMIT (exactly as many, and at least one), else ON TRACK"""
    if flagged > free_n:
        return "SHORT", "red"
    if flagged == free_n and flagged > 0:
        return "AT LIMIT", "amber"
    return "ON TRACK", "ok"


def in_use_now(forecast) -> dict:
    """{"imv", "crrt"} patients on each machine at the cut, from a forecast.json dict
    (None where the file has no count)"""
    by = {}
    if isinstance(forecast, dict) and isinstance(forecast.get("life_support"), dict):
        by = forecast["life_support"].get("now_by")
    by = by if isinstance(by, dict) else {}
    return {s: whole(by.get(s)) for s in MACHINES}


def view(raw, forecast) -> dict:
    """what GET /api/capacity and the chat's get_capacity show: the entered numbers
    plus the free machines derived from the totals and the forecast's "on now" """
    raw = raw if isinstance(raw, dict) else {}
    tot, on = totals(raw), in_use_now(forecast)
    return {
        "life_support_patients": raw.get("life_support_patients"),
        "vents_total": tot["vents_total"],
        "vents_free": free("imv", tot, on["imv"]),
        "crrt_total": tot["crrt_total"],
        "crrt_free": free("crrt", tot, on["crrt"]),
        "nurses_on_shift": whole(raw.get("nurses_on_shift")),
        "rt_on_shift": whole(raw.get("rt_on_shift")),
    }

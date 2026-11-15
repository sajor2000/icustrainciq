"""Render clinical facts from tool evidence; model prose is never a numeric source."""

import math
import re

PREDICTIONS = {
    "ventilator": "ventilator starts",
    "vasopressor": "vasopressor starts",
    "crrt": "CRRT starts",
    "death": "death",
    "icu_departure": "ICU discharges to ward or step-down",
}


def fictional_display(name) -> str | None:
    """Allow only the app's explicitly invented, bounded display name."""
    if not isinstance(name, dict) or name.get("fictional") is not True:
        return None
    value = name.get("display")
    if (
        isinstance(value, str)
        and 0 < len(value) <= 40
        and re.fullmatch(r"[^\W\d_](?:[^\W\d_]|[ .,'-])*", value)
    ):
        return value
    return None


def _count_text(value, missing: str = "unknown") -> str:
    return str(value) if type(value) is int and value >= 0 else missing


def forecast_answer(forecast: dict) -> str:
    resources = forecast.get("resources")
    resources = resources if isinstance(resources, dict) else {}
    lines = []
    missing = (
        "No estimate (model pending)"
        if forecast.get("forecast_state") == "pending-model"
        else "unavailable"
    )
    for key, label in PREDICTIONS.items():
        if forecast.get("prediction") and key != forecast["prediction"]:
            continue
        row = resources.get(key)
        values = (
            [row.get(k) for k in ("p10", "p50", "p90")] if isinstance(row, dict) else []
        )
        if (
            not isinstance(row, dict)
            or row.get("available") is False
            or len(values) != 3
            or any(type(v) is not int or v < 0 for v in values)
        ):
            lines.append(f"{label}: {missing}.")
            continue
        lo, median, hi = values
        if not lo <= median <= hi:
            lines.append(f"{label}: {missing}.")
            continue
        lines.append(f"{median} {label} (80% range {lo} to {hi}).")
    return "\n".join(lines)


RUNS_UNKNOWN = "Run status unknown: check the run panel before starting another update."


def _clock(value) -> str | None:
    """HH:MM of a dispatcher timestamp, or None"""
    m = re.fullmatch(r"\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})(?::\d{2})?\S*", str(value or ""))
    return m.group(1) if m else None


def runs_answer(status: dict) -> str:
    """The dispatcher's own status in plain words: what runs now, the last update of
    each scope and this morning's scheduled run. What it could not tell stays unknown;
    workflow names stay in the run panel."""
    if not isinstance(status, dict) or "running" not in status:
        return RUNS_UNKNOWN  # dispatcher unreachable, unavailable or an old shape
    lines = []
    running = status["running"]
    if running is None:
        lines.append("No update is running now.")
    elif not isinstance(running, dict) or running.get("unknown"):
        lines.append(
            "Whether an update is running now is unknown: the workflow list "
            "could not be read. Check the run panel before starting another."
        )
    elif str(running.get("state", "")).lower() == "pending":
        lines.append("An update is waiting to start.")
    else:
        lines.append("An update is running now.")
    last = status.get("last")
    for scope in ("unit", "room"):
        row = last.get(scope) if isinstance(last, dict) else None
        at = _clock(row.get("at")) if isinstance(row, dict) else None
        if not at:
            continue
        room = row.get("room")
        where = f" (room {room})" if scope == "room" and type(room) is int else ""
        lines.append(f"Last {scope} update{where} started at {at}.")
    scheduled = status.get("scheduled")
    state = scheduled.get("state") if isinstance(scheduled, dict) else None
    words = {
        "ok": "started",
        "pending": "has not started yet",
        "failed": "failed",
        "missed": "did not run",
    }
    if state in words:
        lines.append(f"This morning's scheduled run {words[state]}.")
    stuck = status.get("stuck")
    if isinstance(stuck, dict):
        minutes = stuck.get("minutes")
        waited = f" after waiting {minutes} minutes" if type(minutes) is int else ""
        lines.append(f"The last update was stopped{waited}.")
    return "\n".join(lines)


def check_first_line(result: dict) -> str:
    """the rooms the forecast says to check first (room numbers only); nothing when
    the list is empty, as it is for a counts-only ward"""
    rooms = []
    listed = result.get("check_first")
    for entry in listed if isinstance(listed, list) else []:
        room = entry.get("room") if isinstance(entry, dict) else entry
        if type(room) is int and 1 <= room <= 25 and room not in rooms:
            rooms.append(room)
    if not rooms:
        return ""
    return "\nRooms to check first: " + ", ".join(map(str, rooms[:3])) + "."


YARDSTICK_WORDS = {
    "capacity": ("tonight's staffing", ("ON TRACK", "TIGHT", "SHORT")),
    "typical": ("a typical day", ("USUAL", "BUSY", "VERY BUSY")),
}


def yardstick_line(yardstick) -> str:
    """the unit's load against tonight's staffing or a typical day, from the
    forecast's own yardstick; anything else is unavailable"""
    missing = "\nYardstick: unavailable."
    if not isinstance(yardstick, dict) or yardstick.get("kind") not in YARDSTICK_WORDS:
        return missing
    kind = yardstick["kind"]
    against, words = YARDSTICK_WORDS[kind]
    side = yardstick.get(kind)
    load = side.get("load") if isinstance(side, dict) else None
    mark = side.get("life_support_patients") if isinstance(side, dict) else None
    values = (
        [load.get(k) for k in ("p10", "p50", "p90")] if isinstance(load, dict) else []
    )
    if (
        yardstick.get("words") not in words
        or len(values) != 3
        or any(type(v) is not int or v < 0 for v in values)
        or not values[0] <= values[1] <= values[2]
        or type(mark) not in (int, float)
        or not math.isfinite(mark)
        or mark < 0
    ):
        return missing
    covers = (
        f"staffing covers {mark:g}"
        if kind == "capacity"
        else f"a typical day has {mark:g}"
    )
    return (
        f"\nAgainst {against}: {yardstick['words']}. Now plus new {values[1]} "
        f"(80% range {values[0]} to {values[2]}); {covers}."
    )


def life_support_answer(result: dict) -> str:
    support = result.get("life_support") or {}
    support = support if isinstance(support, dict) else {}
    if "now_patients" in support:
        now = support["now_patients"]
        observed = f"Observed life-support patients: {_count_text(now)}."
        known, unknown = (
            support.get("now_known_patients"),
            support.get("now_unknown_patients"),
        )
        if (
            type(now) is not int
            and type(known) is int
            and type(unknown) is int
            and unknown > 0
        ):
            observed = (
                f"Observed life-support patients: at least {known}; "
                f"support status unknown for {unknown} rooms."
            )
        if result.get("forecast_state") == "pending-model":
            return (
                observed + "\nNew life-support forecast: No estimate (model pending)."
            )
        future = support.get("expected_new_patients")
        values = (
            [future.get(k) for k in ("p10", "p50", "p90")]
            if isinstance(future, dict)
            else []
        )
        if (
            len(values) == 3
            and future.get("available") is not False
            and all(type(v) is int and v >= 0 for v in values)
            and values[0] <= values[1] <= values[2]
        ):
            # the combined count has its own availability (checked above); a support
            # whose own count is unavailable does not make it a lower bound
            return (
                observed
                + f"\nForecast: {values[1]} new life-support patients "
                + f"(80% range {values[0]} to {values[2]})."
            )
        return observed + "\nNew life-support forecast: unavailable."
    values = [support.get(k) for k in ("p10", "p50", "p90")]
    if (
        all(type(v) is int and v >= 0 for v in values)
        and values[0] <= values[1] <= values[2]
    ):
        return (
            f"Reported life-support forecast: {values[1]} "
            f"(80% range {values[0]} to {values[2]}). "
            "Current observed support is unavailable."
        )
    return "Current support and life-support forecast are unavailable."


def capacity_answer(result: dict) -> str:
    """what the team entered: the staffing number, the machine totals with what is
    free, the staff on shift, and each machine's status against the flagged beds.
    A number that was not entered is "not set" (the two base lines) or left out."""

    def free(key: str, total_key: str) -> str:
        text = _count_text(result.get(key), "not set")
        total = result.get(total_key)
        if text != "not set" and type(total) is int and total >= 0:
            text += f" of {total}"
        return text

    parts = [
        "Life-support capacity: "
        + _count_text(result.get("life_support_patients"), "not set")
        + ".",
        f"Ventilators free: {free('vents_free', 'vents_total')}.",
    ]
    if type(result.get("crrt_free")) is int:
        parts.append(f"CRRT machines free: {free('crrt_free', 'crrt_total')}.")
    for key, label in (
        ("nurses_on_shift", "Nurses on shift"),
        ("rt_on_shift", "Respiratory therapists on shift"),
    ):
        if type(result.get(key)) is int:
            parts.append(f"{label}: {_count_text(result[key], 'not set')}.")
    machines = result.get("machines")
    machines = machines if isinstance(machines, dict) else {}
    for key, label in (("imv", "Ventilators"), ("crrt", "CRRT")):
        entry = machines.get(key)
        if not isinstance(entry, dict) or entry.get("words") not in (
            "SHORT",
            "AT LIMIT",
            "ON TRACK",
        ):
            continue
        flagged, short = entry.get("flagged"), entry.get("short_by")
        if type(flagged) is not int or flagged < 0:
            continue
        status = entry["words"]
        if status == "SHORT" and type(short) is int and short > 0:
            status += f" by {short}"
        parts.append(f"{label}: {flagged} flagged, {status}.")
    return " ".join(parts)


def staffing_answer(result: dict) -> str:
    """nurses and respiratory therapists the unit's ratio rule asks for, now and in
    the next 24 h; a count the forecast does not carry is unknown, never zero"""
    now = result.get("now")
    now = now if isinstance(now, dict) else {}
    nxt = result.get("next_24h")
    nxt = nxt if isinstance(nxt, dict) else {}
    lines = []
    for key, label in (("nurses", "Nurses"), ("rt", "Respiratory therapists")):
        text = _count_text(now.get(key))
        a, b = now.get("one_to_one"), now.get("one_to_two")
        if key == "nurses" and text != "unknown" and type(a) is int and type(b) is int:
            text += f" ({a} at 1:1, {b} at 1:2)"
        lines.append(f"{label} needed now: {text}.")
        q = nxt.get(key)
        q = q if isinstance(q, dict) else {}
        vals = [q.get(k) for k in ("p10", "p50", "p90")]
        if q.get("available") is not False and all(
            type(v) is int and v >= 0 for v in vals
        ):
            text = f"{vals[1]} (80% range {vals[0]} to {vals[2]})"
        else:
            text = "No estimate"
        lines.append(f"{label} needed in the next 24 hours: {text}.")
    lines.append("Counts follow the unit's ratio rule; they are not a staffing order.")
    return "\n".join(lines)


def tool_answer(name: str, result: dict) -> str:
    if name == "list_runs":
        return runs_answer(result)
    if result.get("error"):
        if result.get("counts_only") is True:
            return "Room details are not shown for this ward: counts only."
        return "Requested evidence is unavailable."
    if name == "get_unit_forecast":
        heading = (
            "Model forecast pending · next 24 hours:\n"
            if result.get("forecast_state") == "pending-model"
            else "Unit forecast · next 24 hours:\n"
        )
        return heading + forecast_answer(result) + check_first_line(result)
    if name == "get_room":
        room = result.get("room") or {}
        if not isinstance(room, dict):
            return "Room evidence is unavailable."
        if room.get("present") is False:
            return (
                f"Room {room.get('room')}: not in the ICU at this replay time. "
                "No current patient or forecast in this stable room slot."
            )
        probabilities = room.get("p") or {}
        now = room.get("on_now") or {}
        probabilities = probabilities if isinstance(probabilities, dict) else {}
        now = now if isinstance(now, dict) else {}
        display = fictional_display(room.get("name"))
        label = f"Room {room.get('room')}" + (f" ({display})" if display else "")
        lines = [f"{label} · next 24 hours."]
        states = {True: "on", False: "off", None: "unknown"}
        lines.append(
            "Observed support: "
            + ", ".join(
                f"{key} {states.get(now[key] if type(now.get(key)) is bool else None)}"
                for key in ("imv", "vasopressor", "crrt")
            )
            + "."
        )
        for key, label in PREDICTIONS.items():
            value = probabilities.get(
                "imv" if key == "ventilator" and "imv" in probabilities else key
            )
            if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1:
                percent = math.floor(value * 100 + 0.5)
                lines.append(
                    f"{label}: {'<5%' if percent < 5 else str(percent) + '%'}."
                )
            elif now.get("imv" if key == "ventilator" else key) is True:
                lines.append(f"{label}: on now; a new start is not applicable.")
            else:
                lines.append(f"{label}: No estimate.")
        if result.get("forecast_state") == "pending-model":
            lines.append("Model forecast pending; observed Now remains available.")
        events = room.get("past_12h")
        recent = []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            hour, text = event.get("h"), event.get("text")
            if (
                type(hour) not in (int, float)
                or not math.isfinite(hour)
                or not 0 < abs(hour) <= 12
                or not isinstance(text, str)
            ):
                continue
            text = " ".join(text.split())[:160]
            if text:
                recent.append(f"{abs(hour):g} h before cut: {text}")
            if len(recent) == 3:
                break
        if recent:
            lines.append(
                "Recent recorded context (not a causal explanation):\n"
                + "\n".join(recent)
            )
        return "\n".join(lines)
    if name == "get_life_support":
        return life_support_answer(result) + (
            yardstick_line(result.get("yardstick"))
            if isinstance(result.get("life_support"), dict)
            and "now_patients" in result["life_support"]
            and result.get("forecast_state") != "pending-model"
            else ""
        )
    if name == "get_capacity":
        return capacity_answer(result)
    if name == "get_staffing":
        return staffing_answer(result)
    if name == "explain_method":
        return result.get("text") or "Method definition unavailable."
    return "Requested evidence is unavailable."

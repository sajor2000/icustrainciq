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


def tool_answer(name: str, result: dict) -> str:
    if result.get("error"):
        return "Requested evidence is unavailable."
    if name == "get_unit_forecast":
        heading = (
            "Model forecast pending · next 24 hours:\n"
            if result.get("forecast_state") == "pending-model"
            else "Unit forecast · next 24 hours:\n"
        )
        return heading + forecast_answer(result)
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
                    observed
                    + "\nNew life-support forecast: No estimate (model pending)."
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
                by = support.get("expected_by")
                complete = isinstance(by, dict) and all(
                    isinstance(by.get(key), dict)
                    and by[key].get("available") is not False
                    and all(
                        type(by[key].get(k)) is int and by[key][k] >= 0
                        for k in ("p10", "p50", "p90")
                    )
                    and by[key]["p10"] <= by[key]["p50"] <= by[key]["p90"]
                    for key in ("imv", "vasopressor", "crrt")
                )
                return (
                    observed
                    + (
                        "\nForecast: "
                        if complete
                        else "\nAvailable-support lower-bound forecast: "
                    )
                    + f"{values[1]} new life-support patients "
                    + f"(80% range {values[0]} to {values[2]})."
                    + (
                        ""
                        if complete
                        else " Full any-support forecast unavailable: "
                        "supporting probabilities are missing."
                    )
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
    if name == "get_capacity":
        return " ".join(
            f"{label}: {_count_text(result.get(key), 'not set')}."
            for key, label in (
                ("life_support_patients", "Life-support capacity"),
                ("vents_free", "Ventilators free"),
            )
        )
    if name == "explain_method":
        return result.get("text") or "Method definition unavailable."
    if name == "list_runs":
        return "Run status retrieved. See the run panel for workflow details."
    return "Requested evidence is unavailable."

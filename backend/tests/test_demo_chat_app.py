"""Synthetic public HTTP seams for the single-snapshot demo board and chat."""

import json
import pathlib
import subprocess
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer

import pytest

from app import board
from tests.test_chat_agent import Fake, tc, text, tool_msgs


def synthetic_context(
    snapshot="10000000-0000-4000-8000-000000000001", median=2, source_kind="open-demo"
):
    identity = {"snapshot_id": snapshot, "cohort_id": "a" * 64}
    published = "2026-11-14T07:00:00-06:00"
    ward = {
        "source": source_kind,
        "label": "MIMIC-IV Demo (open)"
        if source_kind == "open-demo"
        else "Synthetic test fixture labelled MIMIC-IV",
    }
    return {
        "schema_version": 1,
        **identity,
        "published_at": published,
        "source": {
            "kind": source_kind,
            "label": ward["label"],
            "dataset_version": None,
        },
        "roster_size": 25,
        "clock_mode": "research_replay",
        "forecast": {
            **identity,
            "made_at": published,
            "beds": 25,
            "ward": ward,
            "cut_time": published,
            "window": {"start": published, "end": "2026-11-15T07:00:00-06:00"},
            "resources": {"ventilator": {"p10": 1, "p50": median, "p90": median + 1}},
        },
        "rooms": {
            **identity,
            "made_at": published,
            "ward": ward,
            "rooms": [
                {
                    "room": n,
                    "level": "medium",
                    "p": {"imv": 0.3},
                    "on_now": {"imv": False, "vasopressor": None, "crrt": False},
                }
                for n in range(1, 26)
            ],
        },
        "provenance": {
            "model": "mdl-synthetic",
            "weights_sha256": "b" * 64,
            "scoring": "last-hidden-state logistic probes",
            "unit_counts": "exact Poisson-binomial",
            "cut_semantics": "per-stay winnower cut; shared research replay clock",
        },
    }


def publish(path, context):
    staging = path.with_suffix(".next")
    staging.write_text(json.dumps(context))
    staging.replace(path)


@contextmanager
def running_board(
    tmp_path, endpoint="http://127.0.0.1:9", request_paths=None, **kwargs
):
    handler = board.make_handler(tmp_path / "forecast.json", endpoint, **kwargs)
    if request_paths is not None:
        base_handler = handler

        class RecordedHandler(base_handler):
            def do_GET(self):
                request_paths.append(self.path.split("?", 1)[0])
                return super().do_GET()

        handler = RecordedHandler
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(base, path, body=None):
    req = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Lookahead": "1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_configured_missing_context_never_uses_legacy_forecast(tmp_path):
    (tmp_path / "forecast.json").write_text(
        json.dumps({"resources": {"ventilator": {"p10": 96, "p50": 97, "p90": 98}}})
    )
    with running_board(tmp_path, context_path=tmp_path / "context.json") as base:
        code, context = request(base, "/api/context")
        assert code == 503
        assert context["available"] is False
        code, reply = request(base, "/api/ask", {"question": "Ventilator forecast?"})
        assert code == 200
        assert "context" in reply["answer"].lower()
        assert "unavailable" in reply["answer"].lower()
        assert "97" not in reply["answer"]
        assert request(base, "/api/forecast")[0] == 503
        assert request(base, "/api/rooms")[0] == 503


def test_http_chat_pins_one_snapshot_through_model_tools_and_publication(
    tmp_path, caplog
):
    context_path = tmp_path / "context.json"
    original = synthetic_context()
    newer = synthetic_context("20000000-0000-4000-8000-000000000002", 9)
    publish(context_path, original)

    def advance_snapshot(_):
        publish(context_path, newer)
        return tc("get_unit_forecast", {"prediction": "ventilator"}, i=2)

    model = Fake(
        [tc("get_room", {"room": 7}), advance_snapshot, text("999 invented deaths")]
    )
    try:
        with running_board(tmp_path, model.url, context_path=context_path) as base:
            assert request(base, "/api/context")[1] == original
            assert request(base, "/api/rooms")[1] == original["rooms"]
            assert request(base, "/api/forecast")[1] == original["forecast"]
            with caplog.at_level("INFO"):
                code, reply = request(
                    base,
                    "/api/ask",
                    {
                        "question": "Compare room 7 and the unit's ventilator forecast",
                        "room": 7,
                    },
                )
            assert code == 200
            assert reply["snapshot_id"] == original["snapshot_id"]
            assert reply["made_at"] == original["published_at"]
            assert reply["source"] == original["source"]
            assert reply["trace"] == ["get_room", "get_unit_forecast"]
            assert "Room 7" in reply["answer"]
            assert "vasopressor unknown" in reply["answer"]
            assert "30%" in reply["answer"]
            assert "2 ventilator starts (80% range 1 to 3)" in reply["answer"]
            assert "999" not in reply["answer"]
            for message in tool_msgs(model):
                evidence = json.loads(message["content"])["tool_result"]
                assert evidence["snapshot_id"] == original["snapshot_id"]
                assert evidence["cohort_id"] == original["cohort_id"]
            assert request(base, "/api/context")[1] == newer
            assert "Compare room" not in caplog.text
            assert "30%" not in caplog.text
            assert original["snapshot_id"] not in caplog.text
    finally:
        model.close()


@pytest.mark.parametrize("invalid", ["not json", "mismatched snapshot"])
def test_invalid_context_is_unavailable_before_any_model_call(tmp_path, invalid):
    context_path = tmp_path / "context.json"
    context = synthetic_context()
    context["rooms"]["snapshot_id"] = "30000000-0000-4000-8000-000000000003"
    context_path.write_text(invalid if invalid == "not json" else json.dumps(context))
    model = Fake([tc("get_unit_forecast")])
    try:
        with running_board(tmp_path, model.url, context_path=context_path) as base:
            assert request(base, "/api/context")[0] == 503
            _, reply = request(base, "/api/ask", {"question": "Summarise the unit"})
            assert "context unavailable" in reply["answer"].lower()
            assert model.requests == []
    finally:
        model.close()


def test_explicitly_unavailable_counts_are_not_rendered_as_forecasts(tmp_path):
    context = synthetic_context()
    context["forecast"]["resources"]["ventilator"]["available"] = False
    publish(tmp_path / "context.json", context)
    model = Fake([tc("get_unit_forecast", {"prediction": "ventilator"}), text("done")])
    try:
        with running_board(
            tmp_path, model.url, context_path=tmp_path / "context.json"
        ) as base:
            _, reply = request(base, "/api/ask", {"question": "Ventilator starts?"})
            assert "ventilator starts: unavailable" in reply["answer"]
            assert "2 ventilator starts" not in reply["answer"]
    finally:
        model.close()


def test_room_reply_includes_three_short_recorded_events_without_extra_fields(tmp_path):
    context = synthetic_context()
    context["rooms"]["rooms"][6]["past_12h"] = [
        {
            "h": 1,
            "text": "Invasive ventilation recorded",
            "private_extra": "do not expose",
        },
        {"h": 2, "text": "Mean arterial pressure result: low"},
        {"h": 3, "text": "Vasopressor infusion running"},
        {"h": 4, "text": "Fourth recorded event"},
    ]
    publish(tmp_path / "context.json", context)
    model = Fake([tc("get_room", {"room": 7}), text("This explains the risk")])
    try:
        with running_board(
            tmp_path, model.url, context_path=tmp_path / "context.json"
        ) as base:
            _, reply = request(
                base, "/api/ask", {"question": "Room 7 recent context?", "room": 7}
            )
            assert "Recent recorded context" in reply["answer"]
            assert "1 h before cut: Invasive ventilation recorded" in reply["answer"]
            assert "Fourth recorded event" not in reply["answer"]
            assert "explains" not in reply["answer"]
            assert "private_extra" not in json.dumps(model.requests)
    finally:
        model.close()


def test_combined_tool_results_stay_bounded_and_keep_json_errors(tmp_path):
    context = synthetic_context()
    for room in context["rooms"]["rooms"][:3]:
        room["past_12h"] = [{"h": 1, "text": "synthetic context " * 250}]
    publish(tmp_path / "context.json", context)
    calls = [tc("get_room", {"room": n}, i=n)["tool_calls"][0] for n in (1, 2, 3)]
    model = Fake([{"content": None, "tool_calls": calls}, text("done")])
    try:
        with running_board(
            tmp_path, model.url, context_path=tmp_path / "context.json"
        ) as base:
            _, reply = request(
                base, "/api/ask", {"question": "Compare rooms 1, 2 and 3"}
            )
            messages = tool_msgs(model)
            assert len(messages) == 3
            assert sum(len(message["content"]) for message in messages) <= 12000
            results = [
                json.loads(message["content"])["tool_result"] for message in messages
            ]
            assert "combined evidence" in results[-1]["error"]
            assert "Room 1" in reply["answer"]
            assert "Room 3" not in reply["answer"]
    finally:
        model.close()


def test_model_down_fallback_uses_only_configured_context(tmp_path):
    context = synthetic_context()
    publish(tmp_path / "context.json", context)
    (tmp_path / "forecast.json").write_text(
        json.dumps({"resources": {"ventilator": {"p10": 8, "p50": 9, "p90": 10}}})
    )
    with running_board(tmp_path, context_path=tmp_path / "context.json") as base:
        _, reply = request(base, "/api/ask", {"question": "Ventilator starts?"})
        assert "2 ventilator starts (80% range 1 to 3)" in reply["answer"]
        assert "9 ventilator starts" not in reply["answer"]
        assert reply["snapshot_id"] == context["snapshot_id"]


@pytest.mark.parametrize("context_state", ["absent-mode", "missing-file", "open-demo"])
def test_real_data_mode_refuses_missing_or_demo_context_without_model_calls(
    tmp_path, context_state
):
    context_path = None if context_state == "absent-mode" else tmp_path / "context.json"
    if context_state == "open-demo":
        publish(context_path, synthetic_context())
    (tmp_path / "forecast.json").write_text(
        json.dumps({"resources": {"ventilator": {"p10": 8, "p50": 9, "p90": 10}}})
    )
    model = Fake([tc("get_unit_forecast")])
    try:
        with running_board(
            tmp_path, model.url, context_path=context_path, require_real_data=True
        ) as base:
            for path in ("/api/context", "/api/forecast", "/api/rooms"):
                code, result = request(base, path)
                assert code == 503
                assert result["available"] is False
            code, reply = request(base, "/api/ask", {"question": "Ventilator starts?"})
            assert code == 200
            assert "unavailable" in reply["answer"].lower()
            assert "MIMIC-IV" in reply["answer"]
            assert "9 ventilator starts" not in reply["answer"]
            assert model.requests == []
    finally:
        model.close()


def test_real_data_guard_accepts_real_labelled_synthetic_snapshot_for_same_rooms(
    tmp_path,
):
    """The source label is exercised; every value remains a synthetic test fixture."""
    context = synthetic_context(source_kind="mimic-iv")
    context_path = tmp_path / "context.json"
    publish(context_path, context)
    calls = (
        tc("get_room", {"room": 7})["tool_calls"]
        + tc("get_unit_forecast", {"prediction": "ventilator"}, i=2)["tool_calls"]
    )
    model = Fake([{"content": None, "tool_calls": calls}, text("done")])
    try:
        with running_board(
            tmp_path, model.url, context_path=context_path, require_real_data=True
        ) as base:
            code, envelope = request(base, "/api/context")
            assert code == 200
            assert envelope["source"]["kind"] == "mimic-iv"
            assert len(envelope["rooms"]["rooms"]) == 25
            code, reply = request(
                base,
                "/api/ask",
                {"question": "Compare room 7 and unit ventilator starts", "room": 7},
            )
            assert code == 200
            assert reply["source"] == context["source"]
            assert reply["snapshot_id"] == context["snapshot_id"]
            assert reply["cohort_id"] == context["cohort_id"]
            assert "Room 7" in reply["answer"]
            assert "2 ventilator starts (80% range 1 to 3)" in reply["answer"]
            for message in tool_msgs(model):
                evidence = json.loads(message["content"])["tool_result"]
                assert evidence["snapshot_id"] == context["snapshot_id"]
                assert evidence["cohort_id"] == context["cohort_id"]
            assert (
                request(base, "/api/forecast")[1]["snapshot_id"] == reply["snapshot_id"]
            )
            assert request(base, "/api/rooms")[1]["cohort_id"] == reply["cohort_id"]
            calls_before = len(model.requests)
            publish(context_path, synthetic_context())
            assert request(base, "/api/context")[0] == 503
            _, refused = request(base, "/api/ask", {"question": "Same forecast again?"})
            assert "unavailable" in refused["answer"].lower()
            assert len(model.requests) == calls_before
    finally:
        model.close()


def pending_context():
    context = synthetic_context(source_kind="mimic-iv")
    context["forecast_state"] = "pending-model"
    for view in ("forecast", "rooms"):
        context[view]["forecast_state"] = "pending-model"
    no_estimate = {
        "available": False,
        "p10": None,
        "p50": None,
        "p90": None,
        "expected": None,
    }
    forecast = context["forecast"]
    forecast["resources"] = {
        key: dict(no_estimate)
        for key in ("ventilator", "vasopressor", "crrt", "death", "icu_departure")
    }
    forecast["life_support"] = {
        "now_patients": None,
        "now_known_patients": 1,
        "now_unknown_patients": 1,
        "now_by": {"imv": None, "vasopressor": None, "crrt": 0},
        "now_known_by": {"imv": 1, "vasopressor": 0, "crrt": 0},
        "now_unknown_by": {"imv": 1, "vasopressor": 1, "crrt": 0},
        "expected_new_patients": dict(no_estimate),
        "expected_by": {
            key: dict(no_estimate) for key in ("imv", "vasopressor", "crrt")
        },
    }
    forecast["yardstick"] = None
    forecast["check_first"] = []
    for room in context["rooms"]["rooms"]:
        room.update(
            on_now={"imv": False, "vasopressor": False, "crrt": False},
            p={
                key: None
                for key in ("imv", "vasopressor", "crrt", "death", "icu_departure")
            },
            any_life_support=None,
            level=None,
            out=False,
        )
    context["rooms"]["rooms"][6]["on_now"]["imv"] = True
    context["rooms"]["rooms"][6]["on_now"]["vasopressor"] = None
    context["rooms"]["rooms"][7]["on_now"]["imv"] = None
    context["provenance"].update(
        model=None, weights_sha256=None, scoring="pending-model", unit_counts=None
    )
    return context


def test_pending_model_preserves_real_labelled_now_and_has_no_forecast_estimates(
    tmp_path,
):
    """Only the metadata is real-labelled; no clinical rows are used in this test."""
    context = pending_context()
    publish(tmp_path / "context.json", context)
    calls = (
        tc("get_room", {"room": 7})["tool_calls"]
        + tc("get_life_support", i=2)["tool_calls"]
        + tc("get_unit_forecast", i=3)["tool_calls"]
    )
    model = Fake(
        [{"content": None, "tool_calls": calls}, text("No starts are expected")]
    )
    try:
        with running_board(
            tmp_path,
            model.url,
            context_path=tmp_path / "context.json",
            require_real_data=True,
        ) as base:
            assert request(base, "/api/context")[0] == 200
            assert request(base, "/api/rooms")[1]["rooms"][6]["on_now"]["imv"] is True
            forecast = request(base, "/api/forecast")[1]
            assert all(row["p50"] is None for row in forecast["resources"].values())
            _, reply = request(
                base,
                "/api/ask",
                {"question": "Room 7 and unit support now and next?", "room": 7},
            )
            assert reply["forecast_state"] == "pending-model"
            assert "imv on" in reply["answer"]
            assert "vasopressor unknown" in reply["answer"]
            assert "at least 1" in reply["answer"]
            assert "No estimate" in reply["answer"]
            assert "pending" in reply["answer"].lower()
            assert "0 ventilator starts" not in reply["answer"]
            assert "No starts are expected" not in reply["answer"]
            assert reply["snapshot_id"] == context["snapshot_id"]
    finally:
        model.close()


class RenderedElements(HTMLParser):
    """Read rendered DOM text, without inspecting JavaScript internals."""

    def __init__(self, html):
        super().__init__()
        self.stack, self.text, self.tiles = [], {}, {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if (
            tag == "button"
            and "data-room" in attrs
            and any(i == "grid" for _, i in self.stack)
        ):
            self.tiles[int(attrs["data-room"])] = attrs
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append((tag, attrs.get("id")))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                self.stack = self.stack[:index]
                return

    def handle_data(self, data):
        for _, identifier in self.stack:
            if identifier:
                self.text[identifier] = self.text.get(identifier, "") + data


def rendered_dom(base, tmp_path, fragment):
    chrome = pathlib.Path(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    )
    if not chrome.exists():
        pytest.skip(
            "Local Chrome unavailable; rendered DOM check requires an installed browser"
        )
    result = subprocess.run(
        [
            str(chrome),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--disable-extensions",
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
            f"--user-data-dir={tmp_path / 'chrome-profile'}",
            "--virtual-time-budget=1500",
            "--dump-dom",
            base + "/#" + fragment,
        ],
        text=True,
        capture_output=True,
        timeout=25,
    )
    assert result.returncode == 0, "Synthetic local rendered-DOM process failed"
    return RenderedElements(result.stdout)


def test_picture_board_keeps_known_now_when_future_estimates_are_unavailable(tmp_path):
    context = pending_context()
    # Legacy ready envelopes may also have unavailable probe rows. This separates
    # UI behavior from the pending publisher contract exercised above.
    ready = synthetic_context(source_kind="mimic-iv")
    ready["forecast"]["life_support"] = context["forecast"]["life_support"]
    ready["forecast"]["resources"] = context["forecast"]["resources"]
    ready["rooms"]["rooms"] = context["rooms"]["rooms"]
    publish(tmp_path / "context.json", ready)
    paths = []
    with running_board(
        tmp_path,
        context_path=tmp_path / "context.json",
        require_real_data=True,
        request_paths=paths,
    ) as base:
        dom = rendered_dom(base, tmp_path, "view=strain&when=now")
        assert "At least 1" in dom.text["strainbody"]
        assert "unknown" in dom.text["strainbody"].lower()
        assert "No forecast yet" not in dom.text["strainbody"]
        assert dom.tiles[7]["data-state"] == "now-1"
        assert dom.tiles[8]["data-state"] == "now-unknown"
        assert paths.count("/api/context") == 1
        assert "/api/forecast" not in paths
        assert "/api/rooms" not in paths


def test_ended_slot_remains_visible_without_a_current_patient_or_forecast(tmp_path):
    context = pending_context()
    for room in context["rooms"]["rooms"]:
        room["present"] = True
    ended = context["rooms"]["rooms"][-1]
    ended.update(present=False, age=None, sex=None, on_life_support=None, past_12h=[])
    ended["on_now"] = {key: None for key in ("imv", "vasopressor", "crrt")}
    context["forecast"]["beds"] = 24
    context["rooms"]["dropped"] = 1
    publish(tmp_path / "context.json", context)
    model = Fake([tc("get_room", {"room": 25}), text("Patient 25 is steady")])
    try:
        with running_board(
            tmp_path,
            model.url,
            context_path=tmp_path / "context.json",
            require_real_data=True,
        ) as base:
            dom = rendered_dom(base, tmp_path, "view=beds&when=next&room=25")
            assert len(dom.tiles) == 25
            assert dom.tiles[25]["data-state"] == "ended"
            # The latest approved UI opens pending-model snapshots on Now.
            assert dom.tiles[7]["data-state"] == "now-1"
            assert dom.tiles[8]["data-state"] == "now-unknown"
            assert "not in the icu at this replay time" in dom.text["rv-risk-h"].lower()
            assert "No current patient or forecast" in dom.text["rv-risks"]
            assert "No estimate" in dom.text["alltasks"]
            assert "Steady" not in dom.text["grid"]
            _, reply = request(
                base, "/api/ask", {"question": "Room 25 now?", "room": 25}
            )
            assert "not in the ICU at this replay time" in reply["answer"]
            assert "steady" not in reply["answer"]
    finally:
        model.close()


# ---- CodeRabbit PR #16: the real-ward boundary (docs/DECISIONS.md D6, D19) ----
# Every value below is a synthetic fixture; only the source label says "mimic-iv".


def _real_labelled_context():
    context = synthetic_context(source_kind="mimic-iv")
    context["forecast"]["check_first"] = [
        {"room": 7, "any_life_support": 0.62, "level": "high"}
    ]
    for entry in context["rooms"]["rooms"]:
        entry.update(
            updated_at=context["published_at"],
            cut_time=context["published_at"],
            window=context["forecast"]["window"],
            name={"display": "Ada Example", "fictional": True},
        )
    return context


def test_real_ward_responses_are_counts_only_unless_started_in_real_ward_mode(tmp_path):
    context = _real_labelled_context()
    publish(tmp_path / "context.json", context)
    with running_board(tmp_path, context_path=tmp_path / "context.json") as base:
        code, rooms = request(base, "/api/rooms")
        assert code == 200 and rooms["rooms"] == [] and rooms["counts_only"] is True
        assert rooms["ward"]["source"] == "mimic-iv"
        code, envelope = request(base, "/api/context")
        assert code == 200 and envelope["rooms"]["rooms"] == []
        assert envelope["forecast"]["check_first"] == []
        assert envelope["forecast"]["resources"] == context["forecast"]["resources"]
        code, forecast = request(base, "/api/forecast")
        assert forecast["resources"] == context["forecast"]["resources"]
        assert forecast["check_first"] == []
    for mode in ({"real_ward": True}, {"require_real_data": True}):
        with running_board(
            tmp_path, context_path=tmp_path / "context.json", **mode
        ) as base:
            assert request(base, "/api/rooms")[1] == context["rooms"]
            assert request(base, "/api/context")[1] == context
    # the files without a context (rooms.json next to forecast.json): the same rule
    (tmp_path / "forecast.json").write_text(json.dumps(context["forecast"]))
    (tmp_path / "rooms.json").write_text(json.dumps(context["rooms"]))
    with running_board(tmp_path) as base:
        rooms = request(base, "/api/rooms")[1]
        assert rooms["rooms"] == [] and rooms["counts_only"] is True
        forecast = request(base, "/api/forecast")[1]
        assert forecast["resources"] == context["forecast"]["resources"]
        assert forecast["check_first"] == []
    with running_board(tmp_path, real_ward=True) as base:
        assert request(base, "/api/rooms")[1] == context["rooms"]
        assert request(base, "/api/forecast")[1] == context["forecast"]
    # the open demo ward is never restricted
    demo = synthetic_context()
    (tmp_path / "forecast.json").write_text(json.dumps(demo["forecast"]))
    (tmp_path / "rooms.json").write_text(json.dumps(demo["rooms"]))
    with running_board(tmp_path) as base:
        assert len(request(base, "/api/rooms")[1]["rooms"]) == 25


def test_room_chat_refuses_a_real_ward_unless_started_in_real_ward_mode(tmp_path):
    context = _real_labelled_context()
    publish(tmp_path / "context.json", context)
    calls = (
        tc("get_room", {"room": 7})["tool_calls"]
        + tc("get_unit_forecast", {"prediction": "ventilator"}, i=2)["tool_calls"]
    )
    model = Fake([{"content": None, "tool_calls": calls}, text("done")])
    try:
        with running_board(
            tmp_path, model.url, context_path=tmp_path / "context.json"
        ) as base:
            _, reply = request(
                base, "/api/ask", {"question": "Room 7 and the unit?", "room": 7}
            )
        room, unit = (json.loads(m["content"])["tool_result"] for m in tool_msgs(model))
        assert room["counts_only"] is True and "room" not in room
        assert unit["resources"] == context["forecast"]["resources"]
        assert unit["check_first"] == []  # room numbers with a chance are room data
        sent = json.dumps(model.requests)
        assert "Ada Example" not in sent and '"on_now"' not in sent
        assert "30%" not in reply["answer"] and "Ada" not in reply["answer"]
        assert "counts only" in reply["answer"]
        assert "2 ventilator starts (80% range 1 to 3)" in reply["answer"]
    finally:
        model.close()


def test_real_ward_room_context_reaches_the_model_only_for_the_room_asked(
    tmp_path, caplog
):
    context = _real_labelled_context()
    publish(tmp_path / "context.json", context)
    calls = (
        tc("get_room", {"room": 7})["tool_calls"]
        + tc("get_room", {"room": 9}, i=2)["tool_calls"]
    )
    model = Fake([{"content": None, "tool_calls": calls}, text("done")])
    try:
        with running_board(
            tmp_path, model.url, context_path=tmp_path / "context.json", real_ward=True
        ) as base:
            with caplog.at_level("INFO"):
                _, reply = request(
                    base, "/api/ask", {"question": "How is room 7 doing today?"}
                )
        asked, other = (
            json.loads(m["content"])["tool_result"] for m in tool_msgs(model)
        )
        assert asked["room"]["room"] == 7 and asked["room"]["p"] == {"imv": 0.3}
        assert asked["room"]["name"] == {"display": "Ada Example", "fictional": True}
        # no clock fields or dates in what the model reads for a real ward
        assert not {"updated_at", "cut_time", "window"} & set(asked["room"])
        assert "made_at" not in asked and "2026-" not in json.dumps(asked)
        assert "error" in other and "room" not in other  # room 9 was not asked about
        assert "Room 7 (Ada Example)" in reply["answer"]
        assert "Room 9" not in reply["answer"]
        assert "room 7 doing" not in caplog.text and "Ada" not in caplog.text
        assert "30%" not in caplog.text
    finally:
        model.close()


def test_board_real_ward_flag_and_workflows_agree():
    assert board.parse_args(["--forecast", "f.json"]).real_ward is False
    assert board.parse_args(["--forecast", "f.json", "--real-ward"]).real_ward is True
    from app import dispatcher

    twin = (pathlib.Path(board.__file__).parents[1] / "fuzzball/t7-twin.fz").read_text()
    line = next(x for x in twin.splitlines() if "--dispatcher http://dispatcher" in x)
    assert "--real-ward" not in dispatcher.render_ward(line)  # open demo: no flag
    assert "--real-ward" in dispatcher.render_ward(line, real_ward=True)


def test_capacity_follows_the_context_forecast_in_context_mode(tmp_path):
    """CodeRabbit PR 20 (third review): with --context the forecast the page shows
    is the context's. Free machines come from it (5 ventilated, 8 ventilators: 3
    free), never from a standalone forecast.json that says 1."""
    context = synthetic_context()
    now_by = {"imv": 5, "vasopressor": 1, "crrt": 0}
    context["forecast"]["life_support"] = {"now_patients": 6, "now_by": now_by}
    publish(tmp_path / "context.json", context)
    stale = {"life_support": {"now_by": {**now_by, "imv": 1}}}
    (tmp_path / "forecast.json").write_text(json.dumps(stale))
    (tmp_path / "capacity.json").write_text(json.dumps({"vents_total": 8}))
    with running_board(tmp_path, context_path=tmp_path / "context.json") as base:
        assert request(base, "/api/capacity")[1]["vents_free"] == 3
        code, saved = request(
            base, "/api/capacity", {"role": "ICU nurse", "vents_total": 9}
        )
        assert code == 200 and saved["capacity"]["vents_free"] == 4
    # the context is gone: nothing says what is in use, so nothing is free
    (tmp_path / "context.json").unlink()
    with running_board(tmp_path, context_path=tmp_path / "context.json") as base:
        assert request(base, "/api/capacity")[1]["vents_free"] is None

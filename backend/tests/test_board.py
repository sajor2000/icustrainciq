# ruff: noqa: E501
"""Board endpoints: static page per request, forecast/rooms/runs, scoped rerun, capacity."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app import board
from app import dispatcher as dsp
from tests.test_dispatcher import FakeCli


def serve(handler):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


POST_HEADERS = {"Content-Type": "application/json", "X-Lookahead": "1"}


def call(base, path, body=None, headers=None):
    req = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers={} if body is None else {**POST_HEADERS, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def jcall(base, path, body=None):
    code, data = call(base, path, body)
    return code, json.loads(data)


@pytest.fixture
def stack(tmp_path):
    """board + a real dispatcher (fake CLI) + a static page, all on loopback"""
    fake = FakeCli(tmp_path)
    disp, dbase = serve(dsp.make_handler(fake))
    page = tmp_path / "index.html"
    page.write_text("<html>v1</html>")
    fc = tmp_path / "forecast.json"
    fc.write_text(
        json.dumps(
            {
                "made_at": "2026-11-14T07:00:00-06:00",
                "resources": {"ventilator": {"p10": 1, "p50": 2, "p90": 3}},
            }
        )
    )
    web, base = serve(board.make_handler(fc, "http://127.0.0.1:9", dbase, page))
    yield base, tmp_path, fake, page
    web.shutdown()
    disp.shutdown()


def test_page_is_read_from_disk_on_every_request(stack):
    base, tmp, fake, page = stack
    assert call(base, "/") == (200, b"<html>v1</html>")
    page.write_text("<html>v2</html>")
    assert call(base, "/")[1] == b"<html>v2</html>"
    page.unlink()
    assert call(base, "/")[0] == 503


def test_the_shipped_placeholder_page_exists():
    assert b"<html" in board.STATIC.read_bytes()


def test_forecast_rooms_and_pending_defaults(stack):
    base, tmp, fake, page = stack
    assert jcall(base, "/api/forecast")[1]["resources"]["ventilator"]["p50"] == 2
    assert jcall(base, "/api/rooms") == (200, {"rooms": [], "note": "pending run"})
    (tmp / "rooms.json").write_text(json.dumps({"rooms": [{"room": 1}]}))
    assert jcall(base, "/api/rooms")[1]["rooms"] == [{"room": 1}]
    (tmp / "forecast.json").unlink()
    assert "07:00" in jcall(base, "/api/forecast")[1]["note"]


def test_rerun_scopes_go_through_the_dispatcher(stack):
    base, tmp, fake, page = stack
    c, r = jcall(base, "/api/rerun", {"role": "ICU nurse", "scope": "room", "room": 12})
    assert r["started"] and r["room"] == 12
    c, r = jcall(base, "/api/rerun", {"role": "ICU nurse", "scope": "unit"})
    assert r["started"] and r["scope"] == "unit" and r["demo_clock_hours"] == 4.5
    c, r = jcall(base, "/api/rerun", {"role": "ICU nurse", "scope": "room", "room": 12})
    assert r["started"] is False and "Room 12 updated" in r["reason"]
    c, r = jcall(base, "/api/rerun", {"role": "ICU nurse"})  # default scope unit
    assert r["started"] is False and r["reason"].startswith("Updated 0 minutes ago")
    assert jcall(base, "/api/rerun", {"role": "someone"})[1]["started"] is False


def test_runs_shows_scope_room_clock_running_and_next_0700(stack):
    base, tmp, fake, page = stack
    jcall(base, "/api/rerun", {"role": "pharmacy", "scope": "room", "room": 4})
    fake.running = [{"name": "t7-forecast-room4-1114-1130", "status": "STARTED"}]
    c, runs = jcall(base, "/api/runs")
    assert runs["next_scheduled"].endswith("T07:00") and runs["updating"] is True
    assert runs["last"]["room"]["room"] == 4 and runs["last"]["room"]["scope"] == "room"
    assert runs["last"]["room"]["demo_clock_hours"] == 4.5
    assert runs["demo_clock_label"] == "Ward clock 11:30 (07:00 + 4.5 h)"
    assert runs["recent"][-1]["trigger"] == "pharmacy"


def test_runs_when_the_dispatcher_is_down(tmp_path):
    fc = tmp_path / "forecast.json"
    web, base = serve(
        board.make_handler(fc, "http://127.0.0.1:9", "http://127.0.0.1:9")
    )
    try:
        c, r = jcall(base, "/api/runs")
        assert c == 200 and r["available"] is False and "unreachable" in r["reason"]
    finally:
        web.shutdown()


def test_capacity_validates_saves_and_logs_role_only(stack, caplog):
    base, tmp, fake, page = stack
    assert jcall(base, "/api/capacity")[1]["vents_free"] is None
    good = {"life_support_patients": 12, "vents_free": 3, "role": "ICU nurse"}
    with caplog.at_level("INFO", logger="board"):
        c, r = jcall(base, "/api/capacity", good)
    assert c == 200 and r["ok"] and r["capacity"]["vents_free"] == 3
    saved = json.loads((tmp / "capacity.json").read_text())
    assert saved["life_support_patients"] == 12 and saved["vents_free"] == 3
    assert jcall(base, "/api/capacity")[1]["life_support_patients"] == 12
    msg = " ".join(x.getMessage() for x in caplog.records)
    assert "role=ICU nurse" in msg
    assert (
        "life_support" not in msg
        and "vents" not in msg
        and "12" not in msg.split("role=")[1]
    )
    assert [p.name for p in tmp.iterdir() if p.name.startswith("capacity")] == [
        "capacity.json"
    ]
    for bad in (
        {**good, "vents_free": 51},
        {**good, "vents_free": -1},
        {**good, "life_support_patients": 3.5},
        {**good, "life_support_patients": "7"},
        {**good, "vents_free": True},
        {**good, "role": "visitor"},
        {"role": "ICU nurse"},
    ):
        c, r = jcall(base, "/api/capacity", bad)
        assert c == 400 and r["ok"] is False
    assert (
        json.loads((tmp / "capacity.json").read_text()) == saved
    )  # bad input changed nothing
    assert (
        jcall(
            base,
            "/api/capacity",
            {**good, "vents_free": 0, "life_support_patients": 50},
        )[0]
        == 200
    )


def test_ask_degrades_without_nemotron_and_update_asks_still_work(stack):
    base, tmp, fake, page = stack
    c, r = jcall(base, "/api/ask", {"question": "vents?", "role": "ICU nurse"})
    assert r["answer"] == board.NO_CHAT  # no exception name, no host
    c, r = jcall(
        base, "/api/ask", {"question": "please update room 12", "role": "ICU physician"}
    )
    assert (
        r["answer"].startswith("Started t7-forecast-room12-")
        and "room 12" in r["answer"]
    )
    c, r = jcall(
        base, "/api/ask", {"question": "update the unit", "role": "ICU physician"}
    )
    assert (
        r["answer"].startswith("Started t7-forecast-1114") and "the unit" in r["answer"]
    )
    c, r = jcall(
        base, "/api/ask", {"question": "update the unit", "role": "ICU physician"}
    )
    assert (
        r["answer"]
        == "Forecast not started: Updated 0 minutes ago. You can update again at 11:50."
    )
    assert r["made_at"] == "2026-11-14T07:00:00-06:00"


def test_ask_without_a_chat_model_is_one_plain_line(tmp_path, caplog):
    """t7-twin-nochat: --nemotron "" (and a model that is down) never leak an error"""
    fake = FakeCli(tmp_path)
    disp, dbase = serve(dsp.make_handler(fake))
    fc = tmp_path / "forecast.json"
    fc.write_text(json.dumps({"made_at": "2026-11-14T07:00:00-06:00"}))
    assert board.parse_args(["--forecast", "x", "--nemotron", ""]).nemotron == ""
    for endpoint in ("", "http://127.0.0.1:9", "not a url"):
        web, base = serve(board.make_handler(fc, endpoint, dbase))
        try:
            with caplog.at_level("INFO", logger="board"):
                c, r = jcall(
                    base, "/api/ask", {"question": "vents today?", "role": "ICU nurse"}
                )
            assert c == 200 and r["answer"] == board.NO_CHAT, endpoint
            for leak in ("Error", "Exception", "urlopen", "Traceback", "127.0.0.1"):
                assert leak not in json.dumps(r), (endpoint, leak)
            c, r = jcall(
                base, "/api/ask", {"question": "update room 3", "role": "ICU nurse"}
            )
            assert r["answer"].startswith(
                ("Started t7-forecast-room3-", "Forecast not")
            )
            assert jcall(base, "/api/forecast")[0] == 200
        finally:
            web.shutdown()
    assert "vents today" not in " ".join(x.getMessage() for x in caplog.records)
    disp.shutdown()


def test_capacity_vents_free_is_optional(stack):
    base, tmp, fake, page = stack
    c, r = jcall(
        base, "/api/capacity", {"life_support_patients": 9, "role": "ICU nurse"}
    )
    assert c == 200 and r["ok"] and r["capacity"]["vents_free"] is None
    saved = json.loads((tmp / "capacity.json").read_text())
    assert (
        saved["set_by_role"] == "ICU nurse" and saved["set_at"]
    )  # keys aggregate.py reads


# ---- review fixes (2026-11-14): CSRF rule, headers, strict bodies, HEAD ---------------------

import http.client  # noqa: E402

REFUSED = {"ok": False, "reason": "request refused"}


def raw_post(base, path, body: bytes, headers: dict):
    host, port = base.removeprefix("http://").split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=5)
    c.putrequest("POST", path)
    for k, v in headers.items():
        c.putheader(k, v)
    c.endheaders(body)
    r = c.getresponse()
    return r.status, r.read()


def test_post_needs_json_content_type_and_the_lookahead_header(stack):
    base, *_ = stack
    body = {"role": "ICU nurse", "life_support_patients": 5}
    ok_h = dict(POST_HEADERS)
    assert call(base, "/api/capacity", body)[0] == 200
    for bad in (
        {"X-Lookahead": "1", "Content-Type": "text/plain"},
        {"X-Lookahead": "1", "Content-Type": "application/x-www-form-urlencoded"},
        {"Content-Type": "application/json"},
        {"Content-Type": "application/json", "X-Lookahead": "0"},
    ):
        code, data = raw_post(
            base,
            "/api/capacity",
            json.dumps(body).encode(),
            {**bad, "Content-Length": str(len(json.dumps(body)))},
        )
        assert (code, json.loads(data)) == (403, REFUSED), bad
    assert ok_h  # silence: the accepted shape is POST_HEADERS


def test_origin_must_match_the_host_when_present(stack):
    base, *_ = stack
    body = {"role": "ICU nurse", "life_support_patients": 5}
    host = base.removeprefix("http://")
    assert call(base, "/api/capacity", body, {"Origin": f"http://{host}"})[0] == 200
    for origin in (
        "http://evil.example",
        f"http://127.0.0.1:{int(host.split(':')[1]) + 1}",
        "null",
    ):
        code, data = call(base, "/api/capacity", body, {"Origin": origin})
        assert (code, json.loads(data)) == (403, REFUSED), origin
    for path in ("/api/rerun", "/api/ask"):  # every POST route is covered
        code, data = call(
            base,
            path,
            {"role": "ICU nurse", "question": "x"},
            {"Origin": "http://evil.example"},
        )
        assert code == 403


def test_origin_behind_the_proxy_compares_the_host_name_only(tmp_path):
    fc = tmp_path / "forecast.json"
    fc.write_text("{}")
    web, base = serve(
        board.make_handler(fc, "http://127.0.0.1:9", "", tmp_path / "i.html", True)
    )
    try:
        body = {"role": "ICU nurse", "life_support_patients": 5}
        hdr = {"Origin": "https://127.0.0.1", "Host": "127.0.0.1:8080"}
        assert call(base, "/api/capacity", body, hdr)[0] == 200
        assert (
            call(base, "/api/capacity", body, {"Origin": "https://evil.example"})[0]
            == 403
        )
    finally:
        web.shutdown()


def test_every_response_has_the_security_headers(stack):
    base, *_ = stack
    for path, body in (
        ("/", None),
        ("/nope", None),
        ("/api/forecast", None),
        ("/api/capacity", {"role": "ICU nurse", "life_support_patients": 1}),
        ("/api/capacity", {"role": "x"}),
    ):
        req = urllib.request.Request(
            base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={} if body is None else POST_HEADERS,
        )
        try:
            r = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            r = e
        h = r.headers
        assert (
            h["X-Frame-Options"] == "DENY" and h["X-Content-Type-Options"] == "nosniff"
        )
        csp = h["Content-Security-Policy"]
        assert csp == board.SECURITY_HEADERS["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp and "connect-src 'self'" in csp


def test_content_length_is_strict_and_the_cap_is_413(stack):
    base, *_ = stack
    h = {**POST_HEADERS}
    for bad in ("abc", "-5", "1e3", "", "0x10"):
        code, data = raw_post(base, "/api/capacity", b"", {**h, "Content-Length": bad})
        assert code == 400, bad
    code, data = raw_post(
        base, "/api/capacity", b"x" * 5000, {**h, "Content-Length": "5000"}
    )
    assert code == 413 and json.loads(data)["ok"] is False
    code, _ = raw_post(
        base, "/api/capacity", b"{not json", {**h, "Content-Length": "9"}
    )
    assert code == 400
    code, _ = raw_post(base, "/api/ask", b"[1]", {**h, "Content-Length": "3"})
    assert code == 400


def test_head_root_is_200_with_headers_and_no_body(stack):
    base, *_ = stack
    host, port = base.removeprefix("http://").split(":")
    c = http.client.HTTPConnection(host, int(port), timeout=5)
    c.request("HEAD", "/")
    r = c.getresponse()
    assert r.status == 200 and r.read() == b""
    assert (
        r.getheader("X-Frame-Options") == "DENY"
        and int(r.getheader("Content-Length")) > 0
    )


def test_chat_update_ask_over_fire_cases_do_not_start_a_run(stack):
    base, tmp, fake, page = stack
    code, out = jcall(
        base,
        "/api/ask",
        {"question": "Should we update the unit?", "role": "ICU nurse"},
    )
    assert code == 200 and fake.started == []

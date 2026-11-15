# ruff: noqa: E501  (usage lines read better unwrapped)
"""Unit bed board server and "Ask the board" (stdlib only; runs in python:3.12-slim).

Usage: python app/board.py --forecast /store/forecast.json --nemotron http://nemotron:8000 \
         --dispatcher http://dispatcher:9000 --port 8080

The page itself is `app/static/index.html`, read from disk on every request, so a new
page goes live without restarting the workflow. Everything else is JSON:

GET  /                 the page (503 note if the file is missing)
GET  /api/forecast     forecast.json (unit counts only), or {"resources": {}, "note": ...};
                       the file is sent whole, so "forecast_state" ("ready" | "pending-model") passes through
       --host 127.0.0.1 binds loopback only (a laptop run on real patients); default 0.0.0.0
GET  /api/rooms        rooms.json next to the forecast (stage ward only)
GET  /api/runs         dispatcher status: next 07:00, running update, last per scope, demo clock
GET  /api/capacity     {"life_support_patients", "vents_total", "vents_free", "crrt_total", "crrt_free",
                       "updated_at", "set_by_role"} (null = not set; free = total - on now)
POST /api/capacity     {"role", and any of "life_support_patients", "vents_total", "crrt_total",
                       "nurses_on_shift", "rt_on_shift": whole numbers 0..50} -> capacity.json (merged: a key left out keeps its saved value, null clears it)
POST /api/rerun        {"role", "scope": "unit" | "room", "room"?: 1..25} -> dispatcher
POST /api/ask          {"question","role","room?","seen_made_at?"} -> {"answer","trace"?,"made_at"}

Every POST must send Content-Type: application/json AND the header `X-Lookahead: 1`; an Origin
header, when present, must match the request Host (behind the Fuzzball proxy, `--behind-proxy`,
the host name only). Anything else is refused: 403 {"ok": false, "reason": "request refused"}.
Content-Length must be a whole number from 0 to 4096 (400 otherwise, 413 over the cap).
`role` is advisory: there is no login, it labels the log and the answer, it is not authorization.
Every response carries X-Frame-Options, Content-Security-Policy and X-Content-Type-Options.
"""

import argparse
import datetime as dt
import json
import logging
import os
import pathlib
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from app import capacity as capacity_mod
    from app.chat_agent import (
        ROLES,
        ChatAgent,
        ModelDown,
        ToolsUnsupported,
        filter_answer,
        parse_update_ask,
        update_answer,
        updated_line,
    )
except ImportError:  # run as `python app/board.py`
    import capacity as capacity_mod
    from chat_agent import (
        ROLES,
        ChatAgent,
        ModelDown,
        ToolsUnsupported,
        filter_answer,
        parse_update_ask,
        update_answer,
        updated_line,
    )

log = logging.getLogger("board")
STATIC = pathlib.Path(__file__).with_name("static") / "index.html"
CAPACITY_MAX = capacity_mod.CAPACITY_MAX
BODY_CAP = 4096
SOCKET_TIMEOUT_S = 10  # a slow or stalled client cannot hold a handler thread
REFUSED = {"ok": False, "reason": "request refused"}
SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; frame-ancestors 'none'; connect-src 'self'"
    ),
}

# single-shot fallback when vLLM has no tool calling (the agent in chat_agent.py is the normal path)
SYSTEM = (
    "You are Lookahead, the assistant on an ICU board for nurses, physicians, pharmacy, respiratory "
    "therapy and the bed manager. Answer only from the JSON forecast you are given: the five "
    "predictions (leaving the ICU, invasive ventilation start, vasopressor start, CRRT start, "
    "death) for the next 24 h, 07:00 to 07:00, as unit counts with an 80% range, plus the "
    "life-support count (IMV, vasopressor or CRRT). Quote the median then the 80% range, in one to "
    "three plain sentences, with no disclaimers or notes about the model. Never give treatment "
    "advice and never name or identify a patient. If the forecast cannot answer, say: That's "
    "outside this forecast. I can tell you what the unit is likely to need in the next 24 hours."
)


def _int_in_range(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= CAPACITY_MAX


def make_handler(
    forecast_path: pathlib.Path,
    nemotron: str,
    dispatcher: str = "",
    static_path: pathlib.Path = STATIC,
    behind_proxy: bool = False,
):
    rooms_path = forecast_path.with_name("rooms.json")
    capacity_path = forecast_path.with_name("capacity.json")
    cap_lock = threading.Lock()

    def load():
        try:
            return json.loads(forecast_path.read_text())
        except (OSError, ValueError):
            return {
                "resources": {},
                "note": "no forecast yet: the 07:00 run has not finished",
            }

    def call_dispatcher(path: str, body: dict | None = None) -> dict:
        """the forecast dispatcher service (app/dispatcher.py) inside the same workflow"""
        if not dispatcher:
            return {"started": False, "reason": "no dispatcher configured"}
        req = urllib.request.Request(
            f"{dispatcher}{path}",
            data=None if body is None else json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return json.load(e)
            except ValueError:
                return {"started": False, "reason": f"dispatcher error ({e.code})"}
        except Exception as e:
            return {
                "started": False,
                "reason": f"dispatcher unreachable ({type(e).__name__})",
            }

    agent = ChatAgent(
        nemotron,
        forecast_path,
        rooms_path,
        capacity_path,
        lambda path, body=None: call_dispatcher(path, body),
    )

    def ask(question: str) -> str:
        body = {
            "model": "nemotron",
            "max_tokens": 300,
            "temperature": 0.2,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": f"Forecast: {json.dumps(load())}\nQuestion: {question[:500]}",
                },
            ],
        }
        req = urllib.request.Request(
            f"{nemotron}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return filter_answer(json.load(r)["choices"][0]["message"]["content"])

    def read_capacity() -> dict:
        try:
            cap = json.loads(capacity_path.read_text())
        except (OSError, ValueError):
            cap = {}
        cap = cap if isinstance(cap, dict) else {}
        return {
            **capacity_mod.view(cap, load()),
            "updated_at": cap.get("updated_at"),
            "set_by_role": cap.get("set_by_role"),
        }

    def set_capacity(req: dict) -> tuple[int, dict]:
        role = str(req.get("role", ""))
        if role not in ROLES:
            return 400, {"ok": False, "reason": "choose your role"}
        keys = (
            "life_support_patients",
            "vents_total",
            "crrt_total",
            "nurses_on_shift",
            "rt_on_shift",
        )
        given = {k: req[k] for k in keys if k in req}  # absent = keep what is saved
        # each key is optional and null clears it; one of them must be there
        if not given or not all(v is None or _int_in_range(v) for v in given.values()):
            return 400, {
                "ok": False,
                "reason": f"enter whole numbers from 0 to {CAPACITY_MAX}",
            }
        cap = {
            **{k: None for k in keys},
            **given,  # as entered: free machines are derived when the file is read
            "updated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "set_by_role": role,  # role only, never a name (aggregate.py shows "set by")
        }
        cap["set_at"] = cap["updated_at"]  # the key app/aggregate.py reads
        tmp = capacity_path.with_name(capacity_path.name + ".tmp")
        try:
            with cap_lock:
                try:  # keys this request leaves out keep the saved value
                    prev = json.loads(capacity_path.read_text())
                except (OSError, ValueError):
                    prev = {}
                prev = prev if isinstance(prev, dict) else {}
                for k in keys:
                    if k not in given and _int_in_range(prev.get(k)):
                        cap[k] = prev[k]
                tmp.write_text(json.dumps(cap))
                os.replace(
                    tmp, capacity_path
                )  # whole file or nothing, like forecast.json
        except OSError as e:
            return 500, {"ok": False, "reason": f"could not save ({type(e).__name__})"}
        # privacy: time and role only; the numbers are not logged
        log.info("capacity set at=%s role=%s", cap["updated_at"], role)
        shown = {**cap, **capacity_mod.view(cap, load())}  # with the free machines
        return 200, {"ok": True, "capacity": shown}

    def origin_ok(origin: str | None, host: str | None, fwd_host: str | None) -> bool:
        """no Origin (non-browser client) passes; otherwise it must be this site"""
        if origin is None:
            return True
        try:
            u = urllib.parse.urlsplit(origin)
            o_host, o_port = (u.hostname or "").lower(), u.port
        except ValueError:
            return False
        if u.scheme not in ("http", "https") or not o_host:
            return False
        for h in (host, (fwd_host or "").split(",")[0].strip() or None):
            if not h:
                continue
            try:
                hu = urllib.parse.urlsplit("//" + h)
                h_host, h_port = (hu.hostname or "").lower(), hu.port
            except ValueError:
                continue
            if (
                behind_proxy
            ):  # the proxy terminates TLS and may rewrite the port: host only
                if o_host == h_host:
                    return True
            elif u.scheme == "http" and o_host == h_host:
                # scheme+host+port as the board sees them (it serves plain http)
                if (o_port or 80) == (h_port or 80):
                    return True
        return False

    class H(BaseHTTPRequestHandler):
        timeout = SOCKET_TIMEOUT_S
        _head = False

        def _send(self, code, ctype, data: bytes):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            if not self._head:
                self.wfile.write(data)

        def _json(self, code, obj):
            self._send(code, "application/json", json.dumps(obj).encode())

        def do_HEAD(self):
            self._head = True
            self.do_GET()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/forecast":
                return self._json(200, load())
            if path == "/api/rooms":  # stage ward only (D6)
                try:
                    data = rooms_path.read_bytes()
                except OSError:
                    data = b'{"rooms": [], "note": "pending run"}'
                return self._send(200, "application/json", data)
            if path == "/api/runs":
                st = call_dispatcher("/status")
                if "reason" in st and "next_scheduled" not in st:
                    st = {"available": False, "reason": st["reason"]}
                return self._json(200, st)
            if path == "/api/capacity":
                return self._json(200, read_capacity())
            if path in ("/", "/index.html"):
                try:  # read per request: a new page needs no restart
                    return self._send(
                        200, "text/html; charset=utf-8", static_path.read_bytes()
                    )
                except OSError:
                    return self._send(
                        503,
                        "text/plain; charset=utf-8",
                        b"The board page is not installed (app/static/index.html).",
                    )
            return self._send(404, "text/plain", b"not found")

        def _read_json_body(self):
            """(request dict, None) or (None, (status, reason)); strict Content-Length, capped"""
            raw = self.headers.get("Content-Length", "")
            if not (raw.isascii() and raw.isdigit()):
                return None, (400, "bad request")
            n = int(raw)
            if n > BODY_CAP:
                return None, (413, "request too large")
            try:
                data = self.rfile.read(n)
            except OSError:  # includes the socket timeout
                return None, (400, "bad request")
            if len(data) != n:
                return None, (400, "bad request")
            try:
                req = json.loads(data or b"{}")
            except ValueError:
                return None, (400, "bad request")
            if not isinstance(req, dict):
                return None, (400, "bad request")
            return req, None

        def do_POST(self):
            if self.path not in ("/api/ask", "/api/rerun", "/api/capacity"):
                return self._send(404, "text/plain", b"not found")
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if (
                ctype != "application/json"
                or self.headers.get("X-Lookahead") != "1"
                or not origin_ok(
                    self.headers.get("Origin"),
                    self.headers.get("Host"),
                    self.headers.get("X-Forwarded-Host") if behind_proxy else None,
                )
            ):
                return self._json(403, REFUSED)
            req, err = self._read_json_body()
            if err:
                return self._json(err[0], {"ok": False, "reason": err[1]})
            role = str(req.get("role", ""))
            if self.path == "/api/capacity":
                code, out = set_capacity(req)
                return self._json(code, out)
            if self.path == "/api/rerun":
                body = {"role": role, "scope": req.get("scope", "unit")}
                if "room" in req:
                    body["room"] = req["room"]
                return self._json(200, call_dispatcher("/run", body))
            q = str(req.get("question", ""))[
                :500
            ]  # the model and the ask parse see the same text
            room = req.get("room")
            room = (
                room if isinstance(room, int) and not isinstance(room, bool) else None
            )
            seen = req.get("seen_made_at")
            seen = seen if isinstance(seen, str) else None
            out: dict = {}
            if not q.strip():
                out = {"answer": "Ask a question about the forecast."}
            elif agent.available:
                try:
                    out = agent.ask(q, role, room, seen)
                except ToolsUnsupported:  # vLLM without tool calling: single-shot below
                    out = {}
                except ModelDown as e:
                    # an update request still works without the model (deterministic path below)
                    out = (
                        {}
                        if parse_update_ask(q, room)
                        else {"answer": f"Nemotron is not answering yet ({e})."}
                    )
            if not out:
                update = parse_update_ask(q, room)
                if (
                    update
                ):  # "update room 12" / "update the unit" in the chat starts a job
                    scope, r_no = update
                    body = {"role": role, "scope": scope}
                    if scope == "room":
                        body["room"] = r_no
                    answer = update_answer(
                        call_dispatcher("/run", body), scope, r_no, role
                    )
                else:
                    try:
                        answer = ask(q)
                    except (
                        Exception
                    ) as e:  # keep the board up if Nemotron is still loading
                        answer = f"Nemotron is not answering yet ({type(e).__name__})."
                made_at = load().get("made_at")
                if line := updated_line(seen, made_at):
                    answer = f"{line}\n{answer}"
                out = {"answer": answer, "made_at": made_at}
            self._json(200, out)

        def log_message(self, *a):  # no request logging: questions stay out of logs
            pass

    return H


def serve(a) -> ThreadingHTTPServer:
    """the bound server for parsed arguments (not yet serving)"""
    return ThreadingHTTPServer(
        (a.host, a.port),
        make_handler(a.forecast, a.nemotron, a.dispatcher, a.static, a.behind_proxy),
    )


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast", type=pathlib.Path, required=True)
    ap.add_argument("--nemotron", default="http://nemotron:8000")
    ap.add_argument("--dispatcher", default="", help="e.g. http://dispatcher:9000")
    ap.add_argument("--static", type=pathlib.Path, default=STATIC)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument(
        "--host",
        default="0.0.0.0",
        help="address to bind (default 0.0.0.0, as before: the Fuzzball service). "
        "A laptop run on real patients must pass 127.0.0.1",
    )
    ap.add_argument(
        "--behind-proxy",
        action="store_true",
        help="Fuzzball endpoint proxy in front: compare Origin and Host by host name only",
    )
    return ap.parse_args(argv)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    serve(parse_args()).serve_forever()


if __name__ == "__main__":
    main()

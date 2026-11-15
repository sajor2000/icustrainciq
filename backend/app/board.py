# ruff: noqa: E501  (usage lines read better unwrapped)
"""Unit bed board server and "Ask the board" (stdlib only; runs in python:3.12-slim).

Usage: python app/board.py --forecast /store/forecast.json --nemotron http://nemotron:8000 \
         --dispatcher http://dispatcher:9000 --port 8080

The page itself is `app/static/index.html`, read from disk on every request, so a new
page goes live without restarting the workflow. Everything else is JSON:

GET  /                 the page (503 note if the file is missing)
GET  /api/context      one validated published envelope when --context is configured
GET  /api/forecast     forecast.json (unit counts only), or {"resources": {}, "note": ...}
GET  /api/rooms        rooms.json next to the forecast (open demo ward; a real ward only with --real-ward)
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
With --context, forecast and rooms are projections of that envelope. Invalid or absent
configured context is unavailable; independent legacy files are never a fallback.

Privacy (docs/DECISIONS.md D6, D19): a real MIMIC-IV ward (`ward.source` "mimic-iv") is served
counts-only: `/api/rooms` and the context carry no room records and `check_first` is empty,
and the chat refuses room questions. Room views and room chat for it need the server started
in real-ward mode: `--real-ward` (or `--require-real-data`), on the local cluster only.
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
        PATIENT_ID,
        PATIENT_ID_REFUSAL,
        ROLES,
        ChatAgent,
        ModelDown,
        ToolsUnsupported,
        counts_only_forecast,
        counts_only_rooms,
        is_real_ward,
        parse_update_ask,
        update_answer,
        updated_line,
    )
    from app.demo_context import ContextUnavailable, load_context
    from app.evidence import forecast_answer
except ImportError:  # run as `python app/board.py`
    import capacity as capacity_mod
    from chat_agent import (
        PATIENT_ID,
        PATIENT_ID_REFUSAL,
        ROLES,
        ChatAgent,
        ModelDown,
        ToolsUnsupported,
        counts_only_forecast,
        counts_only_rooms,
        is_real_ward,
        parse_update_ask,
        update_answer,
        updated_line,
    )
    from demo_context import ContextUnavailable, load_context
    from evidence import forecast_answer

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


def _int_in_range(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= CAPACITY_MAX


def make_handler(
    forecast_path: pathlib.Path,
    nemotron: str,
    dispatcher: str = "",
    static_path: pathlib.Path = STATIC,
    behind_proxy: bool = False,
    context_path: pathlib.Path | None = None,
    require_real_data: bool = False,
    real_ward: bool = False,
):
    # Real MIMIC-IV room views only when the operator started the server for them
    # (docs/DECISIONS.md D19); otherwise a real ward is served counts-only.
    real_ward = bool(real_ward or require_real_data)
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

    def call_dispatcher(
        path: str, body: dict | None = None, *, timeout: float = 15.0
    ) -> dict:
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
            with urllib.request.urlopen(req, timeout=min(timeout, 30.0)) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                return json.load(e)
            except ValueError:
                return {"started": False, "reason": f"dispatcher error ({e.code})"}
        except Exception as e:
            if path == "/run" and body is not None:
                return {
                    "started": None,
                    "outcome": "unknown",
                    "reason": "Forecast start outcome unknown. Check run status before retrying.",
                }
            return {
                "started": False,
                "reason": f"dispatcher unreachable ({type(e).__name__})",
            }

    agent = ChatAgent(
        nemotron,
        forecast_path,
        rooms_path,
        capacity_path,
        call_dispatcher,
        context_path=context_path,
        require_real_data=require_real_data,
        real_ward=real_ward,
    )

    def capacity_forecast() -> dict:
        """the forecast the free machines are worked out from: the one the page is
        served. In context mode that is the context's forecast (nothing when the
        context is unavailable), never the standalone forecast.json"""
        if context_path is None and not require_real_data:
            return load()
        try:
            if context_path is None:
                raise ContextUnavailable("A context is required")
            context = load_context(context_path)
            if require_real_data and context["source"]["kind"] != "mimic-iv":
                raise ContextUnavailable("A MIMIC-IV context is required")
        except ContextUnavailable:
            return {}
        return context["forecast"]

    def read_capacity() -> dict:
        try:
            cap = json.loads(capacity_path.read_text())
        except (OSError, ValueError):
            cap = {}
        cap = cap if isinstance(cap, dict) else {}
        return {
            **capacity_mod.view(cap, capacity_forecast()),
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
        shown = {**cap, **capacity_mod.view(cap, capacity_forecast())}  # free machines
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
            if path in ("/api/context", "/api/forecast", "/api/rooms") and (
                context_path is not None or require_real_data
            ):
                try:
                    if context_path is None:
                        raise ContextUnavailable("A context is required")
                    context = load_context(context_path)
                    if require_real_data and context["source"]["kind"] != "mimic-iv":
                        raise ContextUnavailable("A MIMIC-IV context is required")
                except ContextUnavailable:
                    return self._json(
                        503,
                        {
                            "available": False,
                            "reason": "Real-data context unavailable: a published MIMIC-IV snapshot is required."
                            if require_real_data
                            else "Demo context unavailable: a valid published snapshot is required.",
                        },
                    )
                if is_real_ward(context) and not real_ward:
                    context = {
                        **context,
                        "forecast": counts_only_forecast(context["forecast"]),
                        "rooms": counts_only_rooms(context["rooms"]),
                    }
                projection = {"/api/forecast": "forecast", "/api/rooms": "rooms"}.get(
                    path
                )
                return self._json(200, context[projection] if projection else context)
            if path == "/api/context":
                # no context is configured: answered 200 so the page's probe on every
                # load leaves no failed request in the browser console
                return self._json(200, {"available": False, "context_mode": False})
            if path == "/api/forecast":
                fc = load()
                if is_real_ward(fc) and not real_ward:
                    fc = counts_only_forecast(fc)
                return self._json(200, fc)
            if (
                path == "/api/rooms"
            ):  # open demo ward; a real ward only in real-ward mode
                try:
                    data = rooms_path.read_bytes()
                except OSError:
                    data = b'{"rooms": [], "note": "pending run"}'
                if not real_ward:
                    try:
                        doc = json.loads(data)
                    except ValueError:
                        doc = None
                    # the forecast names the ward too: either file saying real is enough
                    if doc is None or is_real_ward(doc, load()):
                        return self._json(200, counts_only_rooms(doc))
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
            elif PATIENT_ID.search(q):
                out = {"answer": PATIENT_ID_REFUSAL}
            elif agent.available or context_path is not None or require_real_data:
                try:
                    out = agent.ask(q, role, room, seen)
                except ToolsUnsupported:  # vLLM without tool calling: single-shot below
                    out = {}
                except ModelDown:
                    out = {}
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
                    fallback = load()
                    answer = "Unit forecast: " + forecast_answer(fallback)
                    made_at = fallback.get("made_at")
                if update:
                    made_at = load().get("made_at")
                if line := updated_line(seen, made_at):
                    answer = f"{line}\n{answer}"
                out = {"answer": answer, "made_at": made_at}
            self._json(200, out)

        def log_message(self, *a):  # no request logging: questions stay out of logs
            pass

    return H


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--forecast", type=pathlib.Path, required=True)
    ap.add_argument(
        "--context",
        type=pathlib.Path,
        help="one validated, atomically published demo context",
    )
    ap.add_argument(
        "--require-real-data",
        action="store_true",
        help="require a MIMIC-IV source context; refuse missing or open-demo snapshots",
    )
    ap.add_argument(
        "--real-ward",
        action="store_true",
        help="serve room views and room chat for a real MIMIC-IV ward (local cluster "
        "only, docs/DECISIONS.md D19); without it such a ward is counts-only",
    )
    ap.add_argument("--nemotron", default="http://nemotron:8000")
    ap.add_argument("--dispatcher", default="", help="e.g. http://dispatcher:9000")
    ap.add_argument("--static", type=pathlib.Path, default=STATIC)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument(
        "--host",
        default="0.0.0.0",
        help="bind address; use 127.0.0.1 for local-only access",
    )
    ap.add_argument(
        "--behind-proxy",
        action="store_true",
        help="Fuzzball endpoint proxy in front: compare Origin and Host by host name only",
    )
    return ap.parse_args(argv)


def serve(a) -> ThreadingHTTPServer:
    """Bind the configured server, retaining the app's local-run interface."""
    return ThreadingHTTPServer(
        (a.host, a.port),
        make_handler(
            a.forecast,
            a.nemotron,
            a.dispatcher,
            a.static,
            a.behind_proxy,
            a.context,
            a.require_real_data,
            a.real_ward,
        ),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    serve(parse_args()).serve_forever()


if __name__ == "__main__":
    main()

# ruff: noqa: E501  (plain-words refusal text and docstrings read better unwrapped)
"""Forecast dispatcher: starts t7-forecast on a daily schedule and on request.

Runs as a CPU service inside t7-twin. Fuzzball 4.3 has no built-in cron, but every
service gets a workflow token (FB_TOKEN, FB_API_HOST) that may start, list and stop
the owner's workflows, so this service is the clock and the on-demand trigger.

Usage: python app/dispatcher.py --fuzzfile /store/code/fuzzball/t7-forecast.fz \
         --log /store/runs.jsonl --at 07:00 --port 9000 --cli /store/bin/fuzzball

GET  /status        next scheduled run, the running update, last run per scope,
                    recent runs, and the demo clock (hours past the 07:00 cut)
POST /run           {"role": ..., "scope": "unit" | "room", "room": 1..25 (room scope)}
                    starts an update; scope defaults to "unit"

Two scopes (docs/DECISIONS.md D9): "unit" refreshes the unit counts and every room,
"room" refreshes one stage-ward room. Fuzzball 4.3 Fuzzfiles have no parameters and
`workflow start` has no --set, so the dispatcher renders a copy of the template for
each run (@SCOPE@, @ROOM@, @HOURS@) and starts that copy.

Guards, because the team has exactly two GPUs: one run at a time (any scope, plus
t7-build, t7-smoke and t7-fit; two requests at once cannot both start, because a started
workflow is tracked until the list shows it); 20 minutes between updates of the same scope (a
room is limited per room, and a unit update also counts for every room; the gap is cleared when
the run is seen to fail early). The 07:00 run ignores the gap, retries for 10 minutes on a busy
GPU, an unreachable cluster or a failed start, logs every attempt and the outcome, and a missed
or failed scheduled run shows in /status ("scheduled"). A dispatcher that starts after 07:00
without a scheduled run since that cut runs it once (catch-up). The 07:00 time is
timezone-aware (--tz, default $TZ or America/Chicago): daylight saving moves neither the cut nor
the demo clock. The log records time, trigger (schedule or role), scope, room and workflow id
only: no names, no patient data. The role is advisory: there is no login.

Ward mode: the template gets @WARD_FLAG@, empty by default (open demo ward); with --real-ward
(set only by lane 2) it renders "--real-ward" for rooms.py and aggregate.py.

Demo clock: the stage ward is a replay, so each update moves its cut forward by the
time elapsed since the 07:00 morning cut (dispatcher clock) and passes that to the
forecast as --demo-clock-hours. The 07:00 run is hour 0.
"""

import argparse
import datetime as dt
import json
import logging
import os
import pathlib
import re
import ssl
import subprocess
import threading
import time
import urllib.request
import zoneinfo
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("dispatcher")

# t7-forecast also matches the burst, the per-run names and the t7-<lane>-build style names;
# t7-smoke and t7-fit hold a GPU too. t7-twin (the services) does not.
GPU_WORKFLOW = re.compile(r"^t7-(\w+-)?(build|forecast|smoke|fit)")
ROLES = {"ICU nurse", "ICU physician", "pharmacy", "respiratory therapy", "bed manager"}
SCOPES = ("unit", "room")
ROOMS = range(1, 26)
# Fuzzball 4.3 stage/workflow statuses (docs: "Checking Workflow Status"): Pending, Started, Finished,
# Errored, Canceled, Down; the CLI prints them as STAGE_STATUS_<NAME>. Matched exactly after the prefix
# is stripped; anything else (including an empty or unknown status) counts as still running.
FAILED_STATES = frozenset(
    {"ERRORED", "FAILED", "CANCELED", "CANCELLED", "STOPPED", "DOWN"}
)
TERMINAL = frozenset({"FINISHED", *FAILED_STATES})
LIST_TIMEOUT_S = 20
START_TIMEOUT_S = 60
LIST_TTL_S = 10.0
INFLIGHT_GRACE_S = 120  # a just-started workflow may not be in the list yet
SCHEDULE_WINDOW_S = 600  # the 07:00 run retries for 10 minutes
BODY_CAP = 1024
SOCKET_TIMEOUT_S = 10
CA = "/run/fuzzball-substrate/trusted-certs/root-ca.crt"
MORNING = "07:00"
KEEP_RENDERED = 30


def _hm(at: str) -> tuple[int, int]:
    h, m = (int(x) for x in at.split(":"))
    return h, m


def _elapsed(later: dt.datetime, earlier: dt.datetime) -> dt.timedelta:
    """real elapsed time; aware datetimes are compared in UTC so a DST change adds no hour"""
    if later.tzinfo is not None and earlier.tzinfo is not None:
        return later.astimezone(dt.UTC) - earlier.astimezone(dt.UTC)
    return later - earlier


def _wall(t: dt.datetime, days: int) -> dt.datetime:
    """the same wall-clock time `days` later (zoneinfo: the offset follows the date)"""
    if t.tzinfo is None:
        return t + dt.timedelta(days=days)
    naive = t.replace(tzinfo=None) + dt.timedelta(days=days)
    return naive.replace(tzinfo=t.tzinfo)


def next_run(now: dt.datetime, at: str) -> dt.datetime:
    """the next local time `at` (HH:MM) strictly after `now`"""
    h, m = _hm(at)
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if _elapsed(t, now) > dt.timedelta(0) else _wall(t, 1)


def last_cut(now: dt.datetime, at: str = MORNING) -> dt.datetime:
    """the most recent morning cut (`at`, default 07:00) at or before `now`"""
    h, m = _hm(at)
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if _elapsed(now, t) >= dt.timedelta(0) else _wall(t, -1)


def demo_clock_hours(now: dt.datetime, at: str = MORNING) -> float:
    """hours elapsed since the morning cut, to 0.1 h; this offset moves the ward's cut"""
    return round(_elapsed(now, last_cut(now, at)).total_seconds() / 360) / 10


def demo_clock_label(hours: float, at: str = MORNING) -> str:
    h, m = _hm(at)
    total = h * 60 + m + round(hours * 60)
    return f"Ward clock {total // 60 % 24:02d}:{total % 60:02d} ({at} + {hours:g} h)"


def _safe(name: str) -> str:
    """workflow names reach user-facing reasons: letters, digits, _ and - only"""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(name))[:64]


def _status_of(w: dict) -> str:
    raw = (
        str(w.get("status") or w.get("state") or w.get("Status") or "").upper().strip()
    )
    return re.sub(r"^(?:STAGE|WORKFLOW)_STATUS_", "", raw)


def _name_of(w: dict) -> str:
    return str(w.get("name") or w.get("Name") or "")


def _id_of(w: dict) -> str:
    for k in ("id", "ID", "Id", "uuid", "workflowId", "workflow_id"):
        if w.get(k):
            return str(w[k])
    return ""


def busy(workflows: list[dict]) -> str | None:
    """(sanitised) name of a GPU workflow that has not clearly ended.

    Statuses are matched exactly against Fuzzball 4.3's terminal set (FINISHED, ERRORED,
    CANCELED, DOWN, ...); an empty or unknown status counts as running (safe side).
    """
    for w in workflows:
        if not isinstance(w, dict):
            continue
        name = _name_of(w)
        if GPU_WORKFLOW.match(name) and _status_of(w) not in TERMINAL:
            return _safe(name)
    return None


def _at_text(t: dt.datetime) -> str:
    return f"{t:%H:%M}"


class Dispatcher:
    def __init__(
        self,
        fuzzfile,
        log: pathlib.Path,
        min_gap_s: int,
        cli="fuzzball",
        clock: Callable[[], dt.datetime] = dt.datetime.now,
        at: str = MORNING,
        real_ward: bool = False,
        list_ttl_s: float = LIST_TTL_S,
        rooms: pathlib.Path | None = None,
    ):
        self.fuzzfile, self.log, self.min_gap_s, self.cli = (
            pathlib.Path(fuzzfile),
            pathlib.Path(log),
            min_gap_s,
            cli,
        )
        self.clock, self.at, self.real_ward = clock, at, real_ward
        # rooms.py --room needs a whole-ward rooms.json to update one room of
        self.rooms = pathlib.Path(rooms) if rooms else self.log.with_name("rooms.json")
        self.list_ttl_s = list_ttl_s
        # self.lock guards the guard state only (last, inflight): never held across a CLI call
        self.lock = threading.Lock()
        self.log_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._cache: tuple[float, list[dict]] | None = None
        # last start per scope key: "unit" or ("room", n); survives a restart via the log
        self.last: dict = {}
        # workflows we started that may not show in the list yet: id -> {name, key, at}
        self.inflight: dict[str, dict] = {}
        self._load_last()

    # ---- plumbing ----------------------------------------------------------------
    def _cli(self, *args, timeout: float = START_TIMEOUT_S) -> str:
        return subprocess.run(
            [self.cli, *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout

    def workflows(self, fresh: bool = False) -> list[dict]:
        """`workflow list`, cached for a few seconds so a burst of asks costs one CLI call"""
        with self._cache_lock:
            c = self._cache
            if not fresh and c and time.monotonic() - c[0] < self.list_ttl_s:
                return c[1]
        out = self._cli("workflow", "list", "-o", "json", timeout=LIST_TIMEOUT_S)
        data = json.loads(out or "[]")
        rows = data if isinstance(data, list) else data.get("workflows", [])
        rows = [w for w in rows if isinstance(w, dict)]
        with self._cache_lock:
            self._cache = (time.monotonic(), rows)
        return rows

    def _drop_cache(self) -> None:
        with self._cache_lock:
            self._cache = None

    def _repair_log(self) -> None:
        """a crash can leave a half-written last line; cut it so the next append starts clean"""
        try:
            data = self.log.read_bytes()
        except OSError:
            return
        if not data or data.endswith(b"\n"):
            return
        head, _, tail = data.rpartition(b"\n")
        try:
            json.loads(tail)
            fixed = data + b"\n"  # complete row, only the newline was lost
        except ValueError:
            fixed = head + b"\n" if head else b""
        self.log.write_bytes(fixed)

    def record(self, **row):
        row["at"] = self.clock().isoformat(timespec="seconds")
        with self.log_lock:
            self._repair_log()
            with self.log.open("a") as f:
                f.write(json.dumps(row) + "\n")

    def _rows(self) -> list[dict]:
        try:
            text = self.log.read_text()
        except OSError:
            return []
        rows = []
        for line in text.splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                rows.append(r)
        return rows

    def _parse_at(self, s: str) -> dt.datetime:
        """a logged time in the clock's flavour (old rows may lack the offset)"""
        t = dt.datetime.fromisoformat(s)
        ref = self.clock()
        if ref.tzinfo is not None and t.tzinfo is None:
            return t.replace(tzinfo=ref.tzinfo)
        if ref.tzinfo is None and t.tzinfo is not None:
            return t.astimezone().replace(tzinfo=None)
        return t

    def _load_last(self) -> None:
        for r in self._rows():
            if r.get("started") and r.get("at"):
                try:
                    self.last[self._key(r.get("scope", "unit"), r.get("room"))] = (
                        self._parse_at(r["at"])
                    )
                except ValueError:
                    pass

    @staticmethod
    def _key(scope, room):
        return ("room", room) if scope == "room" else "unit"

    # ---- guards ------------------------------------------------------------------
    def gap_refusal(self, scope: str, room: int | None) -> str | None:
        """plain-words refusal when this scope (or room) was updated too recently"""
        last = self.last.get(self._key(scope, room))
        if scope == "room":  # a unit update refreshes every room too
            unit = self.last.get("unit")
            last = max(filter(None, [last, unit]), default=None)
        if last is None:
            return None
        now = self.clock()
        since = _elapsed(now, last).total_seconds()
        left = self.min_gap_s - since
        if left <= 0:
            return None
        ago = max(0, int(since // 60))
        when = _at_text(last + dt.timedelta(seconds=self.min_gap_s))
        what = "Updated" if scope == "unit" else f"Room {room} updated"
        return f"{what} {ago} minutes ago. You can update again at {when}."

    def _reap(self, wfs: list[dict]) -> None:
        """settle the workflows we started (call with self.lock held): forget the ended ones,
        and clear the gap of one that failed early so people can try again at once"""
        now = self.clock()
        for wid, info in list(self.inflight.items()):
            if info.get("pending"):
                continue
            hit = next(
                (w for w in wfs if _id_of(w) == wid or _name_of(w) == info["name"]),
                None,
            )
            age = _elapsed(now, info["at"]).total_seconds()
            if hit is None:
                if age > INFLIGHT_GRACE_S:
                    del self.inflight[wid]
                continue
            st = _status_of(hit)
            if st in TERMINAL:
                del self.inflight[wid]
                if st in FAILED_STATES and age < self.min_gap_s:
                    if self.last.get(info["key"]) == info["at"]:
                        del self.last[info["key"]]
                    self.record(event="run_failed", workflow=wid, status=st)

    def _busy(self, wfs: list[dict]) -> str | None:
        """a GPU workflow is active (listed, or started by us and not listed yet)"""
        if other := busy(wfs):
            return other
        now = self.clock()
        for info in self.inflight.values():
            if (
                info.get("pending")
                or _elapsed(now, info["at"]).total_seconds() < INFLIGHT_GRACE_S
            ):
                listed = any(_name_of(w) == info["name"] for w in wfs)
                if not listed:
                    return _safe(info["name"])
        return None

    # ---- starting a run ----------------------------------------------------------
    def render(
        self, scope: str, room: int | None, hours: float, name: str
    ) -> pathlib.Path:
        """a per-run copy of the template with the run's scope, room, demo clock and ward mode"""
        text = (
            self.fuzzfile.read_text()
            .replace("@SCOPE@", scope)
            .replace("@ROOM@", str(room or 0))
            .replace("@HOURS@", f"{hours:g}")
            .replace("@WARD_FLAG@", "--real-ward" if self.real_ward else "")
        )
        out_dir = self.log.parent / "rendered"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"{name}.fz"
        out.write_text(text)
        for old in sorted(out_dir.glob("*.fz"), key=lambda p: p.stat().st_mtime)[
            :-KEEP_RENDERED
        ]:
            old.unlink(missing_ok=True)
        return out

    def start(
        self,
        trigger: str,
        scope: str = "unit",
        room: int | None = None,
        enforce_gap: bool = True,
    ) -> dict:
        """start one update unless a guard says no; returns what happened"""
        if scope not in SCOPES:
            return {"started": False, "reason": "choose the unit or one room"}
        if scope == "room" and (
            not isinstance(room, int) or isinstance(room, bool) or room not in ROOMS
        ):
            return {"started": False, "reason": "choose a room from 1 to 25"}
        if scope == "unit":
            room = None
        elif not self.rooms.exists():
            return {
                "started": False,
                "reason": "No room data yet. Update the unit first, then a single room.",
            }
        try:  # slow call first, outside the lock
            wfs = self.workflows()
        except Exception as e:  # cluster unreachable: refuse, do not guess
            return {
                "started": False,
                "reason": f"cannot list workflows ({type(e).__name__})",
            }
        key = self._key(scope, room)
        with self.lock:
            self._reap(wfs)
            if enforce_gap and (why := self.gap_refusal(scope, room)):
                return {"started": False, "reason": why}
            other = self._busy(wfs)
            if other:
                what = (
                    "The model is being built"
                    if re.match(r"^t7-(\w+-)?(build|fit)", other)
                    else "Another update is running"
                    if re.match(r"^t7-(\w+-)?forecast", other)
                    else "A check is running"
                )
                return {
                    "started": False,
                    "busy": True,
                    "reason": f"{what} ({other}); the two GPUs are in use. Try again in a few minutes.",
                }
            now = self.clock()
            hours = 0.0 if trigger == "schedule" else demo_clock_hours(now, self.at)
            tag = f"room{room}-" if scope == "room" else ""
            name = f"t7-forecast-{tag}{now:%m%d-%H%M}"
            token = f"pending:{name}"
            self.inflight[token] = {
                "name": name,
                "key": key,
                "at": now,
                "pending": True,
            }
        try:  # the CLI call runs without the lock; the pending entry blocks a second start
            path = self.render(scope, room, hours, name)
            wid = self._cli("workflow", "start", str(path), "--name", name).strip()
        except Exception as e:
            with self.lock:
                self.inflight.pop(token, None)
            if trigger != "schedule":  # the scheduled run logs every attempt itself
                self.record(
                    trigger=trigger,
                    scope=scope,
                    room=room,
                    started=False,
                    error=type(e).__name__,
                )
            return {"started": False, "reason": f"start failed ({type(e).__name__})"}
        with self.lock:
            self.inflight.pop(token, None)
            self.inflight[wid] = {"name": name, "key": key, "at": now}
            self.last[key] = now
        self._drop_cache()
        self.record(
            trigger=trigger,
            scope=scope,
            room=room,
            started=True,
            workflow=wid,
            name=name,
            ward="real" if self.real_ward else "demo",
        )
        return {
            "started": True,
            "workflow": wid,
            "name": name,
            "scope": scope,
            "room": room,
            "demo_clock_hours": hours,
            "demo_clock_label": demo_clock_label(hours, self.at),
        }

    # ---- status ------------------------------------------------------------------
    def _decorate(self, r: dict) -> dict:
        """a log row with its scope, room and demo clock (derived from its time)"""
        r = dict(r)
        r.setdefault("scope", "unit")
        try:
            at = self._parse_at(r["at"])
            hours = (
                0.0 if r.get("trigger") == "schedule" else demo_clock_hours(at, self.at)
            )
            r["demo_clock_hours"] = hours
            r["demo_clock_label"] = demo_clock_label(hours, self.at)
        except (KeyError, ValueError):
            pass
        return r

    def recent(self, n=10) -> list[dict]:
        return [self._decorate(r) for r in self._rows()[-n:]]

    def active(self) -> dict | None:
        """the update (or build) that is active now; {"unknown": True} if the list fails"""
        try:
            name = busy(self.workflows())
        except Exception:
            return {"unknown": True}
        return {"name": name} if name else None

    def scheduled_state(self) -> dict:
        """did this morning's scheduled run happen? ok | pending | failed | missed"""
        now = self.clock()
        cut = last_cut(now, self.at)
        rows = []
        for r in self._rows():
            if r.get("trigger") == "schedule" or r.get("event") == "scheduled_outcome":
                try:
                    if _elapsed(self._parse_at(r["at"]), cut) >= dt.timedelta(0):
                        rows.append(r)
                except (KeyError, ValueError):
                    pass
        out = {"cut": cut.isoformat(timespec="minutes")}
        if any(r.get("started") for r in rows):
            return {**out, "state": "ok", "ok": True}
        fails = [r for r in rows if r.get("event") == "scheduled_outcome"]
        if fails:
            return {
                **out,
                "state": "failed",
                "ok": False,
                "detail": str(fails[-1].get("reason", "")),
            }
        if _elapsed(now, cut).total_seconds() <= SCHEDULE_WINDOW_S + 60:
            return {**out, "state": "pending", "ok": None}
        return {
            **out,
            "state": "missed",
            "ok": False,
            "detail": "no scheduled run since the cut",
        }

    def status(self) -> dict:
        now = self.clock()
        started = [r for r in self._rows() if r.get("started")]
        last = {}
        for scope in SCOPES:
            rows = [r for r in started if r.get("scope", "unit") == scope]
            if rows:
                last[scope] = self._decorate(rows[-1])
        hours = demo_clock_hours(now, self.at)
        running = self.active()
        return {
            "next_scheduled": next_run(now, self.at).isoformat(timespec="minutes"),
            "window": f"{self.at} to {self.at}",
            "scheduled": self.scheduled_state(),
            "running": running,
            "updating": bool(running and not running.get("unknown")),
            "last": last,
            "recent": self.recent(),
            "demo_clock_hours": hours,
            "demo_clock_label": demo_clock_label(hours, self.at),
            "min_gap_minutes": self.min_gap_s // 60,
            "ward": "real" if self.real_ward else "demo",
        }


def refresh_token() -> bool:
    """swap FB_TOKEN for a fresh 7-day one; keep the old one if the call fails"""
    url = os.environ.get("FB_OPENAPI_URL", "") + "/v4/workflows:refreshToken"
    try:
        ctx = ssl.create_default_context(
            cafile=CA if pathlib.Path(CA).exists() else None
        )
        req = urllib.request.Request(
            url,
            method="POST",
            headers={"Authorization": f"Bearer {os.environ['FB_TOKEN']}"},
        )
        with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
            token = json.load(r).get("token")
        if token:
            os.environ["FB_TOKEN"] = token
            return True
    except Exception as e:  # never the token itself
        log.warning("token refresh failed (%s); will retry", type(e).__name__)
    return False


def _transient(out: dict) -> bool:
    r = str(out.get("reason", ""))
    return bool(out.get("busy")) or r.startswith(
        ("cannot list workflows", "start failed")
    )


def run_scheduled(
    d: Dispatcher,
    retry_s: float = 60.0,
    window_s: float = SCHEDULE_WINDOW_S,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """the 07:00 run: no gap guard; retries busy GPUs and transient failures for 10 minutes.

    Every attempt and the final outcome go to runs.jsonl; /status shows a failed run.
    """
    out: dict = {}
    waited, attempts = 0.0, 0
    while True:
        attempts += 1
        out = d.start("schedule", "unit", enforce_gap=False)
        if out.get("started"):
            log.info("scheduled run started after %d attempt(s)", attempts)
            return out
        d.record(
            trigger="schedule",
            scope="unit",
            event="scheduled_attempt",
            attempt=attempts,
            started=False,
            reason=out.get("reason", ""),
        )
        if not _transient(out) or waited + retry_s > window_s:
            break
        sleep(retry_s)
        waited += retry_s
    d.record(
        trigger="schedule",
        scope="unit",
        event="scheduled_outcome",
        started=False,
        attempts=attempts,
        reason=out.get("reason", ""),
    )
    log.error(
        "scheduled run failed after %d attempt(s): %s", attempts, out.get("reason")
    )
    return out


class Scheduler:
    """fires the scheduled run once per morning cut; keyed by the cut, so it cannot double fire
    across a clock change, and a start after 07:00 without a run since the cut catches up"""

    def __init__(self, d: Dispatcher, at: str, sleep=time.sleep):
        self.d, self.at, self.sleep = d, at, sleep
        self.fired = None
        cut = last_cut(d.clock(), at)
        if d.scheduled_state().get("ok"):  # this morning's run already happened
            self.fired = cut.isoformat()
        self.last_refresh = time.time()

    def tick(self) -> bool:
        """one wake-up: fire if a cut passed unserved; refresh the token daily"""
        fired = False
        cut = last_cut(self.d.clock(), self.at).isoformat()
        if cut != self.fired:
            self.fired = cut  # set first: a crash inside must not loop on the same cut
            run_scheduled(self.d, sleep=self.sleep)
            fired = True
        if time.time() - self.last_refresh > 86400:
            self.last_refresh = time.time()
            refresh_token()
        return fired


def scheduler(d: Dispatcher, at: str, poll_s: float = 30.0) -> None:
    s = Scheduler(d, at)
    while True:  # nothing in here may end the thread: log and carry on
        try:
            s.tick()
        except Exception:
            log.exception("scheduler tick failed")
        time.sleep(poll_s)


def make_handler(d: Dispatcher, at: str = MORNING):
    class H(BaseHTTPRequestHandler):
        timeout = SOCKET_TIMEOUT_S
        _head = False

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not self._head:
                self.wfile.write(body)

        def do_HEAD(self):
            self._head = True
            self.do_GET()

        def do_GET(self):
            if self.path == "/" and self._head:
                return self._send(200, {})
            if self.path != "/status":
                return self._send(404, {"error": "not found"})
            self._send(200, d.status())

        def do_POST(self):
            if self.path != "/run":
                return self._send(404, {"error": "not found"})
            raw = self.headers.get("Content-Length", "")
            if not (raw.isascii() and raw.isdigit()):
                return self._send(400, {"started": False, "reason": "bad request"})
            n = int(raw)
            if n > BODY_CAP:
                return self._send(
                    413, {"started": False, "reason": "request too large"}
                )
            try:
                data = self.rfile.read(n)
                req = json.loads(data or b"{}")
            except (OSError, ValueError):
                return self._send(400, {"started": False, "reason": "bad request"})
            if len(data) != n or not isinstance(req, dict):
                return self._send(400, {"started": False, "reason": "bad request"})
            role = req.get("role", "")
            if role not in ROLES:
                return self._send(400, {"started": False, "reason": "choose your role"})
            scope = req.get("scope", "unit")
            room = req.get("room")
            out = d.start(role, scope, room)
            self._send(400 if out.get("reason", "").startswith("choose") else 200, out)

        def log_message(self, *a):
            pass

    return H


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fuzzfile", type=pathlib.Path, required=True)
    ap.add_argument("--log", type=pathlib.Path, required=True)
    ap.add_argument("--at", default=MORNING, help="daily local start time, HH:MM")
    ap.add_argument("--tz", default=os.environ.get("TZ") or "America/Chicago")
    ap.add_argument(
        "--min-gap", type=int, default=20, help="minutes between updates of one scope"
    )
    ap.add_argument("--cli", default="fuzzball")
    ap.add_argument(
        "--rooms", type=pathlib.Path, help="rooms.json (default: next to --log)"
    )
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument(
        "--real-ward",
        action="store_true",
        help="render --real-ward into the forecast runs (real MIMIC-IV rooms; lane 2 only)",
    )
    a = ap.parse_args()
    tz = zoneinfo.ZoneInfo(a.tz)
    d = Dispatcher(
        a.fuzzfile,
        a.log,
        a.min_gap * 60,
        a.cli,
        clock=lambda: dt.datetime.now(tz),
        at=a.at,
        real_ward=a.real_ward,
        rooms=a.rooms,
    )
    threading.Thread(target=scheduler, args=(d, a.at), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(d, a.at)).serve_forever()


if __name__ == "__main__":
    main()

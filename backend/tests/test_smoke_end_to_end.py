"""End to end on a laptop, no network, GPU or model: the open demo ward through
scripts/run_cohort.py (pending-model files, made-up names), the board started as
`python app/board.py` on loopback, every endpoint with and without the required
headers, then the same with a scored ("ready") forecast, then broken files and a
dispatcher that is down. Nothing but backend/clif_demo and synthetic frames."""

import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import numpy as np
import polars as pl
import pytest
import test_lookahead as tl

from app import dispatcher as dsp
from app import stage_ward
from tests.test_board import serve
from tests.test_chat_agent import Fake, tc, text
from tests.test_cohort import DEMO, HOSP, run_cohort
from tests.test_dispatcher import FakeCli

BACKEND = pathlib.Path(__file__).resolve().parents[1]
HEADERS = {"Content-Type": "application/json", "X-Lookahead": "1"}
QUESTION = "zebra-crossing question about room 3"  # must never reach a log
GETS = ("/api/forecast", "/api/rooms", "/api/runs", "/api/capacity")
# an exception's class name, a traceback, or a value that was never filled in
LEAK = re.compile(
    r"Traceback|\b[A-Z]\w*(?:Error|Exception)\b|null more|undefined|\bNaN\b|Errno"
)


def http(base, path, body=None, headers=None):
    req = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def clean(base, path, body=None, headers=None, want=200):
    """the call's JSON; fails on the wrong status, a body that is not JSON, or a leak"""
    code, raw = http(base, path, body, headers)
    assert code == want, (path, code, raw[:200])
    assert not LEAK.search(raw), (path, LEAK.search(raw).group(0))
    return json.loads(raw)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Board:
    """`python app/board.py` as its own process (the way the workflow runs it), its
    stdout and stderr kept in a file"""

    def __init__(self, box: pathlib.Path, forecast: pathlib.Path, *args: str):
        self.log_path = box / f"board-{free_port()}.log"
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.log = self.log_path.open("w")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(BACKEND / "app" / "board.py"),
                "--forecast",
                str(forecast),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                *args,
            ],
            stdout=self.log,
            stderr=subprocess.STDOUT,
            cwd=box,  # not the repo: `app` is importable only as the script finds it
            env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        )
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.2):
                    return
            except OSError:
                assert self.proc.poll() is None, self.logs()
                time.sleep(0.1)
        raise AssertionError("the board did not start: " + self.logs())

    def logs(self) -> str:
        self.log.flush()
        return self.log_path.read_text()

    def stop(self) -> str:
        """end the process (once) and return everything it wrote"""
        if self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        self.log.close()
        return self.log_path.read_text()


@pytest.fixture(scope="module")
def ward(tmp_path_factory):
    """pending-model files for the 25 open-demo stays, with made-up names; and a
    scored copy (synthetic features, really fitted probes) in `scored/`"""
    tmp = tmp_path_factory.mktemp("smoke")
    sel, _ = stage_ward.select_rooms(
        stage_ward.score_stays(DEMO, stage_ward.eligible_stays(DEMO))
    )
    ids = tmp / "ids.parquet"
    sel.select(HOSP).write_parquet(ids)
    args = [str(DEMO), "--ward-ids", str(ids), "--work", str(tmp / "work")]
    args += ["--names", "fake"]
    run_cohort.main([*args, "--out", str(tmp / "out")])

    box = tmp / "model"
    box.mkdir()
    home = tl._model_dir(box)
    _, probes = tl._fit_probes(box, home)

    def fake_extract(root, model_home, config=None, stay_ids=None):
        rng = np.random.default_rng(1)
        for f in pathlib.Path(root).glob("*_for_inference.parquet"):
            lab = pl.read_parquet(f, columns=[HOSP, "last_valid", "cut_s"])
            x = rng.normal(size=(lab.height, 4)).astype(np.float32)
            split = f.name.removesuffix("_for_inference.parquet")
            lab.with_columns(features=pl.Series(list(x))).write_parquet(
                pathlib.Path(root) / f"features-{split}-{tl.MODEL}.parquet"
            )

    from icutwin.scoring import extractor

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(extractor, "extract", fake_extract)
        run_cohort.main(
            [*args, "--reuse-tokens", "--out", str(tmp / "scored")]
            + ["--model", str(home), "--probes", str(probes)]
        )
    return tmp, sel[HOSP].to_list()


@pytest.fixture
def stack(ward, tmp_path):
    """a served copy of the pending files, the board process, a dispatcher (the
    Fuzzball CLI faked) and a scripted stand-in for the chat model"""
    tmp, ids = ward
    store = tmp_path / "store"
    shutil.copytree(tmp / "out", store)
    disp, dbase = serve(dsp.make_handler(FakeCli(tmp_path)))
    model = Fake([tc("get_room", {"room": 3}), text("Room 3: no forecast yet.")] * 4)
    b = Board(tmp_path, store / "forecast.json", "--dispatcher", dbase)
    b.model, b.store, b.scored, b.ids = model, store, tmp / "scored", ids
    b.chat = Board(
        tmp_path,
        store / "forecast.json",
        "--dispatcher",
        dbase,
        "--nemotron",
        model.url,
    )
    yield b
    b.chat.stop()
    b.stop()
    model.close()
    disp.shutdown()


def walk(b, state: str) -> list[str]:
    """every endpoint once; returns the made-up names on the board"""
    base = b.base
    code, page = http(base, "/")
    assert code == 200 and "<html" in page.lower() and "Traceback" not in page
    fc = clean(base, "/api/forecast")
    rooms = clean(base, "/api/rooms")
    assert fc["forecast_state"] == rooms["forecast_state"] == state
    assert len(rooms["rooms"]) == 25 and rooms["dropped"] == 0
    assert [r["room"] for r in rooms["rooms"]] == list(range(1, 26))
    assert rooms["names"] == "fictional"
    names = [r["name"]["display"] for r in rooms["rooms"]]
    assert all(n and r["name"]["fictional"] for n, r in zip(names, rooms["rooms"]))
    assert all("vasoactives" in r["on_now_detail"] for r in rooms["rooms"])
    assert fc["beds"] == 25 and fc["staffing_now"]["nurses"] >= 13
    assert fc["life_support"]["now_patients"] >= 0
    runs = clean(base, "/api/runs")
    assert "next_scheduled" in runs
    cap = clean(base, "/api/capacity")
    assert set(cap) >= {"life_support_patients", "vents_total", "crrt_total"}

    saved = clean(
        base,
        "/api/capacity",
        {"vents_total": 12, "crrt_total": 3, "role": "ICU nurse"},
        HEADERS,
    )
    on = fc["life_support"]["now_by"]
    assert saved["ok"] and saved["capacity"]["vents_free"] == max(0, 12 - on["imv"])
    assert clean(base, "/api/capacity")["crrt_free"] == max(0, 3 - on["crrt"])
    run = clean(base, "/api/rerun", {"role": "ICU nurse", "scope": "unit"}, HEADERS)
    assert isinstance(run["started"], bool) and (run["started"] or run["reason"])
    ask = {"question": QUESTION, "role": "ICU nurse", "room": 3}
    assert clean(base, "/api/ask", ask, HEADERS)["answer"]
    got = clean(b.chat.base, "/api/ask", ask, HEADERS)  # the agent, with a tool call
    assert got["answer"].startswith("Room 3") and got["trace"] == ["get_room"]

    for path, body in (
        ("/api/capacity", {"vents_total": 1, "role": "ICU nurse"}),
        ("/api/rerun", {"role": "ICU nurse", "scope": "unit"}),
        ("/api/ask", ask),
    ):
        for bad in ({"Content-Type": "application/json"}, {"X-Lookahead": "1"}, {}):
            refused = clean(base, path, body, bad, want=403)
            assert refused == {"ok": False, "reason": "request refused"}
    assert (
        clean(base, "/api/capacity")["vents_total"] == 12
    )  # a refused POST saved nothing
    return names


def test_pending_then_ready_through_every_endpoint_and_nothing_private_in_the_logs(
    stack,
):
    b = stack
    names = walk(b, "pending-model")
    fc = clean(b.base, "/api/forecast")
    assert fc["model"] == "pending" and fc["yardstick"] is None
    assert fc["staffing_next_24h"]["nurses"]["p50"] is None
    assert fc["machines"] is None  # made before any total was entered
    rooms = clean(b.base, "/api/rooms")["rooms"]
    assert all(set(r["p"].values()) == {None} and r["level"] is None for r in rooms)

    # second pass: the scored files replace the pending ones (read per request)
    for f in ("rooms.json", "forecast.json"):
        shutil.copy(b.scored / f, b.store / (f + ".tmp"))
        os.replace(b.store / (f + ".tmp"), b.store / f)
    names += walk(b, "ready")
    fc = clean(b.base, "/api/forecast")
    assert fc["resources"]["ventilator"]["p50"] is not None
    assert fc["staffing_next_24h"]["rt"]["available"] is True
    rooms = clean(b.base, "/api/rooms")["rooms"]
    assert all(r["level"] in ("low", "medium", "high") for r in rooms)

    logs = b.stop() + b.chat.stop() + (b.store.parent / "runs.jsonl").read_text()
    assert "capacity set" in logs  # the log was captured
    assert "Traceback" not in logs
    assert QUESTION not in logs and "zebra" not in logs
    for n in set(names):
        assert n not in logs and n.split(",")[0] not in logs
    assert not any(i in logs for i in b.ids)
    sent = json.dumps(b.model.requests)  # the model saw the question, not a stay id
    assert QUESTION in sent and not any(i in sent for i in b.ids)


BROKEN = {
    "forecast.json missing": lambda s: (s / "forecast.json").unlink(),
    "forecast.json truncated": lambda s: (s / "forecast.json").write_text(
        (s / "forecast.json").read_text()[:300]
    ),
    "forecast.json not an object": lambda s: (s / "forecast.json").write_text("[1]"),
    "rooms.json missing": lambda s: (s / "rooms.json").unlink(),
    "rooms.json truncated": lambda s: (s / "rooms.json").write_text(
        (s / "rooms.json").read_text()[:300]
    ),
    "capacity.json corrupt": lambda s: (s / "capacity.json").write_text('{"vents_'),
    "capacity.json not an object": lambda s: (s / "capacity.json").write_text('"x"'),
}


@pytest.mark.parametrize("case", sorted(BROKEN))
def test_a_broken_file_gives_clear_json_never_a_500(stack, case):
    b = stack
    BROKEN[case](b.store)
    code, page = http(b.base, "/")
    assert code == 200
    for path in GETS:
        clean(b.base, path)
    if case.startswith("forecast"):
        assert "no forecast yet" in clean(b.base, "/api/forecast")["note"]
    if case.startswith("rooms"):
        assert clean(b.base, "/api/rooms") == {"rooms": [], "note": "pending run"}
    if case.startswith("capacity"):
        assert clean(b.base, "/api/capacity")["vents_total"] is None
    ask = {"question": "how many ventilators?", "role": "ICU nurse", "room": 3}
    for base in (b.base, b.chat.base):
        assert clean(base, "/api/ask", ask, HEADERS)["answer"]
    body = {"vents_total": 9, "role": "ICU nurse"}
    assert clean(b.base, "/api/capacity", body, HEADERS)["ok"]
    assert clean(b.base, "/api/capacity")["vents_total"] == 9  # a save repairs the file
    clean(b.base, "/api/rerun", {"role": "ICU nurse", "scope": "unit"}, HEADERS)
    assert "Traceback" not in b.logs() + b.chat.logs()


def test_dispatcher_unreachable_is_said_plainly(ward, tmp_path):
    tmp, _ = ward
    store = tmp_path / "store"
    shutil.copytree(tmp / "out", store)
    dead = f"http://127.0.0.1:{free_port()}"
    for extra in (["--dispatcher", dead], []):  # down, and none configured
        b = Board(tmp_path, store / "forecast.json", *extra)
        try:
            runs = clean(b.base, "/api/runs")
            assert runs["available"] is False and "dispatcher" in runs["reason"]
            body = {"role": "ICU nurse", "scope": "unit"}
            run = clean(b.base, "/api/rerun", body, HEADERS)
            assert run["started"] is False and "dispatcher" in run["reason"]
            ask = {"question": "update the unit", "role": "ICU nurse"}
            got = clean(b.base, "/api/ask", ask, HEADERS)
            assert got["answer"].startswith("Forecast not started: ")
            assert (
                clean(b.base, "/api/forecast")["beds"] == 25
            )  # the board still serves
        finally:
            assert "Traceback" not in b.stop()

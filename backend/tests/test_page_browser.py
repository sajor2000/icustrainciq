r"""The board page in a real browser (CodeRabbit PR #16, findings on the page).

The page is Dema's final board (D25): a bed has no trajectory word, so a fully
observed bed with nothing at its threshold reads "clear" (never "Steady"), and the
machine totals are the server's (capacity.json), not the device copy.

Skipped unless Playwright is installed:
    uv run --extra dev --extra model --with playwright \
        python -m pytest -q tests/test_page_browser.py
Synthetic data only (examples/). Each check runs at a desk and a phone width.
"""

import http.server
import json
import pathlib
import re
import threading
import time

import pytest

from tests.test_chat_agent import Fake, text
from tests.test_demo_chat_app import running_board

REPO = pathlib.Path(__file__).resolve().parents[2]
PAGE = REPO / "mockups/command-center.html"
SUPPORTS = ("imv", "vasopressor", "crrt")
WIDTHS = [(1440, 900), (390, 844)]


def test_the_served_page_is_a_copy_of_the_mockup():
    assert (REPO / "backend/app/static/index.html").read_bytes() == PAGE.read_bytes()


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:  # no bundled browser downloaded: use the installed Chrome
            try:
                b = p.chromium.launch(channel="chrome")
            except Exception:
                pytest.skip("no Chromium or Chrome for Playwright")
        yield b
        b.close()


def unit_files(tmp_path, edit):
    """examples/ forecast and rooms; every support off and unlikely, then `edit`"""
    rooms = json.loads((REPO / "examples/rooms.json").read_text())
    for r in rooms["rooms"]:
        r["on_now"] = {k: False for k in SUPPORTS} | {"ecmo": None}
        r["on_life_support"] = False
        r["p"] = {k: 0.05 for k in SUPPORTS} | {"icu_departure": 0.1, "death": 0.01}
    edit({r["room"]: r for r in rooms["rooms"]})
    (tmp_path / "rooms.json").write_text(json.dumps(rooms))
    (tmp_path / "forecast.json").write_text(
        (REPO / "examples/forecast.json").read_text()
    )


def open_page(browser, base, size, fragment="fast", storage=None, wait=None):
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    if storage:
        page.add_init_script(
            "".join(
                f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});"
                for k, v in storage.items()
            )
        )
    page.goto(f"{base}/#{fragment}")
    page.wait_for_selector(wait or 'button.bed[data-room="1"]', state="attached")
    return page


@pytest.mark.parametrize("size", WIDTHS)
def test_unknown_current_support_is_not_steady(browser, tmp_path, size):
    def edit(room):
        room[7]["on_now"]["imv"] = None  # not observed; every chance is low

    unit_files(tmp_path, edit)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, size)
        state = lambda n: page.get_attribute(  # noqa: E731
            f'button.bed[data-room="{n}"]', "data-state"
        )
        assert state(8) == "clear"  # the same chances, fully observed
        assert state(7) == "unknown"
        label = page.get_attribute('button.bed[data-room="7"]', "aria-label")
        assert "Steady" not in label and "No estimate" in label
        assert "nothing new" not in label and "unknown: Ventilator" in label, label
        tile = " ".join(page.inner_text('button.bed[data-room="7"]').split())
        assert "No estimate" in tile and "nothing new" not in tile, tile
        assert "No life support" not in tile and "unknown" in tile, tile
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_machine_total_stays_when_use_exceeds_it(browser, tmp_path, size):
    def edit(room):
        for n in (1, 2, 3, 4, 5):  # five ventilators in use
            room[n]["on_now"]["imv"], room[n]["p"]["imv"] = True, None
        for n in (10, 11):  # two more beds flagged
            room[n]["p"]["imv"] = 0.6

    unit_files(tmp_path, edit)
    # the saved total is four (on the server: its totals win over the device copy)
    (tmp_path / "capacity.json").write_text(json.dumps({"vents_total": 4}))
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, size, "view=strain&fast")
        card = page.locator('article.wc[data-k="imv"]')
        bar = card.locator("svg.ubar")
        label = bar.get_attribute("aria-label")
        assert "5 in use now" in label and "4 in total" in label, label
        assert "over the total" in label
        assert "4 total" in bar.text_content()
        words = " ".join(card.inner_text().split())
        assert "Free 0 of 4 · 1 over" in words, words
        # one already over, two flagged: three short, not two
        assert "Ventilators short by 3" in page.inner_text("body")
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
@pytest.mark.parametrize("questions", [1, 2])
def test_close_discards_pending_answers(browser, tmp_path, size, questions):
    def slow(_):
        time.sleep(1.2)
        return text("late")

    unit_files(tmp_path, lambda room: None)
    model = Fake([slow] * questions)
    try:
        with running_board(tmp_path, model.url, static_path=PAGE) as base:
            page = open_page(browser, base, size)
            page.click("#chatbtn")
            for i in range(questions):
                page.fill("#q", f"synthetic question {i}")
                page.click("#send")
            page.wait_for_selector("#log .msg")
            page.click("#chatclose")
            page.click("#chatbtn")
            page.wait_for_timeout(3200)  # longer than every pending answer
            assert page.locator("#log .msg").count() == 0, page.inner_text("#log")
            # the next conversation works as before
            page.fill("#q", "synthetic question after close")
            page.click("#send")
            page.wait_for_selector("#log .msg.a", timeout=10000)
            assert page.locator("#log .msg").count() == 2
            page.close()
    finally:
        model.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_a_stopped_support_keeps_the_available_forecast(browser, tmp_path, size):
    """CodeRabbit PR #16: a vasopressor started and stopped before the cut has no
    score by the task rule; the bed still has a forecast (Steady), not No estimate"""

    def edit(room):
        room[7]["p"]["vasopressor"] = None
        room[7]["stopped_before_cut"] = {
            "imv": False,
            "vasopressor": True,
            "crrt": False,
        }
        room[8]["p"]["vasopressor"] = None  # no score and no reason: unknown

    unit_files(tmp_path, edit)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, size)
        state = lambda n: page.get_attribute(  # noqa: E731
            f'button.bed[data-room="{n}"]', "data-state"
        )
        assert state(7) == "clear" and state(8) == "unknown"
        words = lambda n: " ".join(  # noqa: E731
            page.inner_text(f'button.bed[data-room="{n}"]').split()
        )
        assert "nothing new" in words(7) and "No estimate" not in words(7)
        assert "No estimate" in words(8) and "nothing new" not in words(8)
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_an_ended_slot_shows_no_vitals_from_the_room_before(browser, tmp_path, size):
    def edit(room):
        room[7]["vitals_12h"] = {"heart_rate": [{"h": h, "v": 80 + h} for h in (1, 2)]}
        room[8].update(present=False)

    unit_files(tmp_path, edit)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, size, "room=7&fast")
        page.wait_for_selector("#rv-vit:not([hidden])")
        page.evaluate("location.hash = 'room=8&fast'")
        page.wait_for_function(
            "document.getElementById('rv-risk-h').textContent"
            ".includes('Not in the ICU')"
        )
        assert page.is_hidden("#rv-vit")
        assert page.inner_html("#vits") == ""
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_machines_in_use_come_from_unit_counts_when_rooms_are_withheld(
    browser, tmp_path, size
):
    """a counts-only ward: no room records, 5 ventilators in use by the unit count,
    saved total 4. Never 4 free. The capacity POST sends the total and never a
    derived number free (PR 18); the server works out 0 free from its own count."""
    unit_files(tmp_path, lambda room: None)
    (tmp_path / "rooms.json").write_text(json.dumps({"rooms": [], "counts_only": True}))
    (tmp_path / "capacity.json").write_text(json.dumps({"vents_total": 4}))
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(
            browser, base, size, "view=strain&fast", wait="#sline:not([hidden])"
        )
        assert "Ventilators short by 1" in page.inner_text("body")
        page.click("#gear")
        page.fill("#cap-ls", "12")
        with page.expect_response(
            lambda r: r.url.endswith("/api/capacity") and r.request.method == "POST"
        ) as got:
            page.press("#cap-ls", "Enter")
        body = json.loads(got.value.request.post_data)
        assert body["vents_total"] == 4 and "vents_free" not in body, body
        assert got.value.json()["capacity"]["vents_free"] == 0
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_a_cleared_total_drops_the_free_count_derived_from_it(browser, tmp_path, size):
    """CodeRabbit PR 20 (second review): the forecast's yardstick carries 3
    ventilators free, worked out from a total that has since been cleared. The
    server's capacity is the source: no total and no stored number free, so no
    "Free 3". A number free that the server still stores is shown."""

    def files(capacity):
        unit_files(tmp_path, lambda room: None)
        fc = json.loads((tmp_path / "forecast.json").read_text())
        fc["yardstick"] = {
            **fc["yardstick"],
            "kind": "capacity",
            "capacity": {
                "life_support_patients": 12,
                "vents_free": 3,
                "set_at": "2026-11-14T07:00:00-06:00",
                "set_by_role": "ICU nurse",
            },
        }
        (tmp_path / "forecast.json").write_text(json.dumps(fc))
        (tmp_path / "capacity.json").write_text(json.dumps(capacity))

    def card_words():
        with running_board(tmp_path, static_path=PAGE) as base:
            page = open_page(browser, base, size, "view=strain&fast")
            words = " ".join(page.inner_text('article.wc[data-k="imv"]').split())
            page.close()
            return words

    files({"life_support_patients": 12})  # the total was cleared
    assert "Free 3" not in card_words()
    files({"life_support_patients": 12, "vents_free": 3})  # stored on the server
    assert "Free 3" in card_words()


@pytest.mark.parametrize("size", WIDTHS)
def test_a_refresh_updates_the_capacity_box_that_is_not_being_edited(
    browser, tmp_path, size
):
    """CodeRabbit PR 20 (second review): the ventilator box has focus while another
    device saves 5 CRRT machines. The CRRT box follows, so the next save does not
    send the old 3 back."""
    unit_files(tmp_path, lambda room: None)
    cap = tmp_path / "capacity.json"
    cap.write_text(json.dumps({"vents_total": 4, "crrt_total": 3}))
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, size, "view=strain&fast")
        page.click("#gear")
        page.wait_for_function("() => document.getElementById('cap-ct').value === '3'")
        page.focus("#cap-vt")
        page.fill("#cap-vt", "6")  # being edited: a refresh must leave it alone
        cap.write_text(json.dumps({"vents_total": 4, "crrt_total": 5}))
        page.wait_for_function(
            "() => document.getElementById('cap-ct').value === '5'", timeout=8000
        )
        assert page.input_value("#cap-vt") == "6"
        assert page.evaluate("document.activeElement.id") == "cap-vt"
        with page.expect_request(
            lambda r: r.url.endswith("/api/capacity") and r.method == "POST"
        ) as sent:
            page.press("#cap-vt", "Enter")
        body = json.loads(sent.value.post_data)
        assert (body["vents_total"], body["crrt_total"]) == (6, 5), body
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_attention_first_is_ordered_by_the_highest_flagged_chance(
    browser, tmp_path, size
):
    """The chat's "see first" list is ordered by each bed's highest chance of a new
    life support at its threshold. Death never ranks or marks a bed (D13), so a
    saved death line from an older page changes nothing. The built-in demo data."""
    unit_files(tmp_path, lambda room: None)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(
            browser, base, size, "synthetic&fast", {"lookahead-lines": {"death": 5}}
        )
        assert page.locator('#grid use[href="#i-death"]').count() == 0
        # each bed's highest shown chance, leaving the ICU aside ("<5%" reads as 4)
        top = page.evaluate(
            """() => Object.fromEntries(
              [...document.querySelectorAll('button.bed')].map(b => [
                b.dataset.room,
                Math.max(-1, ...[...b.querySelectorAll('.nextl .nx')]
                  .filter(x => !/leaving the ICU/.test(x.dataset.tip || ''))
                  .map(x => x.textContent.trim())
                  .map(t => t.startsWith('<') ? 4 : parseInt(t, 10)))]))"""
        )
        page.click("#chatbtn")
        page.fill("#q", "Which beds should we see first?")
        page.click("#send")
        page.wait_for_selector("#log .msg.a")
        answer = page.inner_text("#log .msg.a")
        assert "highest chance first" in answer, answer
        order = re.findall(r"bed (\d+)", answer.split("first:", 1)[1])
        chances = [top[n] for n in order]
        assert len(order) >= 3 and min(chances) >= 0, (order, chances)
        assert len({top[n] for n in order}) > 1  # a real ordering, not all ties
        assert chances == sorted(chances, reverse=True), list(zip(order, chances))
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_death_is_a_unit_count_and_see_first_names_the_top_beds(
    browser, tmp_path, size
):
    """J.C.'s decisions Q4/Q9 and Q6a: no death icon and no death flag on a bed
    tile; one unit count in the alert line; See first names Dema's top beds."""

    def edit(room):
        room[3]["p"]["death"] = 0.9  # very likely to die: still no mark on the tile
        room[5]["p"]["vasopressor"] = 0.6
        room[9]["p"]["imv"] = 0.5
        room[12]["p"]["crrt"] = 0.4

    unit_files(tmp_path, edit)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, size, "fast")
        tile = page.locator('button.bed[data-room="3"]')
        assert tile.get_attribute("data-state") == "clear"
        assert "hit" not in tile.get_attribute("class")
        assert "death" not in tile.get_attribute("aria-label").lower()
        assert page.locator('#grid use[href="#i-death"]').count() == 0
        assert "Deaths expected" in page.inner_text("#alerts")
        first = page.locator("#seefirst .sfb")
        assert [b.get_attribute("data-room") for b in first.all()] == ["5", "9", "12"]
        first.nth(0).click()
        page.wait_for_selector("#roomview:not([hidden])")
        assert "Dies in hospital" in page.inner_text(
            "#rv-risks"
        )  # death is in the pop-up
        # Escape closes one panel at a time: Settings first, then the bed
        page.evaluate("document.getElementById('gear').click()")
        page.keyboard.press("Escape")
        assert page.is_hidden("#setmenu") and page.is_visible("#roomview")
        page.keyboard.press("Escape")
        page.wait_for_selector("#roomview", state="hidden", timeout=3000)
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_no_failed_request_when_no_context_is_published(browser, tmp_path, size):
    """The page probes /api/context on every load; without a context the server
    answers 200 {"context_mode": false}, so nothing is logged as a failed request."""
    unit_files(tmp_path, lambda room: None)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = browser.new_page(viewport={"width": size[0], "height": size[1]})
        failed = []
        page.on(
            "response",
            lambda r: failed.append((r.status, r.url)) if r.status >= 400 else None,
        )
        page.on(
            "console", lambda m: failed.append(m.text) if m.type == "error" else None
        )
        page.goto(f"{base}/#fast")
        page.wait_for_selector('button.bed[data-room="1"]', state="attached")
        page.wait_for_timeout(600)
        assert failed == []
        page.close()


def test_an_update_shows_its_steps_then_updated(browser, tmp_path):
    """J.C.'s decision Q6b: Queued, Running on the GPU, Scoring, Done, then a short
    "Updated HH:MM"; a stopped run says so in plain words (built-in demo data)."""
    unit_files(tmp_path, lambda room: None)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(browser, base, WIDTHS[0], "synthetic&fast")
        page.click("#rerun")
        page.wait_for_selector("#runprog .steps li.is")
        steps = " ".join(page.locator("#runprog .steps li").all_inner_texts())
        for word in ("Queued", "Running on the GPU", "Scoring", "Done"):
            assert word in steps, steps
        page.wait_for_selector("#runprog .pg-h.ok", timeout=5000)
        assert re.search(r"Updated \d\d:\d\d", page.inner_text("#runprog"))
        page.wait_for_selector("#runprog", state="hidden", timeout=5000)
        page.close()
        page = open_page(browser, base, WIDTHS[0], "synthetic&fast&failrun")
        page.click("#rerun")
        page.wait_for_selector("#runprog .pg-h.bad", timeout=5000)
        words = page.inner_text("#runprog")
        assert "was stopped" in words and "still shown" in words, words
        page.click("#runprog .pg-x")
        assert page.is_hidden("#runprog")
        page.close()


class _FakeDispatcher:
    """a dispatcher whose /status follows a script: the page's progress strip reads
    running.state and stuck from it through GET /api/runs"""

    def __init__(self):
        self.status = {"running": None, "updating": False, "stuck": None}
        me = self

        class H(http.server.BaseHTTPRequestHandler):
            def _send(self, obj):
                data = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send({"next_scheduled": "2026-01-02T07:00", **me.status})

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self._send({"started": True, "name": "t7-forecast-unit-0101-0700"})

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def set(self, state=None, stuck=None):
        run = {"name": "t7-forecast-unit-0101-0700", "state": state} if state else None
        self.status = {"running": run, "updating": bool(run), "stuck": stuck}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_a_live_update_follows_the_dispatcher_and_ends_updated_or_stopped(
    browser, tmp_path
):
    """Served live, the strip's step comes from /api/runs: PENDING is Queued, any
    other running state is Running on the GPU, the job gone from the list is Scoring,
    and a new forecast file is "Updated HH:MM". A run the dispatcher stopped says so."""
    unit_files(tmp_path, lambda room: None)
    fake = _FakeDispatcher()
    current = lambda page: page.inner_text("#runprog .steps li.is")  # noqa: E731
    try:
        with running_board(tmp_path, dispatcher=fake.url, static_path=PAGE) as base:
            page = open_page(browser, base, WIDTHS[0], "fast")
            fake.set("PENDING")
            page.click("#rerun")
            page.wait_for_selector("#runprog .steps li.is")
            assert "Queued" in current(page)
            fake.set("STARTED")
            page.wait_for_selector(
                "#runprog .steps li.is:has-text('Running on the GPU')"
            )
            fake.set(None)
            page.wait_for_selector("#runprog .steps li.is:has-text('Scoring')")
            forecast = json.loads((tmp_path / "forecast.json").read_text())
            forecast["made_at"] = "2026-01-01T07:42:00"
            (tmp_path / "forecast.json").write_text(json.dumps(forecast))
            page.wait_for_selector("#runprog .pg-h.ok", timeout=5000)
            assert "Updated 07:42" in page.inner_text("#runprog")
            page.wait_for_selector("#runprog", state="hidden", timeout=5000)
            # a second run that waits for a GPU and is stopped by the dispatcher
            fake.set("PENDING")
            page.click("#rerun")
            page.wait_for_selector("#runprog .steps li.is")
            stopped = {
                "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "name": "t7-forecast-unit-0101-0700",
                "minutes": 5,
                "reason": "The update waited for a GPU for 5 minutes and was stopped.",
            }
            fake.set(None, stuck=stopped)
            page.wait_for_selector("#runprog .pg-h.bad", timeout=5000)
            words = page.inner_text("#runprog")
            assert "The update was stopped." in words, words
            assert "waited for a free GPU for 5 minutes" in words, words
            assert page.get_attribute("#rerun", "aria-disabled") == "false"
            page.close()
    finally:
        fake.close()

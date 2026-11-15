r"""The board page in a real browser (CodeRabbit PR #16, findings on the page).

The page is Dema's final board (D25): a bed has no trajectory word, so a fully
observed bed with nothing at its threshold reads "clear" (never "Steady"), and the
machine totals are the server's (capacity.json), not the device copy.

Skipped unless Playwright is installed:
    uv run --extra dev --extra model --with playwright \
        python -m pytest -q tests/test_page_browser.py
Synthetic data only (examples/). Each check runs at a desk and a phone width.
"""

import json
import pathlib
import re
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
    """CodeRabbit PR 20 (second review): "highest chance first" counts death too.
    The built-in demo data (#synthetic), with the death line at 5%."""
    unit_files(tmp_path, lambda room: None)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(
            browser, base, size, "synthetic&fast", {"lookahead-lines": {"death": 5}}
        )
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
        page.fill("#q", "Which beds need attention first?")
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

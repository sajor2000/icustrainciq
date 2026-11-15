r"""The board page in a real browser (CodeRabbit PR #16, findings on the page).

Skipped unless Playwright is installed:
    uv run --extra dev --extra model --with playwright \
        python -m pytest -q tests/test_page_browser.py
Synthetic data only (examples/). Each check runs at a desk and a phone width.
"""

import json
import pathlib
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


def open_page(browser, base, size, fragment="fast", storage=None):
    page = browser.new_page(viewport={"width": size[0], "height": size[1]})
    if storage:
        page.add_init_script(
            "".join(
                f"localStorage.setItem({json.dumps(k)}, {json.dumps(json.dumps(v))});"
                for k, v in storage.items()
            )
        )
    page.goto(f"{base}/#{fragment}")
    page.wait_for_selector('button.bed[data-room="1"]', state="attached")
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
        assert state(8) == "steady"  # the same chances, fully observed
        assert state(7) == "unknown"
        label = page.get_attribute('button.bed[data-room="7"]', "aria-label")
        assert "Steady" not in label and "No estimate" in label
        page.close()


@pytest.mark.parametrize("size", WIDTHS)
def test_machine_total_stays_when_use_exceeds_it(browser, tmp_path, size):
    def edit(room):
        for n in (1, 2, 3, 4, 5):  # five ventilators in use
            room[n]["on_now"]["imv"], room[n]["p"]["imv"] = True, None
        for n in (10, 11):  # two more beds flagged
            room[n]["p"]["imv"] = 0.6

    unit_files(tmp_path, edit)
    with running_board(tmp_path, static_path=PAGE) as base:
        page = open_page(  # the saved total is four
            browser,
            base,
            size,
            "view=strain&fast",
            {"lookahead-machines": {"imv": 4, "crrt": None}},
        )
        card = page.locator('article.wc[data-k="imv"]')
        bar = card.locator("svg.ubar")
        label = bar.get_attribute("aria-label")
        assert "5 in use now" in label and "4 in total" in label, label
        assert "over the total" in label
        assert "4 total" in bar.text_content()
        words = " ".join(card.inner_text().split())
        assert "free of 4 · 1 over" in words, words
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

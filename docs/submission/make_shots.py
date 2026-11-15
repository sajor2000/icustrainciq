"""Regenerate the one-sheet's screenshots and export the sheet.

    uv run --with playwright python docs/submission/make_shots.py          # shots + PDF + PNG
    uv run --with playwright python docs/submission/make_shots.py shots    # screenshots only
    uv run --with playwright python docs/submission/make_shots.py export   # PDF + PNG only

Screenshots come from mockups/command-center.html opened with #synthetic
(made-up patients generated on the page; no backend, no patient data).
First run on a new machine: uv run --with playwright playwright install chromium
"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
BOARD = (HERE.parent.parent / "mockups" / "command-center.html").as_uri()
IMG = HERE / "img"
SCALE = 3          # device pixels per CSS pixel: prints well above 300 dpi at the sizes used
PAD = 8            # CSS px of board ground kept around a crop, so card shadows are not cut


async def box(page, js):
    """Union rectangle (page coordinates) of the elements a JS expression returns."""
    return await page.evaluate(
        """(els) => { els = els.filter(Boolean); const r = els.map(e => e.getBoundingClientRect());
            const x0 = Math.min(...r.map(b => b.left)), y0 = Math.min(...r.map(b => b.top));
            const x1 = Math.max(...r.map(b => b.right)), y1 = Math.max(...r.map(b => b.bottom));
            return {x: x0 + scrollX, y: y0 + scrollY, width: x1 - x0, height: y1 - y0}; }""",
        await page.evaluate_handle(js),
    )


async def crop(page, name, js, pad=PAD, max_height=None):
    b = await box(page, js)
    clip = {"x": max(b["x"] - pad, 0), "y": max(b["y"] - pad, 0),
            "width": b["width"] + 2 * pad, "height": b["height"] + 2 * pad}
    if max_height:
        clip["height"] = min(clip["height"], max_height)
    await page.screenshot(path=str(IMG / f"{name}.png"), clip=clip, full_page=True)
    print(f"  {name}.png  {round(clip['width'])} x {round(clip['height'])} css px")


async def open_board(browser, width, hash_):
    ctx = await browser.new_context(viewport={"width": width, "height": 1000}, device_scale_factor=SCALE)
    page = await ctx.new_page()
    await page.goto(BOARD + hash_)
    await page.wait_for_selector("#grid button", state="attached")
    await page.add_style_tag(content="#chatbtn{visibility:hidden} *{transition:none!important;animation:none!important}")
    await page.wait_for_timeout(300)
    return ctx, page


async def shots(browser):
    IMG.mkdir(exist_ok=True)
    first3 = "[...document.querySelectorAll('#grid > *')].slice(0, 3)"
    # 940 px is the narrowest three-across layout where no name in these tiles is cut short

    # Bed board, Next 24 h: rooms 1 to 3
    ctx, page = await open_board(browser, 940, "#synthetic")
    await crop(page, "beds-next", first3)
    await ctx.close()

    # The header strain line with tonight's machines set: 6 ventilators, 3 CRRT machines, staffing covers 14
    # (capacity lives in the Settings panel; #settings opens it)
    ctx, page = await open_board(browser, 1280, "#synthetic&view=strain&settings")
    await page.fill("#cap-vt", "6")
    await page.fill("#cap-ct", "3")
    await page.fill("#cap-ls", "14")
    await page.click("#capform button[type=submit]")
    await page.wait_for_timeout(400)
    await page.click("#setclose")
    await page.wait_for_timeout(300)
    # one row on the sheet: the two small notes at the end of the line (who set the capacity, last run) are left out of this crop
    await page.add_style_tag(content="#alerts .capset,#runbadge{display:none!important}#alerts,#alerts .hi{flex-wrap:nowrap}#alerts>*,#alerts .albody>*{white-space:nowrap;flex:none}")
    await crop(page, "strain-line", "[document.getElementById('alerts')]", pad=5)
    # One event card on Unit strain: the top of the ventilator card (on now, free, predicted new, unit forecast, usage bar)
    await crop(page, "event-card", "[document.querySelector('.wc[data-k=\"imv\"]')]", pad=5, max_height=200)   # down to the usage bar
    await ctx.close()


async def export(browser):
    ctx = await browser.new_context(viewport={"width": 816, "height": 1056}, device_scale_factor=3)
    page = await ctx.new_page()
    await page.goto((HERE / "one-sheet.html").as_uri())
    await page.wait_for_load_state("networkidle")
    await page.emulate_media(media="print")
    await page.pdf(path=str(HERE / "one-sheet.pdf"), prefer_css_page_size=True, print_background=True)
    await page.screenshot(path=str(HERE / "one-sheet.png"), clip={"x": 0, "y": 0, "width": 816, "height": 1056})
    over = await page.evaluate("document.querySelector('.sheet').scrollHeight - document.querySelector('.sheet').clientHeight")
    print(f"  one-sheet.pdf, one-sheet.png  (content overflow: {over} px; must be 0)")
    await ctx.close()


async def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        if what in ("all", "shots"):
            print("screenshots:")
            await shots(browser)
        if what in ("all", "export"):
            print("export:")
            await export(browser)
        await browser.close()


asyncio.run(main())

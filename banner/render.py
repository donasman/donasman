"""banner.html을 라이트·다크 PNG로 렌더링한다. 실행: python banner/render.py"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
SRC = (HERE / "banner.html").resolve().as_uri()
OUT = HERE.parent / "assets"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome")
    page = browser.new_page(viewport={"width": 900, "height": 600}, device_scale_factor=2)
    for theme in ("light", "dark"):
        page.goto(SRC)
        page.evaluate("t => document.documentElement.dataset.theme = t", theme)
        page.wait_for_selector("body[data-ready='1']")
        page.evaluate("draw()")
        page.locator(".banner").screenshot(path=str(OUT / f"banner-{theme}.png"), omit_background=True)
        print("saved", OUT / f"banner-{theme}.png")
    browser.close()

"""Smoke-check the deployed public site in desktop and mobile Chromium.

Screenshots are CI artifacts, never published user files.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://roki0i.github.io/steam-research/"
SCREENSHOTS = Path("screenshots")
SCREENSHOTS.mkdir(exist_ok=True)


def check_desktop(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    errors = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    response = page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    assert response and response.status == 200, "Public site did not return HTTP 200"
    page.locator("#explorer").wait_for(state="visible", timeout=60000)
    assert page.locator("#game-count").inner_text().strip() == "1,000"
    assert page.locator("#games .game-button").count() > 0
    assert page.locator("#chart svg").count() == 1
    page.screenshot(path=str(SCREENSHOTS / "steam-desktop.png"), full_page=True)
    page.locator('#periods [data-period="12"]').click()
    assert page.locator('#periods [data-period="12"]').get_attribute("aria-pressed") == "true"

    page.locator("#open-import").click()
    page.locator("#monthly-file").set_input_files({
        "name": "smoke.csv",
        "mimeType": "text/csv",
        "buffer": b"appid,name,month,avg_players,peak_players\n730,PORTFOLIO CSV TEST,2026-10,20,30\n",
    })
    page.locator("#import-submit").click()
    page.locator("#game-title").get_by_text("PORTFOLIO CSV TEST", exact=True).wait_for(timeout=15000)
    assert "PORTFOLIO CSV TEST" in page.locator("#game-title").inner_text()
    page.screenshot(path=str(SCREENSHOTS / "steam-csv.png"), full_page=True)
    assert not errors, f"Browser JavaScript errors: {errors}"
    context.close()


def check_mobile(browser):
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=1,
        is_mobile=True,
        has_touch=True,
        color_scheme="dark",
    )
    errors = []
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.locator("#explorer").wait_for(state="visible", timeout=60000)
    assert page.locator("#game-count").inner_text().strip() == "1,000"
    overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow <= 12, f"Unexpected mobile horizontal overflow: {overflow}px"
    page.screenshot(path=str(SCREENSHOTS / "steam-mobile.png"), full_page=True)
    assert not errors, f"Mobile JavaScript errors: {errors}"
    context.close()


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            check_desktop(browser)
            check_mobile(browser)
            print("Production desktop/mobile smoke checks passed.")
        finally:
            browser.close()

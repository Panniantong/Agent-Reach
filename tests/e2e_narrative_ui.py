# -*- coding: utf-8 -*-
"""Browser acceptance flow for the local narrative workbench.

Run through the webapp-testing with_server helper; this file owns only Playwright logic.
"""

import os
from datetime import date
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("NARRATIVE_E2E_URL", "http://127.0.0.1:8137")
SCREENSHOT = os.environ.get("NARRATIVE_E2E_SCREENSHOT", "")


def main():
    browser_errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda error: browser_errors.append(str(error)))
        page.on(
            "console",
            lambda message: browser_errors.append(message.text)
            if message.type == "error"
            else None,
        )

        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")

        expect(page.locator('[role="tab"]')).to_have_count(8)
        expect(page.locator("#nr-health-text")).to_contain_text("QUANT")

        page.locator('[data-tab="company"]').click()
        expect(page.locator("#nr-ticker")).to_be_visible()
        page.locator("#nr-ticker").fill("NVDA")
        page.locator("#nr-company-form").evaluate("(form) => form.requestSubmit()")
        expect(page.get_by_text("EVIDENCE GRADE", exact=True)).to_be_visible()

        page.locator('[data-tab="inference"]').click()
        expect(page.locator("#nr-import-form")).to_be_visible()
        page.locator("#nr-import-domain").fill("information-technology")
        page.locator("#nr-import-ticker").fill("NVDA")
        page.locator("#nr-import-text").fill(
            "因為 AI 伺服器需求上升，NVDA 2027 年價格可能上漲，但這仍需要 Quant 數據支持。"
        )
        page.locator("#nr-import-form").evaluate("(form) => form.requestSubmit()")
        expect(page.locator(".nr-claim-keep")).to_be_visible(timeout=10_000)
        page.locator(".nr-claim-keep").first.click()
        expect(page.locator(".nr-claim-keep")).to_have_count(0)

        page.locator("#nr-statement").fill("NVDA 在結算日收盤高於 200")
        page.locator("#nr-resolution-date").fill("2027-06-30")
        page.locator("#nr-contract-domain").fill("information-technology")
        page.locator("#nr-criteria").fill('{"operator":"price_above","threshold":200}')
        page.locator("#nr-contract-form").evaluate("(form) => form.requestSubmit()")
        page.wait_for_function(
            "() => document.querySelector('#nr-forecast-contract').value.startsWith('evt_')"
        )

        page.locator("#nr-forecast-asof").fill(date.today().isoformat())
        page.locator("#nr-samples").fill("[]")
        page.locator("#nr-forecast-form").evaluate("(form) => form.requestSubmit()")
        expect(page.locator("#nr-console-log")).to_contain_text("局面校準 完成", timeout=15_000)

        page.locator('[data-tab="company"]').click()
        expect(page.get_by_text("資料不足", exact=True).first).to_be_visible(timeout=10_000)

        page.keyboard.press("Alt+8")
        expect(page.get_by_text("機率要接受結算，不接受文采。", exact=True)).to_be_visible()

        if SCREENSHOT:
            target = Path(SCREENSHOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target), full_page=True)

        browser.close()

    assert not browser_errors, "browser errors: " + " | ".join(browser_errors)


if __name__ == "__main__":
    main()

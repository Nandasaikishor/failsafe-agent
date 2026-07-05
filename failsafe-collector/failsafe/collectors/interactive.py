"""Interactive collector — executes browser actions on dynamically rendered pages."""

from __future__ import annotations

from failsafe.collectors.base import BaseCollector, CollectionResult
from failsafe.schema import InteractiveConfig
from failsafe.utils.clean import clean_text


class InteractiveCollector(BaseCollector):
    def execute(self, config: InteractiveConfig, **kwargs) -> CollectionResult:
        result = CollectionResult()

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result.errors.append("playwright not installed — run: pip install playwright && playwright install")
            return result

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(config.url, wait_until="networkidle")

                if config.wait_for_selector:
                    page.wait_for_selector(config.wait_for_selector, timeout=30000)

                for action in config.actions:
                    self._execute_action(page, action)

                if config.wait_for_selector:
                    page.wait_for_selector(config.wait_for_selector, timeout=10000)

                items = page.query_selector_all(config.result_selector)
                for item in items:
                    record = {}
                    for field_name, selector in config.field_selectors.items():
                        el = item.query_selector(selector)
                        if el:
                            record[field_name] = clean_text(el.inner_text())
                        else:
                            record[field_name] = ""
                    result.records.append(record)

                if config.screenshot:
                    result.metadata["screenshot"] = page.screenshot()

                browser.close()

        except Exception as e:
            result.errors.append(f"Interactive execution failed: {e}")

        result.metadata["url"] = config.url
        result.metadata["actions_count"] = len(config.actions)
        return result

    def _execute_action(self, page, action):
        if action.action == "click":
            page.click(action.selector)
        elif action.action == "type":
            page.fill(action.selector, action.value or "")
        elif action.action == "wait":
            page.wait_for_timeout(action.wait_ms)
        elif action.action == "scroll":
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif action.action == "select":
            page.select_option(action.selector, action.value)
        if action.wait_ms:
            page.wait_for_timeout(action.wait_ms)

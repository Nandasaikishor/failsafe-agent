"""List collector — traverses paginated list pages to discover detail-page links."""

from __future__ import annotations

from urllib.parse import urlencode

from failsafe.collectors.base import BaseCollector, CollectionResult
from failsafe.schema import ListConfig
from failsafe.utils.parse import extract_href, extract_text, select_elements
from failsafe.utils.request import RequestError, fetch_page, parse_html


class ListCollector(BaseCollector):
    def execute(self, config: ListConfig, **kwargs) -> CollectionResult:
        result = CollectionResult()
        rate_limit = kwargs.get("rate_limit", 1.0)

        for page_num in range(config.start_page, config.start_page + config.max_pages):
            url = self._build_page_url(config, page_num)
            try:
                html = fetch_page(url, rate_limit=rate_limit)
                soup = parse_html(html)

                items = select_elements(soup, config.item_selector)
                if not items:
                    break

                for item in items:
                    record = {}
                    title_el = item.select_one(config.title_selector)
                    link_el = item.select_one(config.link_selector)

                    record["title"] = extract_text(title_el)
                    link = extract_href(link_el, config.list_url)
                    record["url"] = link

                    if config.date_selector:
                        date_el = item.select_one(config.date_selector)
                        record["date"] = extract_text(date_el)

                    if link:
                        result.urls_discovered.append(link)
                    result.records.append(record)

                if not self._has_next_page(soup, config):
                    break

            except RequestError as e:
                result.errors.append(str(e))
                break

        result.metadata["pages_fetched"] = page_num - config.start_page + 1
        return result

    def _build_page_url(self, config: ListConfig, page_num: int) -> str:
        if page_num == config.start_page and not config.page_param:
            return config.list_url
        if config.page_param:
            base = config.list_url
            separator = "&" if "?" in base else "?"
            return f"{base}{separator}{urlencode({config.page_param: str(page_num)})}"
        return config.list_url

    def _has_next_page(self, soup, config: ListConfig) -> bool:
        if config.next_page_selector:
            return soup.select_one(config.next_page_selector) is not None
        return config.page_param is not None

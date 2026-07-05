"""Search collector — discovers candidate URLs by keyword from search entry points."""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

from failsafe.collectors.base import BaseCollector, CollectionResult
from failsafe.schema import SearchConfig
from failsafe.utils.parse import extract_href, extract_text, select_elements
from failsafe.utils.request import RequestError, fetch_page, parse_html


class SearchCollector(BaseCollector):
    def execute(self, config: SearchConfig, **kwargs) -> CollectionResult:
        result = CollectionResult()
        rate_limit = kwargs.get("rate_limit", 1.0)

        for keyword in config.keywords:
            pages_fetched = 0
            current_url = self._build_search_url(config, keyword)

            while current_url and pages_fetched < config.max_pages:
                try:
                    html = fetch_page(current_url, rate_limit=rate_limit)
                    soup = parse_html(html)

                    items = select_elements(soup, config.result_selector)
                    for item in items:
                        title_el = item.select_one(config.title_selector)
                        link_el = item.select_one(config.link_selector)

                        title = extract_text(title_el)
                        link = extract_href(link_el, config.search_url)

                        if link:
                            result.records.append({"title": title, "url": link, "keyword": keyword})
                            result.urls_discovered.append(link)

                    current_url = self._get_next_page(soup, config, current_url)
                    pages_fetched += 1
                except RequestError as e:
                    result.errors.append(str(e))
                    break

        result.metadata["keywords"] = config.keywords
        result.metadata["pages_fetched"] = pages_fetched
        return result

    def _build_search_url(self, config: SearchConfig, keyword: str) -> str:
        base = config.search_url
        separator = "&" if "?" in base else "?"
        return f"{base}{separator}{urlencode({config.keyword_param: keyword})}"

    def _get_next_page(self, soup, config: SearchConfig, current_url: str) -> Optional[str]:
        if not config.next_page_selector:
            return None
        next_el = soup.select_one(config.next_page_selector)
        if next_el:
            return extract_href(next_el, config.search_url)
        return None

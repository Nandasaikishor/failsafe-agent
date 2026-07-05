"""Detail collector — extracts structured fields from a single detail page."""

from __future__ import annotations

from failsafe.collectors.base import BaseCollector, CollectionResult
from failsafe.schema import DetailConfig
from failsafe.utils.clean import clean_text, parse_date
from failsafe.utils.parse import extract_fields_from_page, extract_href, select_elements
from failsafe.utils.request import RequestError, fetch_page, parse_html


class DetailCollector(BaseCollector):
    def execute(self, config: DetailConfig, **kwargs) -> CollectionResult:
        result = CollectionResult()
        urls = kwargs.get("urls", [])
        rate_limit = kwargs.get("rate_limit", 1.0)

        if not urls and config.url_pattern:
            urls = [config.url_pattern]

        for url in urls:
            try:
                html = fetch_page(url, rate_limit=rate_limit, encoding=config.encoding)
                soup = parse_html(html)

                record = extract_fields_from_page(soup, config.field_selectors, url)

                for field_name, value in record.items():
                    record[field_name] = clean_text(value)

                if config.content_selector:
                    content_el = soup.select_one(config.content_selector)
                    if content_el:
                        record["content"] = clean_text(content_el.get_text(separator="\n"))

                if config.attachment_selector:
                    attachments = select_elements(soup, config.attachment_selector)
                    record["attachments"] = [
                        extract_href(a, url) for a in attachments if extract_href(a, url)
                    ]

                if config.date_format:
                    for field_name in ("date", "publish_date", "time", "timestamp"):
                        if field_name in record and record[field_name]:
                            record[field_name] = parse_date(
                                record[field_name], config.date_format
                            ) or record[field_name]

                record["source_url"] = url
                result.records.append(record)

            except RequestError as e:
                result.errors.append(f"{url}: {e}")

        result.metadata["urls_processed"] = len(urls)
        return result

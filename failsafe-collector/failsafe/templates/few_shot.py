"""Few-shot example retrieval for the instantiation agent.

Examples are retrieved by collector type and task similarity.
"""

from __future__ import annotations

from failsafe.schema import CollectorType

FEW_SHOT_EXAMPLES: dict[CollectorType, list[dict]] = {
    CollectorType.SEARCH: [
        {
            "description": "Search for news articles about AI regulation",
            "config": {
                "search_url": "https://example-news.com/search",
                "keyword_param": "q",
                "keywords": ["AI regulation", "artificial intelligence policy"],
                "result_selector": ".search-result-item",
                "title_selector": "h3.result-title",
                "link_selector": "a.result-link",
                "next_page_selector": "a.next-page",
                "max_pages": 3,
            },
        }
    ],
    CollectorType.LIST: [
        {
            "description": "Collect announcements from a government page",
            "config": {
                "list_url": "https://example-gov.org/announcements",
                "item_selector": ".announcement-item",
                "title_selector": ".item-title a",
                "link_selector": ".item-title a",
                "date_selector": ".item-date",
                "page_param": "page",
                "start_page": 1,
                "max_pages": 5,
            },
        }
    ],
    CollectorType.DETAIL: [
        {
            "description": "Extract article details from a news page",
            "config": {
                "field_selectors": {
                    "title": "h1.article-title",
                    "author": ".author-name",
                    "date": "time.published-date",
                    "body": "article.content",
                },
                "content_selector": "article.content",
                "attachment_selector": "a.attachment-link",
                "date_format": "%Y-%m-%d",
            },
        }
    ],
    CollectorType.API: [
        {
            "description": "Fetch product data from a REST API",
            "config": {
                "endpoint_url": "https://api.example.com/v1/products",
                "method": "GET",
                "params": {"limit": 50, "sort": "created_at"},
                "pagination_type": "offset",
                "pagination_param": "offset",
                "data_path": "$.data.products",
                "field_mappings": {
                    "name": "product_name",
                    "price": "unit_price",
                    "category": "category.name",
                },
                "max_pages": 5,
            },
        }
    ],
    CollectorType.INTERACTIVE: [
        {
            "description": "Collect data from a dynamically loaded table",
            "config": {
                "url": "https://example.com/data-table",
                "actions": [
                    {"action": "click", "selector": "#load-data-btn", "wait_ms": 2000},
                    {"action": "scroll", "wait_ms": 1000},
                ],
                "result_selector": "table.data-table tbody tr",
                "field_selectors": {
                    "name": "td:nth-child(1)",
                    "value": "td:nth-child(2)",
                    "date": "td:nth-child(3)",
                },
                "wait_for_selector": "table.data-table",
            },
        }
    ],
    CollectorType.FILE: [
        {
            "description": "Parse a financial report Excel file",
            "config": {
                "file_url": "https://example.com/reports/q4-2024.xlsx",
                "file_type": "xlsx",
                "sheet_name": "Summary",
                "start_row": 2,
                "header_row": 1,
                "field_mappings": {
                    "metric": "Metric Name",
                    "value": "Q4 Value",
                    "change": "YoY Change",
                },
            },
        }
    ],
}


def get_examples(collector_type: CollectorType) -> list[dict]:
    return FEW_SHOT_EXAMPLES.get(collector_type, [])

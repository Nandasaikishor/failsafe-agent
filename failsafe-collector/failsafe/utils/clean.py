"""Pre-built cleaning utility functions.

Deterministic data cleaning and normalization.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def clean_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = strip_html(text)
    text = normalize_whitespace(text)
    return text


def parse_date(text: str, fmt: Optional[str] = None) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    if fmt:
        try:
            dt = datetime.strptime(text, fmt)
            return dt.isoformat()
        except ValueError:
            pass

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%Y%m%d",
    ]
    for f in formats:
        try:
            dt = datetime.strptime(text, f)
            return dt.isoformat()
        except ValueError:
            continue
    return text


def deduplicate_records(
    records: list[dict[str, Any]], key_fields: Optional[List[str]] = None
) -> list[dict[str, Any]]:
    if not records:
        return []
    if not key_fields:
        key_fields = list(records[0].keys())
    seen = set()
    unique = []
    for record in records:
        key = tuple(str(record.get(f, "")) for f in key_fields)
        if key not in seen:
            seen.add(key)
            unique.append(record)
    return unique


def truncate_field(value: str, max_length: int = 10000) -> str:
    if len(value) <= max_length:
        return value
    return value[:max_length] + "..."


def normalize_url(url: str, base_url: str = "") -> str:
    url = url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = base_url.rstrip("/") + url
    elif not url.startswith(("http://", "https://")):
        url = base_url.rstrip("/") + "/" + url
    return url


def filter_empty_records(
    records: list[dict[str, Any]], min_non_empty: int = 1
) -> list[dict[str, Any]]:
    result = []
    for record in records:
        non_empty = sum(1 for v in record.values() if v is not None and str(v).strip())
        if non_empty >= min_non_empty:
            result.append(record)
    return result

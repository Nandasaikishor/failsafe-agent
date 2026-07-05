"""Pre-built request utility functions.

These are the deterministic, reusable request functions that templates invoke
at execution time — no LLM tokens consumed here.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
from bs4 import BeautifulSoup


class RequestError(Exception):
    pass


def fetch_page(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 30.0,
    rate_limit: float = 1.0,
    encoding: Optional[str] = None,
) -> str:
    time.sleep(rate_limit)
    default_headers = {
        "User-Agent": "FailsafeCollector/0.1 (research; +https://github.com/failsafe-collector)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if headers:
        default_headers.update(headers)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=default_headers)
            resp.raise_for_status()
            if encoding:
                resp.encoding = encoding
            return resp.text
    except httpx.HTTPStatusError as e:
        raise RequestError(f"HTTP {e.response.status_code} for {url}") from e
    except httpx.RequestError as e:
        raise RequestError(f"Request failed for {url}: {e}") from e


def fetch_json(
    url: str,
    *,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
    rate_limit: float = 1.0,
) -> Any:
    time.sleep(rate_limit)
    default_headers = {
        "User-Agent": "FailsafeCollector/0.1",
        "Accept": "application/json",
    }
    if headers:
        default_headers.update(headers)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.request(
                method, url, headers=default_headers, params=params, json=body
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise RequestError(f"HTTP {e.response.status_code} for {url}") from e
    except httpx.RequestError as e:
        raise RequestError(f"Request failed for {url}: {e}") from e


def fetch_binary(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 60.0,
    rate_limit: float = 1.0,
) -> bytes:
    time.sleep(rate_limit)
    default_headers = {"User-Agent": "FailsafeCollector/0.1"}
    if headers:
        default_headers.update(headers)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers=default_headers)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as e:
        raise RequestError(f"HTTP {e.response.status_code} for {url}") from e
    except httpx.RequestError as e:
        raise RequestError(f"Request failed for {url}: {e}") from e


def check_robots_txt(base_url: str, path: str = "/") -> bool:
    try:
        robots_url = base_url.rstrip("/") + "/robots.txt"
        text = fetch_page(robots_url, rate_limit=0)
        for line in text.splitlines():
            line = line.strip().lower()
            if line.startswith("disallow:"):
                disallowed = line.split(":", 1)[1].strip()
                if disallowed and path.startswith(disallowed):
                    return False
        return True
    except RequestError:
        return True


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")

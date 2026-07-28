"""Fetches recent news headlines for a symbol — the raw input to sentiment scoring.

`GoogleNewsRssProvider` scrapes Google News' public RSS search feed
rather than a JS-rendered finance page: modern finance sites (Yahoo
Finance included) render their news lists client-side, so a plain HTTP
GET + HTML parse would come back empty. RSS is server-rendered XML meant
for exactly this kind of consumption, so it's the more reliable "simple
scraping" target — no headless browser, no API key, no cost.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Callable
from urllib.parse import quote

_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
_DEFAULT_TIMEOUT_SECONDS = 10


class NewsProvider(ABC):
    """Source of recent headline text for a symbol."""

    @abstractmethod
    def get_headlines(self, symbol: str, limit: int = 10) -> list[str]:
        raise NotImplementedError


def _default_fetch(url: str) -> str:
    import requests  # local import: avoid the import cost when a fake fetcher is injected

    response = requests.get(url, timeout=_DEFAULT_TIMEOUT_SECONDS, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.text


class GoogleNewsRssProvider(NewsProvider):
    """Scrapes Google News' RSS search feed for `"{symbol} stock"`."""

    def __init__(self, fetch: Callable[[str], str] | None = None) -> None:
        self._fetch = fetch or _default_fetch

    def get_headlines(self, symbol: str, limit: int = 10) -> list[str]:
        query = quote(f"{symbol} stock")
        url = _RSS_URL.format(query=query)

        xml_text = self._fetch(url)
        if not xml_text:
            return []

        root = ET.fromstring(xml_text)
        titles = [item.findtext("title") for item in root.findall(".//item")]
        return [title for title in titles if title][:limit]

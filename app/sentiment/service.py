"""Combines a `NewsProvider` and `SentimentAnalyzer` behind a short-TTL cache.

Mirrors `app.data.cache.CachedMarketDataProvider`'s latest-price cache:
scraping + scoring a symbol on every single signal check within one scan
cycle would be wasteful and slow, so results are reused for
`cache_ttl_seconds`. Scraping failures (network errors, malformed feed,
a symbol with no news) are swallowed and logged rather than propagated —
sentiment is an optional confirmation signal, not something that should
ever block a strategy from running.
"""

from __future__ import annotations

import time

from app.models.domain import SentimentScore
from app.sentiment.analyzer import SentimentAnalyzer
from app.sentiment.news_provider import NewsProvider
from app.utils.logging_config import get_logger

logger = get_logger("app")


class SentimentService:
    def __init__(
        self,
        provider: NewsProvider,
        analyzer: SentimentAnalyzer,
        headline_limit: int = 10,
        cache_ttl_seconds: float = 1800.0,
    ) -> None:
        self._provider = provider
        self._analyzer = analyzer
        self._headline_limit = headline_limit
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[SentimentScore, float]] = {}

    def get_sentiment(self, symbol: str) -> SentimentScore | None:
        """Returns `None` if scraping/scoring fails -- callers should treat that as "unknown", not bearish."""
        cached = self._cache.get(symbol)
        now = time.monotonic()
        if cached is not None and now - cached[1] < self._cache_ttl_seconds:
            return cached[0]

        try:
            headlines = self._provider.get_headlines(symbol, self._headline_limit)
            score = self._analyzer.analyze(symbol, headlines)
        except Exception:
            logger.exception("Failed to compute sentiment for %s", symbol)
            return None

        self._cache[symbol] = (score, now)
        return score

"""Dependency-injection wiring for the sentiment stack.

Mirrors `app.data.factory.build_market_data_provider`: this is the one
place that decides which `NewsProvider`/`SentimentAnalyzer` are actually
used, so callers depend only on `SentimentService`.
"""

from __future__ import annotations

from app.config.settings import Settings
from app.sentiment.analyzer import VaderSentimentAnalyzer
from app.sentiment.news_provider import GoogleNewsRssProvider
from app.sentiment.service import SentimentService


def build_sentiment_service(settings: Settings) -> SentimentService:
    return SentimentService(
        provider=GoogleNewsRssProvider(),
        analyzer=VaderSentimentAnalyzer(),
        headline_limit=settings.sentiment_headline_limit,
        cache_ttl_seconds=settings.sentiment_cache_ttl_seconds,
    )

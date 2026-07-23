"""Dependency-injection wiring for the market data stack.

This is the one place that decides "which `MarketDataProvider` do we
actually use" — currently always `YFinanceProvider` wrapped in
`CachedMarketDataProvider`. Callers (the scheduler, backtester, manual
scripts) depend on the `MarketDataProvider` interface and get a concrete,
cached instance from here rather than constructing `YFinanceProvider`
themselves.
"""

from __future__ import annotations

from app.config.settings import Settings
from app.data.base import MarketDataProvider
from app.data.cache import CachedMarketDataProvider
from app.data.yfinance_provider import YFinanceProvider


def build_market_data_provider(settings: Settings) -> MarketDataProvider:
    return CachedMarketDataProvider(
        provider=YFinanceProvider(),
        cache_dir=settings.cache_dir,
        latest_price_ttl_seconds=settings.latest_price_cache_ttl_seconds,
    )

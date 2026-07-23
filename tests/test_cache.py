import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from app.data.base import MarketDataProvider
from app.data.cache import CachedMarketDataProvider


class _CountingProvider(MarketDataProvider):
    """Counts calls so tests can assert the cache actually avoided a refetch."""

    def __init__(self) -> None:
        self.history_calls = 0
        self.price_calls = 0

    def get_history(self, symbol: str, start: datetime, end: datetime, interval: str = "1d") -> pd.DataFrame:
        self.history_calls += 1
        return pd.DataFrame(
            {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [100]},
            index=[start],
        )

    def get_latest_price(self, symbol: str) -> float:
        self.price_calls += 1
        return 100.0 + self.price_calls


def test_get_history_caches_completed_historical_ranges(tmp_path: Path) -> None:
    inner = _CountingProvider()
    cache = CachedMarketDataProvider(inner, cache_dir=tmp_path)

    start, end = datetime(2020, 1, 1), datetime(2020, 1, 31)
    first = cache.get_history("AAPL", start, end)
    second = cache.get_history("AAPL", start, end)

    assert inner.history_calls == 1
    pd.testing.assert_frame_equal(first, second)


def test_get_history_does_not_cache_ranges_that_include_today(tmp_path: Path) -> None:
    inner = _CountingProvider()
    cache = CachedMarketDataProvider(inner, cache_dir=tmp_path)

    start, end = datetime.now() - timedelta(days=5), datetime.now()
    cache.get_history("AAPL", start, end)
    cache.get_history("AAPL", start, end)

    assert inner.history_calls == 2


def test_different_symbols_are_cached_separately(tmp_path: Path) -> None:
    inner = _CountingProvider()
    cache = CachedMarketDataProvider(inner, cache_dir=tmp_path)

    start, end = datetime(2020, 1, 1), datetime(2020, 1, 31)
    cache.get_history("AAPL", start, end)
    cache.get_history("MSFT", start, end)

    assert inner.history_calls == 2


def test_get_latest_price_is_cached_within_ttl(tmp_path: Path) -> None:
    inner = _CountingProvider()
    cache = CachedMarketDataProvider(inner, cache_dir=tmp_path, latest_price_ttl_seconds=60)

    first = cache.get_latest_price("AAPL")
    second = cache.get_latest_price("AAPL")

    assert first == second
    assert inner.price_calls == 1


def test_get_latest_price_refetches_after_ttl_expires(tmp_path: Path) -> None:
    inner = _CountingProvider()
    cache = CachedMarketDataProvider(inner, cache_dir=tmp_path, latest_price_ttl_seconds=0.01)

    first = cache.get_latest_price("AAPL")
    time.sleep(0.02)
    second = cache.get_latest_price("AAPL")

    assert first != second
    assert inner.price_calls == 2


def test_price_cache_is_independent_per_symbol(tmp_path: Path) -> None:
    inner = _CountingProvider()
    cache = CachedMarketDataProvider(inner, cache_dir=tmp_path, latest_price_ttl_seconds=60)

    cache.get_latest_price("AAPL")
    cache.get_latest_price("MSFT")

    assert inner.price_calls == 2

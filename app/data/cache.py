"""Caching decorator for any `MarketDataProvider`.

`CachedMarketDataProvider` wraps another provider rather than replacing
it: strategies, the execution engine, and the backtester still just see
a `MarketDataProvider`, so caching can be added, tuned, or removed
without touching anything above this layer or baking caching concerns
into vendor-specific code like `YFinanceProvider`.

Two independent caches are kept:
  - Historical OHLCV ranges are cached to disk as Parquet, keyed by
    (symbol, interval, start, end). Only *completed* ranges (entirely in
    the past) are cached — a range that includes "today" could still be
    growing an in-progress bar, so it's always fetched fresh.
  - The latest price is cached in memory for a short TTL, so a scan that
    checks the same symbol multiple times in one cycle doesn't refetch
    it repeatedly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.data.base import MarketDataProvider


@dataclass(slots=True)
class CachedMarketDataProvider(MarketDataProvider):
    provider: MarketDataProvider
    cache_dir: Path
    latest_price_ttl_seconds: float = 60.0

    _price_cache: dict[str, tuple[float, float]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        is_completed_range = end < datetime.now()
        cache_path = self._history_path(symbol, interval, start, end)

        if is_completed_range and cache_path.exists():
            return pd.read_parquet(cache_path)

        data = self.provider.get_history(symbol, start, end, interval)
        if is_completed_range and not data.empty:
            data.to_parquet(cache_path)
        return data

    def get_latest_price(self, symbol: str) -> float:
        cached = self._price_cache.get(symbol)
        now = time.monotonic()
        if cached is not None and now - cached[1] < self.latest_price_ttl_seconds:
            return cached[0]

        price = self.provider.get_latest_price(symbol)
        self._price_cache[symbol] = (price, now)
        return price

    def _history_path(self, symbol: str, interval: str, start: datetime, end: datetime) -> Path:
        filename = f"{symbol}_{interval}_{start:%Y%m%dT%H%M%S}_{end:%Y%m%dT%H%M%S}.parquet"
        return self.cache_dir / filename

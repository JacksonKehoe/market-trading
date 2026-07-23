"""Shared test fixtures/doubles."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.data.base import MarketDataProvider


class FakeMarketDataProvider(MarketDataProvider):
    """An in-memory `MarketDataProvider` double — no network access."""

    def __init__(self, prices: dict[str, float]) -> None:
        self._prices = dict(prices)

    def get_history(
        self, symbol: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> pd.DataFrame:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    def get_latest_price(self, symbol: str) -> float:
        return self._prices[symbol]

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price


def make_price_frame(closes: list[float], start: str = "2026-01-01") -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of closing prices.

    Open/high/low are set equal to close and volume is constant — these
    indicator/strategy tests only care about the `close` column, so the
    other columns just need to satisfy the OHLCV shape.
    """
    index = pd.date_range(start, periods=len(closes), freq="D")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1_000] * len(closes),
        },
        index=index,
    )

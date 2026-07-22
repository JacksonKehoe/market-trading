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

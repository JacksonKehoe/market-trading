"""Market data provider interface.

Design intent: strategies, the backtester, and the execution engine all
ask for price data through this interface rather than calling yfinance
(or any other vendor) directly. That makes it possible to swap or combine
data sources later (a paid real-time feed, a crypto exchange, etc.)
without touching any code above this layer, and makes strategies testable
against fixture DataFrames with no network access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class MarketDataProvider(ABC):
    """Base class for all market data sources."""

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Return OHLCV history for `symbol` between `start` and `end`.

        Must return a DataFrame indexed by timestamp with at least the
        columns: open, high, low, close, volume.
        """
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        """Return the most recent available price for `symbol`."""
        raise NotImplementedError

    def get_latest_prices(self, symbols: list[str]) -> dict[str, float]:
        """Convenience helper: latest price for many symbols at once.

        Default implementation just loops; providers with a bulk-quote API
        should override this for efficiency.
        """
        return {symbol: self.get_latest_price(symbol) for symbol in symbols}

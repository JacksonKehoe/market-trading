"""`MarketDataProvider` backed by Yahoo Finance via the free `yfinance` package.

No API key is required, and this module makes no brokerage calls of any
kind — it only reads public market data. `yfinance` is injected (defaulting
to the real package, imported lazily) so tests can substitute a fake
module and run with zero network access.
"""

from __future__ import annotations

from datetime import datetime
from types import ModuleType
from typing import Any

import pandas as pd

from app.data.base import MarketDataProvider

_COLUMNS = ["open", "high", "low", "close", "volume"]
_COLUMN_MAP = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}


class YFinanceProvider(MarketDataProvider):
    """Fetches historical and latest-price data for US equities and ETFs."""

    def __init__(self, yf_module: ModuleType | Any | None = None) -> None:
        if yf_module is None:
            import yfinance as yf_module  # local import: avoid the import cost when unused
        self._yf = yf_module

    def get_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        raw = self._yf.Ticker(symbol).history(start=start, end=end, interval=interval, auto_adjust=True)
        if raw.empty:
            return pd.DataFrame(columns=_COLUMNS)
        return raw.rename(columns=_COLUMN_MAP)[_COLUMNS]

    def get_latest_price(self, symbol: str) -> float:
        ticker = self._yf.Ticker(symbol)

        try:
            price = ticker.fast_info["last_price"]
            if price is not None:
                return float(price)
        except Exception:
            pass  # fast_info can be unavailable for some symbols/versions; fall back below

        history = ticker.history(period="1d", interval="1d")
        if history.empty:
            raise ValueError(f"No price data available for {symbol!r}")
        return float(history["Close"].iloc[-1])

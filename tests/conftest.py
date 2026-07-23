"""Shared test fixtures/doubles."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.data.base import MarketDataProvider
from app.database.engine import Base
from app.database.repository import SqlTradeRepository


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


class FakeHistoricalMarketDataProvider(MarketDataProvider):
    """Serves preset historical OHLCV DataFrames — for backtest-style tests.

    Unlike `FakeMarketDataProvider` (always-empty history, fixed live
    price), this one actually has history to replay: `get_latest_price`
    returns the last close in the stored frame.
    """

    def __init__(self, history: dict[str, pd.DataFrame]) -> None:
        self._history = history

    def get_history(
        self, symbol: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> pd.DataFrame:
        data = self._history.get(symbol, pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
        return data.loc[start:end]

    def get_latest_price(self, symbol: str) -> float:
        data = self._history.get(symbol)
        if data is None or data.empty:
            raise ValueError(f"No data available for {symbol!r}")
        return float(data["close"].iloc[-1])


def build_test_repository(db_path: Path) -> SqlTradeRepository:
    """A `SqlTradeRepository` backed by a throwaway SQLite file — for tests
    that need real persistence (not a fake) without touching the real DB."""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return SqlTradeRepository(sessionmaker(bind=engine, expire_on_commit=False))


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

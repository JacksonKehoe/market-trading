"""Strategy interface — the contract every trading strategy must satisfy.

Design intent: a Strategy is a pure function of price history. It receives
OHLCV data for one symbol and returns a Signal (BUY/SELL/HOLD). It must
NOT read or write the database, place orders, know about the portfolio,
or have any other side effect. That separation is what lets strategies be
unit-tested with a plain DataFrame and reused unchanged in backtesting,
paper trading, and (eventually) live trading.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from app.models.domain import Signal


class Strategy(ABC):
    """Base class for all interchangeable strategy plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """A short, unique, human-readable identifier (e.g. 'sma_crossover_20_50')."""

    @abstractmethod
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        """Evaluate `data` (OHLCV, indexed by timestamp, ascending) and return one Signal.

        Implementations should be stateless between calls where possible;
        any lookback window they need must come out of `data` itself.
        """
        raise NotImplementedError

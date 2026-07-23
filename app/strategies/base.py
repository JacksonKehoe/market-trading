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
from datetime import datetime

import pandas as pd

from app.models.domain import Signal
from app.models.enums import SignalType


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

    def _hold(self, symbol: str, timestamp: datetime, price: float, reason: str) -> Signal:
        """Shared helper for the common "no action" case (e.g. still warming up)."""
        return Signal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            timestamp=timestamp,
            price=price,
            strategy_name=self.name,
            reason=reason,
        )

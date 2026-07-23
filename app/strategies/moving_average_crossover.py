"""Moving Average Crossover strategy.

BUY when the fast SMA crosses above the slow SMA; SELL when it crosses
back below. "Crosses" means the relationship actually flipped between the
previous bar and the current one — not just "fast is currently above
slow" — so the signal fires once at the crossover event rather than on
every bar of an ongoing trend.
"""

from __future__ import annotations

import pandas as pd

from app.indicators.moving_average import sma
from app.models.domain import Signal
from app.models.enums import SignalType
from app.strategies.base import Strategy


class MovingAverageCrossoverStrategy(Strategy):
    def __init__(self, fast_window: int = 20, slow_window: int = 50) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        self.fast_window = fast_window
        self.slow_window = slow_window

    @property
    def name(self) -> str:
        return f"sma_crossover_{self.fast_window}_{self.slow_window}"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        if data.empty:
            raise ValueError(f"Cannot generate a signal for {symbol!r} from empty data")

        timestamp = data.index[-1]
        price = float(data["close"].iloc[-1])

        # One extra bar is needed beyond the slow window to compare "before" vs "after".
        if len(data) < self.slow_window + 1:
            return self._hold(symbol, timestamp, price, "Not enough history for the slow moving average")

        fast_ma = sma(data["close"], self.fast_window)
        slow_ma = sma(data["close"], self.slow_window)
        fast_prev, fast_curr = fast_ma.iloc[-2], fast_ma.iloc[-1]
        slow_prev, slow_curr = slow_ma.iloc[-2], slow_ma.iloc[-1]

        if pd.isna(fast_prev) or pd.isna(slow_prev):
            return self._hold(symbol, timestamp, price, "Not enough history for the slow moving average")

        if fast_prev <= slow_prev and fast_curr > slow_curr:
            reason = f"{self.fast_window}-SMA crossed above {self.slow_window}-SMA"
            return Signal(symbol, SignalType.BUY, timestamp, price, self.name, reason)

        if fast_prev >= slow_prev and fast_curr < slow_curr:
            reason = f"{self.fast_window}-SMA crossed below {self.slow_window}-SMA"
            return Signal(symbol, SignalType.SELL, timestamp, price, self.name, reason)

        return self._hold(symbol, timestamp, price, "No crossover")

"""MACD crossover strategy.

BUY when the MACD line crosses above its signal line; SELL when it
crosses back below.
"""

from __future__ import annotations

import pandas as pd

from app.indicators.macd import macd
from app.models.domain import Signal
from app.models.enums import SignalType
from app.strategies.base import Strategy


class MacdStrategy(Strategy):
    def __init__(self, fast: int = 12, slow: int = 26, signal_window: int = 9) -> None:
        if fast >= slow:
            raise ValueError("fast window must be smaller than slow window")
        self.fast = fast
        self.slow = slow
        self.signal_window = signal_window

    @property
    def name(self) -> str:
        return f"macd_{self.fast}_{self.slow}_{self.signal_window}"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        if data.empty:
            raise ValueError(f"Cannot generate a signal for {symbol!r} from empty data")

        timestamp = data.index[-1]
        price = float(data["close"].iloc[-1])

        # The slow EMA must warm up, then the signal line (EMA of MACD) warms up on top of that,
        # plus one extra bar to compare "before" vs "after".
        if len(data) < self.slow + self.signal_window + 1:
            return self._hold(symbol, timestamp, price, "Not enough history for MACD")

        macd_df = macd(data["close"], self.fast, self.slow, self.signal_window)
        macd_prev, macd_curr = macd_df["macd"].iloc[-2], macd_df["macd"].iloc[-1]
        signal_prev, signal_curr = macd_df["signal"].iloc[-2], macd_df["signal"].iloc[-1]

        if pd.isna(macd_prev) or pd.isna(signal_prev) or pd.isna(macd_curr) or pd.isna(signal_curr):
            return self._hold(symbol, timestamp, price, "Not enough history for MACD")

        if macd_prev <= signal_prev and macd_curr > signal_curr:
            return Signal(symbol, SignalType.BUY, timestamp, price, self.name, "MACD crossed above signal line")

        if macd_prev >= signal_prev and macd_curr < signal_curr:
            return Signal(symbol, SignalType.SELL, timestamp, price, self.name, "MACD crossed below signal line")

        return self._hold(symbol, timestamp, price, "No crossover")

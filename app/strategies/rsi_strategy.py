"""RSI mean-reversion strategy.

BUY when RSI crosses back up through the oversold threshold (a bounce
off an oversold condition); SELL when it crosses back down through the
overbought threshold. As with the crossover strategy, these are edge
events, not "RSI is currently below 30" — that would keep firing BUY
every bar all the way down.
"""

from __future__ import annotations

import pandas as pd

from app.indicators.rsi import rsi
from app.models.domain import Signal
from app.models.enums import SignalType
from app.strategies.base import Strategy


class RsiStrategy(Strategy):
    def __init__(self, window: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        if not 0 < oversold < overbought < 100:
            raise ValueError("require 0 < oversold < overbought < 100")
        self.window = window
        self.oversold = oversold
        self.overbought = overbought

    @property
    def name(self) -> str:
        return f"rsi_{self.window}_{self.oversold:g}_{self.overbought:g}"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        if data.empty:
            raise ValueError(f"Cannot generate a signal for {symbol!r} from empty data")

        timestamp = data.index[-1]
        price = float(data["close"].iloc[-1])

        # RSI needs `window` diffs to warm up, plus one extra bar to compare "before" vs "after".
        if len(data) < self.window + 2:
            return self._hold(symbol, timestamp, price, "Not enough history for RSI")

        rsi_values = rsi(data["close"], self.window)
        rsi_prev, rsi_curr = rsi_values.iloc[-2], rsi_values.iloc[-1]

        if pd.isna(rsi_prev) or pd.isna(rsi_curr):
            return self._hold(symbol, timestamp, price, "Not enough history for RSI")

        if rsi_prev <= self.oversold < rsi_curr:
            reason = f"RSI crossed above oversold level {self.oversold:g} ({rsi_prev:.1f} -> {rsi_curr:.1f})"
            return Signal(symbol, SignalType.BUY, timestamp, price, self.name, reason)

        if rsi_prev >= self.overbought > rsi_curr:
            reason = f"RSI crossed below overbought level {self.overbought:g} ({rsi_prev:.1f} -> {rsi_curr:.1f})"
            return Signal(symbol, SignalType.SELL, timestamp, price, self.name, reason)

        return self._hold(symbol, timestamp, price, f"RSI in neutral range ({rsi_curr:.1f})")

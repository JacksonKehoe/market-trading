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
    def __init__(
        self, fast_window: int = 20, slow_window: int = 50, near_crossover_gap_pct: float = 0.015
    ) -> None:
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.near_crossover_gap_pct = near_crossover_gap_pct

    @property
    def name(self) -> str:
        return f"sma_crossover_{self.fast_window}_{self.slow_window}"

    def _moving_averages(self, data: pd.DataFrame) -> tuple[float, float, float, float] | None:
        """Returns `(fast_prev, fast_curr, slow_prev, slow_curr)`, or `None` if there
        isn't enough history yet -- shared by `generate_signal` and `near_bullish_crossover`
        so both agree on exactly what "the crossover state" means."""
        if len(data) < self.slow_window + 1:
            return None

        fast_ma = sma(data["close"], self.fast_window)
        slow_ma = sma(data["close"], self.slow_window)
        fast_prev, fast_curr = fast_ma.iloc[-2], fast_ma.iloc[-1]
        slow_prev, slow_curr = slow_ma.iloc[-2], slow_ma.iloc[-1]

        if pd.isna(fast_prev) or pd.isna(slow_prev):
            return None
        return float(fast_prev), float(fast_curr), float(slow_prev), float(slow_curr)

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        if data.empty:
            raise ValueError(f"Cannot generate a signal for {symbol!r} from empty data")

        timestamp = data.index[-1]
        price = float(data["close"].iloc[-1])

        mas = self._moving_averages(data)
        if mas is None:
            return self._hold(symbol, timestamp, price, "Not enough history for the slow moving average")
        fast_prev, fast_curr, slow_prev, slow_curr = mas

        if fast_prev <= slow_prev and fast_curr > slow_curr:
            reason = f"{self.fast_window}-SMA crossed above {self.slow_window}-SMA"
            return Signal(symbol, SignalType.BUY, timestamp, price, self.name, reason)

        if fast_prev >= slow_prev and fast_curr < slow_curr:
            reason = f"{self.fast_window}-SMA crossed below {self.slow_window}-SMA"
            return Signal(symbol, SignalType.SELL, timestamp, price, self.name, reason)

        return self._hold(symbol, timestamp, price, "No crossover")

    def near_bullish_crossover(self, data: pd.DataFrame) -> bool:
        """True if the fast SMA is still below the slow SMA but has closed most of the
        gap since the previous bar -- i.e. a bullish crossover looks imminent, not just
        "somewhat close" by coincidence. Used by `SentimentFilteredStrategy` to pull a
        BUY forward a bar early on strongly bullish news instead of waiting for the
        crossover to actually confirm."""
        mas = self._moving_averages(data)
        if mas is None:
            return False
        fast_prev, fast_curr, slow_prev, slow_curr = mas

        if fast_curr >= slow_curr or slow_curr <= 0 or slow_prev <= 0:
            return False  # already crossed (a real BUY fires instead) or not applicable

        gap_pct = (slow_curr - fast_curr) / slow_curr
        prev_gap_pct = (slow_prev - fast_prev) / slow_prev
        return gap_pct <= self.near_crossover_gap_pct and gap_pct < prev_gap_pct

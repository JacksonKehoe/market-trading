"""Buy-and-hold benchmark equity curve, normalized to a given starting capital.

"What would this same starting capital be worth if it had just tracked
the benchmark symbol (e.g. SPY, as a proxy for the S&P 500) instead of
being traded" — shared by the backtester, the live dashboard, and the
evening email report, so all three compare against the benchmark the
same way.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.data.base import MarketDataProvider


def compute_benchmark_curve(
    provider: MarketDataProvider,
    symbol: str,
    start: datetime,
    end: datetime,
    initial_capital: float,
) -> pd.Series | None:
    """Returns `None` if the benchmark symbol has no data for the range (never raises)."""
    data = provider.get_history(symbol, start, end)
    if data.empty:
        return None

    first_close = data["close"].iloc[0]
    if first_close <= 0:
        return None

    curve = (data["close"] / first_close) * initial_capital
    curve.index.name = "date"
    return curve

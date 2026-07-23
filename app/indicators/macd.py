"""Moving Average Convergence Divergence."""

from __future__ import annotations

import pandas as pd

from app.indicators.moving_average import ema


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Return a DataFrame with `macd`, `signal`, and `histogram` columns."""
    if fast >= slow:
        raise ValueError("fast window must be smaller than slow window")

    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line

    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})

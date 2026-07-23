"""Simple and exponential moving averages.

Pure functions over `pandas.Series` — no classes, no state, no knowledge
of symbols or strategies. `NaN` is returned wherever there isn't yet
enough history to fill the window, so callers can detect the "still
warming up" case explicitly rather than getting a misleadingly early value.
"""

from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple moving average over `window` periods."""
    if window < 1:
        raise ValueError("window must be >= 1")
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    """Exponential moving average with span `window`."""
    if window < 1:
        raise ValueError("window must be >= 1")
    return series.ewm(span=window, adjust=False, min_periods=window).mean()

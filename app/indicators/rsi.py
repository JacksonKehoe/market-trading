"""Relative Strength Index (Wilder's smoothing)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """RSI over `window` periods, in the range [0, 100].

    Uses Wilder's smoothing (an EWM with alpha = 1/window), the standard
    definition. A flat price series (no gains or losses at all) is
    defined as RSI 50 — neutral, since there's no directional evidence
    either way; that's the one case the direct formula can't express
    (0/0), everything else falls out of the algebra on its own.
    """
    if window < 1:
        raise ValueError("window must be >= 1")

    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        rsi_values = 100 - (100 / (1 + rs))

    return rsi_values.mask((avg_gain == 0) & (avg_loss == 0), 50.0)

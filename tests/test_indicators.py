import numpy as np
import pandas as pd
import pytest

from app.indicators.macd import macd
from app.indicators.moving_average import ema, sma
from app.indicators.rsi import rsi


# --- SMA / EMA ---------------------------------------------------------------


def test_sma_matches_manual_average() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(series, window=3)

    assert result.iloc[:2].isna().all()
    assert result.iloc[2] == 2.0  # mean(1,2,3)
    assert result.iloc[3] == 3.0  # mean(2,3,4)
    assert result.iloc[4] == 4.0  # mean(3,4,5)


def test_sma_rejects_invalid_window() -> None:
    with pytest.raises(ValueError):
        sma(pd.Series([1.0, 2.0]), window=0)


def test_ema_reacts_faster_than_sma_to_a_recent_jump() -> None:
    series = pd.Series([10.0] * 20 + [20.0])
    sma_result = sma(series, window=10)
    ema_result = ema(series, window=10)

    assert ema_result.iloc[-1] > sma_result.iloc[-1]


def test_ema_is_flat_for_a_flat_series() -> None:
    series = pd.Series([5.0] * 15)
    result = ema(series, window=5)

    assert result.dropna().eq(5.0).all()


# --- RSI -----------------------------------------------------------------------


def test_rsi_stays_within_bounds() -> None:
    rng = np.random.default_rng(42)
    series = pd.Series(100 + np.cumsum(rng.normal(0, 1, size=100)))
    result = rsi(series, window=14).dropna()

    assert (result >= 0).all()
    assert (result <= 100).all()


def test_rsi_approaches_100_for_strictly_increasing_prices() -> None:
    series = pd.Series(range(1, 41), dtype=float)
    result = rsi(series, window=14)

    assert result.iloc[-1] > 95.0


def test_rsi_approaches_0_for_strictly_decreasing_prices() -> None:
    series = pd.Series(range(40, 0, -1), dtype=float)
    result = rsi(series, window=14)

    assert result.iloc[-1] < 5.0


def test_rsi_is_neutral_50_for_a_flat_series() -> None:
    series = pd.Series([50.0] * 30)
    result = rsi(series, window=14)

    assert result.iloc[-1] == 50.0


def test_rsi_has_nan_during_warmup() -> None:
    series = pd.Series(range(1, 10), dtype=float)
    result = rsi(series, window=14)

    assert result.isna().all()


# --- MACD ------------------------------------------------------------------------


def test_macd_returns_expected_columns() -> None:
    series = pd.Series(range(1, 60), dtype=float)
    result = macd(series)

    assert list(result.columns) == ["macd", "signal", "histogram"]


def test_macd_histogram_equals_macd_minus_signal() -> None:
    series = pd.Series(range(1, 60), dtype=float)
    result = macd(series).dropna()

    diff = (result["macd"] - result["signal"] - result["histogram"]).abs()
    assert (diff < 1e-9).all()


def test_macd_rejects_fast_not_smaller_than_slow() -> None:
    with pytest.raises(ValueError):
        macd(pd.Series([1.0, 2.0, 3.0]), fast=26, slow=12)


def test_macd_warms_up_then_produces_values() -> None:
    series = pd.Series(range(1, 60), dtype=float)
    result = macd(series, fast=12, slow=26, signal=9)

    assert result["macd"].iloc[:24].isna().all()
    assert result.iloc[-1].notna().all()

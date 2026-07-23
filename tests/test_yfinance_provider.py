from datetime import datetime

import pandas as pd
import pytest

from app.data.yfinance_provider import YFinanceProvider


class _FakeTicker:
    """Stands in for `yfinance.Ticker` — no network access."""

    def __init__(self, history_df: pd.DataFrame, last_price: float | None) -> None:
        self._history_df = history_df
        self.fast_info = {} if last_price is None else {"last_price": last_price}

    def history(self, start=None, end=None, interval="1d", period=None, auto_adjust=True) -> pd.DataFrame:
        return self._history_df


class _FakeYFinanceModule:
    def __init__(self, tickers: dict[str, _FakeTicker]) -> None:
        self._tickers = tickers

    def Ticker(self, symbol: str) -> _FakeTicker:
        return self._tickers[symbol]


def _ohlcv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [1.0, 2.0],
            "High": [1.5, 2.5],
            "Low": [0.5, 1.5],
            "Close": [1.2, 2.2],
            "Volume": [1000, 2000],
            "Dividends": [0.0, 0.0],
            "Stock Splits": [0.0, 0.0],
        },
        index=pd.date_range("2026-01-01", periods=2),
    )


def test_get_history_normalizes_columns_to_lowercase_ohlcv() -> None:
    fake_module = _FakeYFinanceModule({"AAPL": _FakeTicker(_ohlcv_frame(), last_price=150.0)})
    provider = YFinanceProvider(yf_module=fake_module)

    result = provider.get_history("AAPL", datetime(2026, 1, 1), datetime(2026, 1, 3))

    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert result.iloc[0]["close"] == 1.2
    assert result.iloc[1]["volume"] == 2000


def test_get_history_returns_empty_frame_with_correct_columns_when_no_data() -> None:
    fake_module = _FakeYFinanceModule({"BADSYM": _FakeTicker(pd.DataFrame(), last_price=None)})
    provider = YFinanceProvider(yf_module=fake_module)

    result = provider.get_history("BADSYM", datetime(2026, 1, 1), datetime(2026, 1, 3))

    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert result.empty


def test_get_latest_price_uses_fast_info_when_available() -> None:
    fake_module = _FakeYFinanceModule({"AAPL": _FakeTicker(pd.DataFrame(), last_price=150.0)})
    provider = YFinanceProvider(yf_module=fake_module)

    assert provider.get_latest_price("AAPL") == 150.0


def test_get_latest_price_falls_back_to_history_close_when_fast_info_missing() -> None:
    history = pd.DataFrame({"Close": [148.0, 149.5]}, index=pd.date_range("2026-01-01", periods=2))
    fake_module = _FakeYFinanceModule({"AAPL": _FakeTicker(history, last_price=None)})
    provider = YFinanceProvider(yf_module=fake_module)

    assert provider.get_latest_price("AAPL") == 149.5


def test_get_latest_price_raises_when_no_data_anywhere() -> None:
    fake_module = _FakeYFinanceModule({"BADSYM": _FakeTicker(pd.DataFrame(), last_price=None)})
    provider = YFinanceProvider(yf_module=fake_module)

    with pytest.raises(ValueError, match="No price data"):
        provider.get_latest_price("BADSYM")

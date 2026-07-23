import pandas as pd
import pytest

from app.models.enums import SignalType
from app.strategies.macd_strategy import MacdStrategy
from tests.conftest import make_price_frame


def test_detects_both_crossovers_across_an_up_down_up_price_series() -> None:
    # MACD's slow EMA + signal EMA need ~35 bars to warm up, so each leg has
    # to be long enough to both clear that warmup and settle into a stable
    # state before reversing -- otherwise a cross happens invisibly during
    # warmup and is never observed.
    rise1 = list(range(10, 70))
    decline = list(range(70, 10, -1))
    rise2 = list(range(10, 70))
    prices = [float(p) for p in rise1 + decline + rise2]
    data = make_price_frame(prices)
    strategy = MacdStrategy(fast=12, slow=26, signal_window=9)

    signal_types = [
        strategy.generate_signal("TEST", data.iloc[: i + 1]).signal_type for i in range(len(data))
    ]

    assert SignalType.SELL in signal_types
    assert SignalType.BUY in signal_types


def test_holds_when_not_enough_history() -> None:
    data = make_price_frame([float(x) for x in range(1, 10)])
    strategy = MacdStrategy()

    signal = strategy.generate_signal("TEST", data)

    assert signal.signal_type == SignalType.HOLD


def test_name_reflects_configured_params() -> None:
    strategy = MacdStrategy(fast=12, slow=26, signal_window=9)
    assert strategy.name == "macd_12_26_9"


def test_rejects_fast_window_not_smaller_than_slow_window() -> None:
    with pytest.raises(ValueError):
        MacdStrategy(fast=26, slow=12)


def test_raises_on_empty_data() -> None:
    strategy = MacdStrategy()
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    with pytest.raises(ValueError):
        strategy.generate_signal("TEST", empty)

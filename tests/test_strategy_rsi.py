import pandas as pd
import pytest

from app.models.enums import SignalType
from app.strategies.rsi_strategy import RsiStrategy
from tests.conftest import make_price_frame


def test_buy_signal_on_bounce_from_oversold() -> None:
    decline = [100 - i for i in range(1, 21)]  # steep 20-day decline
    bounce = [80 + i for i in range(1, 11)]  # 10-day bounce
    prices = [100.0] + [float(p) for p in decline + bounce]
    data = make_price_frame(prices)
    strategy = RsiStrategy(window=14, oversold=30, overbought=70)

    signal_types = [
        strategy.generate_signal("TEST", data.iloc[: i + 1]).signal_type for i in range(len(data))
    ]

    assert SignalType.BUY in signal_types


def test_sell_signal_on_pullback_from_overbought() -> None:
    rise = [100 + i for i in range(1, 21)]  # steep 20-day rise
    pullback = [120 - i for i in range(1, 11)]  # 10-day pullback
    prices = [100.0] + [float(p) for p in rise + pullback]
    data = make_price_frame(prices)
    strategy = RsiStrategy(window=14, oversold=30, overbought=70)

    signal_types = [
        strategy.generate_signal("TEST", data.iloc[: i + 1]).signal_type for i in range(len(data))
    ]

    assert SignalType.SELL in signal_types


def test_holds_when_not_enough_history() -> None:
    data = make_price_frame([10.0, 11.0, 12.0])
    strategy = RsiStrategy(window=14)

    signal = strategy.generate_signal("TEST", data)

    assert signal.signal_type == SignalType.HOLD


def test_name_reflects_configured_params() -> None:
    strategy = RsiStrategy(window=14, oversold=25, overbought=75)
    assert strategy.name == "rsi_14_25_75"


def test_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError):
        RsiStrategy(oversold=70, overbought=30)


def test_raises_on_empty_data() -> None:
    strategy = RsiStrategy()
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    with pytest.raises(ValueError):
        strategy.generate_signal("TEST", empty)

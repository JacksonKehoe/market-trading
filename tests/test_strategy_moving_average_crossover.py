import pandas as pd
import pytest

from app.models.enums import SignalType
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from tests.conftest import make_price_frame


def test_buy_signal_on_upward_cross() -> None:
    data = make_price_frame([5.0, 4.0, 3.0, 2.0, 10.0])
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    signal = strategy.generate_signal("TEST", data)

    assert signal.signal_type == SignalType.BUY
    assert signal.price == 10.0
    assert signal.strategy_name == "sma_crossover_2_3"


def test_sell_signal_on_downward_cross() -> None:
    data = make_price_frame([2.0, 3.0, 4.0, 5.0, 0.5])
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    signal = strategy.generate_signal("TEST", data)

    assert signal.signal_type == SignalType.SELL


def test_holds_when_not_enough_history() -> None:
    data = make_price_frame([10.0, 11.0, 12.0])
    strategy = MovingAverageCrossoverStrategy(fast_window=5, slow_window=10)

    signal = strategy.generate_signal("TEST", data)

    assert signal.signal_type == SignalType.HOLD


def test_holds_steady_state_uptrend_with_no_crossover() -> None:
    data = make_price_frame([float(x) for x in range(1, 51)])
    strategy = MovingAverageCrossoverStrategy(fast_window=3, slow_window=8)

    signal = strategy.generate_signal("TEST", data)

    assert signal.signal_type == SignalType.HOLD
    assert signal.reason == "No crossover"


def test_detects_both_crossovers_across_an_up_down_up_price_series() -> None:
    # The first leg needs to be long enough to both warm up the slow MA and
    # settle into a stable "fast above slow" state before it reverses --
    # otherwise the down-cross happens invisibly during warmup and is never
    # observed (there's no "prev" bar to compare against before bar 0).
    rise1 = list(range(10, 50))
    decline = list(range(50, 10, -1))
    rise2 = list(range(10, 50))
    prices = [float(p) for p in rise1 + decline + rise2]
    data = make_price_frame(prices)
    strategy = MovingAverageCrossoverStrategy(fast_window=3, slow_window=8)

    signal_types = [
        strategy.generate_signal("TEST", data.iloc[: i + 1]).signal_type for i in range(len(data))
    ]

    assert SignalType.SELL in signal_types
    assert SignalType.BUY in signal_types


def test_name_reflects_configured_windows() -> None:
    strategy = MovingAverageCrossoverStrategy(fast_window=10, slow_window=30)
    assert strategy.name == "sma_crossover_10_30"


def test_rejects_fast_window_not_smaller_than_slow_window() -> None:
    with pytest.raises(ValueError):
        MovingAverageCrossoverStrategy(fast_window=30, slow_window=10)


def test_raises_on_empty_data() -> None:
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    with pytest.raises(ValueError):
        strategy.generate_signal("TEST", empty)


def test_near_bullish_crossover_true_when_gap_is_small_and_narrowing() -> None:
    # A dip (fast SMA falls below slow SMA) followed by a partial recovery that
    # closes most -- but not all -- of the gap on the last bar.
    prices = [10.0, 10.0, 10.0, 9.0, 9.0, 9.0, 10.15]
    data = make_price_frame(prices)
    strategy = MovingAverageCrossoverStrategy(fast_window=3, slow_window=6)

    assert strategy.near_bullish_crossover(data) is True
    assert strategy.generate_signal("TEST", data).signal_type == SignalType.HOLD  # not an actual cross yet


def test_near_bullish_crossover_false_when_gap_still_wide() -> None:
    # Same dip, but a much smaller recovery bump -- gap narrows but stays well above threshold.
    prices = [10.0, 10.0, 10.0, 9.0, 9.0, 9.0, 9.3]
    data = make_price_frame(prices)
    strategy = MovingAverageCrossoverStrategy(fast_window=3, slow_window=6)

    assert strategy.near_bullish_crossover(data) is False


def test_near_bullish_crossover_false_when_already_crossed() -> None:
    data = make_price_frame([5.0, 4.0, 3.0, 2.0, 10.0])
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    assert strategy.near_bullish_crossover(data) is False


def test_near_bullish_crossover_false_when_not_enough_history() -> None:
    data = make_price_frame([10.0, 11.0, 12.0])
    strategy = MovingAverageCrossoverStrategy(fast_window=5, slow_window=10)

    assert strategy.near_bullish_crossover(data) is False

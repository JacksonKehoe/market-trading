import pytest

from app.strategies.factory import available_strategies, build_strategy
from app.strategies.macd_strategy import MacdStrategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from app.strategies.rsi_strategy import RsiStrategy


def test_available_strategies_lists_all_three_sorted() -> None:
    assert available_strategies() == ["macd", "rsi", "sma"]


def test_build_strategy_returns_correct_type() -> None:
    assert isinstance(build_strategy("sma"), MovingAverageCrossoverStrategy)
    assert isinstance(build_strategy("rsi"), RsiStrategy)
    assert isinstance(build_strategy("macd"), MacdStrategy)


def test_build_strategy_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy"):
        build_strategy("not_a_real_strategy")

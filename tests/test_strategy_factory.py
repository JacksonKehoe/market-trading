import pytest

from app.config.settings import Settings
from app.strategies.factory import available_strategies, build_strategy
from app.strategies.macd_strategy import MacdStrategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from app.strategies.rsi_strategy import RsiStrategy
from app.strategies.sentiment_filtered import SentimentFilteredStrategy


def test_available_strategies_lists_all_four_sorted() -> None:
    assert available_strategies() == ["macd", "rsi", "sma", "sma_sentiment"]


def test_build_strategy_returns_correct_type() -> None:
    assert isinstance(build_strategy("sma"), MovingAverageCrossoverStrategy)
    assert isinstance(build_strategy("rsi"), RsiStrategy)
    assert isinstance(build_strategy("macd"), MacdStrategy)


def test_build_strategy_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown strategy"):
        build_strategy("not_a_real_strategy")


def test_build_strategy_builds_sentiment_filtered_variant() -> None:
    strategy = build_strategy("sma_sentiment", Settings())

    assert isinstance(strategy, SentimentFilteredStrategy)
    assert strategy.name == "sma_crossover_20_50_sentiment"


def test_build_strategy_defaults_settings_when_not_provided() -> None:
    # Must not raise even without an explicit Settings -- falls back to get_settings().
    strategy = build_strategy("sma_sentiment")
    assert isinstance(strategy, SentimentFilteredStrategy)

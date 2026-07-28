"""Strategy selection by name.

The one place that maps a config string (e.g. `STRATEGIES=sma,rsi` in
`.env`) to a concrete `Strategy` instance, so `run_backtest.py`, the
scheduler jobs, and the dashboard never diverge on what "sma" means.

Each factory entry is a callable taking optional `Settings` (ignored by
the plain strategies; used by sentiment-filtered variants to build their
`SentimentService`) rather than a bare zero-arg constructor, so adding
more decorated variants later doesn't require changing this module's shape.
"""

from __future__ import annotations

from collections.abc import Callable

from app.config.settings import Settings, get_settings
from app.sentiment.factory import build_sentiment_service
from app.strategies.base import Strategy
from app.strategies.macd_strategy import MacdStrategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from app.strategies.rsi_strategy import RsiStrategy
from app.strategies.sentiment_filtered import SentimentFilteredStrategy

_FACTORIES: dict[str, Callable[[Settings], Strategy]] = {
    "sma": lambda settings: MovingAverageCrossoverStrategy(),
    "rsi": lambda settings: RsiStrategy(),
    "macd": lambda settings: MacdStrategy(),
    "sma_sentiment": lambda settings: SentimentFilteredStrategy(
        MovingAverageCrossoverStrategy(), build_sentiment_service(settings)
    ),
}


def available_strategies() -> list[str]:
    return sorted(_FACTORIES)


def build_strategy(name: str, settings: Settings | None = None) -> Strategy:
    try:
        factory = _FACTORIES[name]
    except KeyError:
        raise ValueError(f"Unknown strategy {name!r}; choose one of {available_strategies()}") from None
    return factory(settings or get_settings())

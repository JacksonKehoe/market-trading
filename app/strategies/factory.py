"""Strategy selection by name.

The one place that maps a config string (e.g. `STRATEGY=sma` in `.env`)
to a concrete `Strategy` instance, so `run_backtest.py`, the scheduler
jobs, and the dashboard never diverge on what "sma" means.
"""

from __future__ import annotations

from app.strategies.base import Strategy
from app.strategies.macd_strategy import MacdStrategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from app.strategies.rsi_strategy import RsiStrategy

_FACTORIES: dict[str, type[Strategy]] = {
    "sma": MovingAverageCrossoverStrategy,
    "rsi": RsiStrategy,
    "macd": MacdStrategy,
}


def available_strategies() -> list[str]:
    return sorted(_FACTORIES)


def build_strategy(name: str) -> Strategy:
    try:
        factory = _FACTORIES[name]
    except KeyError:
        raise ValueError(f"Unknown strategy {name!r}; choose one of {available_strategies()}") from None
    return factory()

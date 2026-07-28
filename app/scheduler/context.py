"""Wires the concrete live/scheduled paper trading pipeline.

This is the live-trading counterpart to `app.reporting.backtest.Backtester`:
same `PaperBroker` + `RiskManager` + `ExecutionEngine`, but persisted to
the real database and rehydrated from it on startup, so restarting the
scheduler doesn't silently reset a strategy's paper account back to
`INITIAL_CAPITAL` and lose its open positions.

Each configured strategy (`Settings.strategies`) gets its own
`TradingContext` -- its own `PaperBroker`/`Portfolio`, starting from the
same `INITIAL_CAPITAL`, trading the same watchlist. They share one
`MarketDataProvider` (so its cache is shared instead of duplicated) and
one `SqlTradeRepository`, but their account state is kept completely
separate by `strategy_name` at the persistence layer -- see
`app.database.repository`. That's what makes their results directly
comparable: same starting conditions, independent outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.settings import Settings, get_settings
from app.data.base import MarketDataProvider
from app.data.factory import build_market_data_provider
from app.data.watchlist import load_watchlist
from app.database.engine import get_session_factory, init_db
from app.database.repository import SqlTradeRepository
from app.execution.engine import ExecutionEngine
from app.execution.paper_broker import PaperBroker
from app.risk.risk_manager import RiskManager
from app.risk.rules import RiskLimits
from app.strategies.base import Strategy
from app.strategies.factory import build_strategy


@dataclass(slots=True)
class TradingContext:
    settings: Settings
    data_provider: MarketDataProvider
    repository: SqlTradeRepository
    broker: PaperBroker
    engine: ExecutionEngine
    strategy: Strategy
    watchlist: list[str]
    risk_limits: RiskLimits


def build_trading_context(
    settings: Settings | None = None,
    strategy_name: str | None = None,
    data_provider: MarketDataProvider | None = None,
    repository: SqlTradeRepository | None = None,
) -> TradingContext:
    """Build a `TradingContext` for one strategy.

    `data_provider`/`repository` can be supplied so multiple contexts
    (see `build_trading_contexts`) share the same cache and DB session
    factory instead of each constructing its own.
    """
    settings = settings or get_settings()
    init_db(settings)

    data_provider = data_provider or build_market_data_provider(settings)
    repository = repository or SqlTradeRepository(get_session_factory(settings))
    strategy = build_strategy(strategy_name or (settings.strategies[0] if settings.strategies else "sma"), settings)

    initial_cash = repository.latest_cash_balance(strategy.name)
    if initial_cash is None:
        initial_cash = settings.initial_capital

    broker = PaperBroker(initial_cash, data_provider, settings.commission_per_trade)
    broker.portfolio.positions = {p.symbol: p for p in repository.list_open_positions(strategy.name)}

    risk_limits = RiskLimits.from_settings(settings)
    engine = ExecutionEngine(
        broker, data_provider, RiskManager(risk_limits), repository, strategy_name=strategy.name
    )

    return TradingContext(
        settings=settings,
        data_provider=data_provider,
        repository=repository,
        broker=broker,
        engine=engine,
        strategy=strategy,
        watchlist=load_watchlist(settings),
        risk_limits=risk_limits,
    )


def build_trading_contexts(settings: Settings | None = None) -> list[TradingContext]:
    """One `TradingContext` per `Settings.strategies` entry, sharing a data provider and repository."""
    settings = settings or get_settings()
    init_db(settings)

    data_provider = build_market_data_provider(settings)
    repository = SqlTradeRepository(get_session_factory(settings))

    names = settings.strategies or ["sma"]
    return [
        build_trading_context(settings, strategy_name=name, data_provider=data_provider, repository=repository)
        for name in names
    ]

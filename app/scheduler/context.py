"""Wires the concrete live/scheduled paper trading pipeline.

This is the live-trading counterpart to `app.reporting.backtest.Backtester`:
same `PaperBroker` + `RiskManager` + `ExecutionEngine`, but persisted to
the real database and rehydrated from it on startup, so restarting the
scheduler doesn't silently reset the paper account back to
`INITIAL_CAPITAL` and lose all open positions.
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


def build_trading_context(settings: Settings | None = None) -> TradingContext:
    settings = settings or get_settings()
    init_db(settings)

    data_provider = build_market_data_provider(settings)
    repository = SqlTradeRepository(get_session_factory(settings))

    initial_cash = repository.latest_cash_balance()
    if initial_cash is None:
        initial_cash = settings.initial_capital

    broker = PaperBroker(initial_cash, data_provider, settings.commission_per_trade)
    broker.portfolio.positions = {p.symbol: p for p in repository.list_open_positions()}

    risk_limits = RiskLimits.from_settings(settings)
    engine = ExecutionEngine(broker, data_provider, RiskManager(risk_limits), repository)

    return TradingContext(
        settings=settings,
        data_provider=data_provider,
        repository=repository,
        broker=broker,
        engine=engine,
        strategy=build_strategy(settings.strategy),
        watchlist=load_watchlist(settings),
        risk_limits=risk_limits,
    )

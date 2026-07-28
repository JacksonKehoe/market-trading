"""Backtesting — replays a Strategy against historical data through the
*exact same* paper trading engine (`PaperBroker`, `RiskManager`,
`ExecutionEngine`) used for live paper trading.

That reuse is the point: a backtest isn't a separate simulation written
against different rules, it's the real execution/risk pipeline fed
historical bars one day at a time instead of live ones. The only new
piece is `ReplayMarketDataProvider`, which serves data "as of" a
simulated current date so nothing in the pipeline can see the future.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from app.data.base import MarketDataProvider
from app.execution.engine import ExecutionEngine
from app.execution.paper_broker import PaperBroker
from app.models.domain import Fill, Position
from app.reporting.benchmark import compute_benchmark_curve
from app.risk.risk_manager import RiskManager
from app.risk.rules import RiskLimits
from app.strategies.base import Strategy
from app.utils.logging_config import get_logger

logger = get_logger("app")

_EMPTY_OHLCV = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])


class ReplayMarketDataProvider(MarketDataProvider):
    """Serves pre-fetched historical data "as of" a simulated current date.

    `advance_to(date)` moves simulated "now" forward; `get_latest_price`
    and `get_history` only ever return data up to and including that
    date (forward-filling to the last known trading day for symbols that
    didn't trade on the exact date), so a strategy or the broker can
    never see a future bar.
    """

    def __init__(self, history: dict[str, pd.DataFrame]) -> None:
        self._history = history
        self._current_date: pd.Timestamp | None = None

    def advance_to(self, date: pd.Timestamp) -> None:
        self._current_date = pd.Timestamp(date)

    def _as_of(self, symbol: str) -> pd.DataFrame:
        data = self._history.get(symbol, _EMPTY_OHLCV)
        if data.empty or self._current_date is None:
            return data
        return data.loc[:self._current_date]

    def get_history(
        self, symbol: str, start: datetime, end: datetime, interval: str = "1d"
    ) -> pd.DataFrame:
        return self._as_of(symbol).loc[start:end]

    def get_latest_price(self, symbol: str) -> float:
        window = self._as_of(symbol)
        if window.empty:
            raise ValueError(f"No data available for {symbol!r} on or before {self._current_date}")
        return float(window["close"].iloc[-1])


@dataclass(frozen=True, slots=True)
class BacktestResult:
    equity_curve: pd.Series
    """Daily total equity (cash + mark-to-market positions), indexed by date."""

    trades: list[Fill]
    final_positions: list[Position]
    benchmark_curve: pd.Series | None = None
    """Buy-and-hold equity curve for the benchmark symbol, same starting capital, if requested."""


class Backtester:
    """Runs one `Strategy` across a watchlist over a historical date range."""

    def __init__(
        self,
        data_provider: MarketDataProvider,
        initial_capital: float,
        risk_limits: RiskLimits,
        commission_per_trade: float = 0.0,
    ) -> None:
        self.data_provider = data_provider
        self.initial_capital = initial_capital
        self.risk_limits = risk_limits
        self.commission_per_trade = commission_per_trade

    def run(
        self,
        strategy: Strategy,
        symbols: list[str],
        start: datetime,
        end: datetime,
        benchmark_symbol: str | None = None,
    ) -> BacktestResult:
        history = self._fetch_history(symbols, start, end)
        calendar = sorted(set().union(*(data.index for data in history.values())))
        if not calendar:
            raise ValueError(
                f"No historical data available for {symbols} between {start:%Y-%m-%d} and {end:%Y-%m-%d}"
            )

        replay_provider = ReplayMarketDataProvider(history)
        broker = PaperBroker(self.initial_capital, replay_provider, self.commission_per_trade)
        risk_manager = RiskManager(self.risk_limits)
        engine = ExecutionEngine(broker, replay_provider, risk_manager, strategy_name=strategy.name)

        trades: list[Fill] = []
        equity_by_date: dict[pd.Timestamp, float] = {}

        for date in calendar:
            replay_provider.advance_to(date)
            engine.start_new_trading_day()

            trades.extend(engine.run_exit_checks())

            for symbol, data in history.items():
                if date not in data.index:
                    continue
                window = data.loc[:date]
                signal = strategy.generate_signal(symbol, window)
                fill = engine.process_signal(signal)
                if fill is not None:
                    trades.append(fill)

            equity_by_date[date] = broker.get_account().equity

        equity_curve = pd.Series(equity_by_date).sort_index()
        equity_curve.index.name = "date"

        benchmark_curve = (
            self._compute_benchmark(benchmark_symbol, start, end) if benchmark_symbol else None
        )

        return BacktestResult(
            equity_curve=equity_curve,
            trades=trades,
            final_positions=broker.get_positions(),
            benchmark_curve=benchmark_curve,
        )

    def _fetch_history(
        self, symbols: list[str], start: datetime, end: datetime
    ) -> dict[str, pd.DataFrame]:
        history: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            data = self.data_provider.get_history(symbol, start, end)
            if data.empty:
                logger.warning("No historical data for %s in the requested range; skipping", symbol)
                continue
            history[symbol] = data
        return history

    def _compute_benchmark(
        self, symbol: str, start: datetime, end: datetime
    ) -> pd.Series | None:
        curve = compute_benchmark_curve(self.data_provider, symbol, start, end, self.initial_capital)
        if curve is None:
            logger.warning("No historical data for benchmark %s; skipping benchmark comparison", symbol)
        return curve

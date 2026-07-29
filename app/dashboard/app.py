"""Lightweight local dashboard — a read-only Flask app over the paper trading database.

Never executes trades or writes to the database: it only reads current
state (via `SqlTradeRepository`) and, for the strategy-signals panel,
calls each configured `Strategy` against live market data. Runs on
localhost only (see `run_dashboard.py`) -- there is no authentication
because it isn't meant to be reachable beyond your own machine.

Each configured strategy (`Settings.strategies`) trades its own
independent simulated account, so this page is built around comparing
them: a summary table, a combined equity-curve chart (one line per
strategy), and combined detail tables tagged with a "Strategy" column.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask, render_template

from app.config.settings import Settings, get_settings
from app.data.factory import build_market_data_provider
from app.data.watchlist import load_watchlist
from app.database.engine import get_session_factory, init_db
from app.database.repository import SqlTradeRepository
from app.reporting.benchmark import compute_benchmark_curve
from app.reporting.charts import build_multi_equity_curve_chart
from app.reporting.positions import position_rows
from app.risk.rules import RiskLimits
from app.strategies.factory import build_strategy
from app.utils.logging_config import get_logger

logger = get_logger("app")

_SIGNAL_LOOKBACK_DAYS = 250
_MAX_RECENT_TRADES = 25
_MIN_BENCHMARK_LOOKBACK_DAYS = 7
"""Even on a brand-new account (minutes of history), request at least this
much benchmark history -- a narrower window may not contain a single daily bar."""

_STRATEGY_DISPLAY_LABELS = {
    "sma": "SMA",
    "rsi": "RSI",
    "macd": "MACD",
    "sma_sentiment": "SENTIMENT",
}
"""Cosmetic labels for the dashboard only, keyed by the `STRATEGIES` factory
name (e.g. "sma_sentiment"), not the technical `Strategy.name` it builds
(e.g. "sma_crossover_20_50_sentiment") -- the latter stays the real
identifier everywhere else (database keys, email reports)."""


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    init_db(settings)

    repository = SqlTradeRepository(get_session_factory(settings))
    data_provider = build_market_data_provider(settings)
    watchlist = load_watchlist(settings)
    risk_limits = RiskLimits.from_settings(settings)
    strategy_names = settings.strategies or ["sma"]

    app = Flask(__name__)

    @app.route("/")
    def index():  # type: ignore[no-untyped-def]
        comparison = []
        equity_curves = {}
        all_positions = []
        all_signals = []
        all_trades = []
        risk_rows = []

        end = datetime.now()
        start = end - timedelta(days=_SIGNAL_LOOKBACK_DAYS)

        for name in strategy_names:
            strategy = build_strategy(name, settings)
            label = _STRATEGY_DISPLAY_LABELS.get(name, strategy.name)

            cash = repository.latest_cash_balance(strategy.name)
            if cash is None:
                cash = settings.initial_capital

            open_positions = repository.list_open_positions(strategy.name)
            broker_view = _StaticPositionsView(open_positions)
            rows = position_rows(broker_view, data_provider)
            for row in rows:
                row["strategy"] = label
                all_positions.append(row)
            positions_value = sum(row["market_value"] for row in rows)
            equity = cash + positions_value

            equity_curves[label] = repository.equity_curve(strategy.name)

            for fill in repository.list_trades(strategy_name=strategy.name):
                all_trades.append({"strategy": label, "fill": fill})

            for symbol in watchlist:
                try:
                    data = data_provider.get_history(symbol, start, end)
                    if data.empty:
                        continue
                    signal = strategy.generate_signal(symbol, data)
                    all_signals.append(
                        {
                            "strategy": label,
                            "symbol": signal.symbol,
                            "signal_type": signal.signal_type,
                            "price": signal.price,
                            "reason": signal.reason,
                        }
                    )
                except Exception:
                    logger.exception("Failed to compute a %s signal for %s on the dashboard", strategy.name, symbol)

            return_pct = (equity / settings.initial_capital - 1) * 100 if settings.initial_capital else 0.0
            comparison.append(
                {
                    "strategy": label,
                    "equity": equity,
                    "cash": cash,
                    "return_pct": return_pct,
                    "open_positions": len(rows),
                }
            )
            risk_rows.append(
                {
                    "strategy": label,
                    "allocation_pct": (positions_value / equity * 100) if equity else 0.0,
                    "open_positions": len(rows),
                    "max_open_positions": risk_limits.max_open_positions,
                    "cash_reserve_pct": (cash / equity * 100) if equity else 0.0,
                }
            )

        non_empty_curves = [curve for curve in equity_curves.values() if not curve.empty]
        earliest_snapshot = min(curve.index.min() for curve in non_empty_curves) if non_empty_curves else start
        # On a fresh account, the earliest snapshot can be minutes old -- too
        # narrow a window for a *daily* benchmark bar to exist at all. Always
        # request at least a week so the benchmark works from day one instead of
        # silently doing nothing until several days of history have accumulated.
        benchmark_start = min(earliest_snapshot, end - timedelta(days=_MIN_BENCHMARK_LOOKBACK_DAYS))
        benchmark_curve = compute_benchmark_curve(
            data_provider, settings.benchmark_symbol, benchmark_start, end, settings.initial_capital
        )
        benchmark_label = f"{settings.benchmark_symbol} (Benchmark)"
        if benchmark_curve is not None and not benchmark_curve.empty:
            equity_curves[benchmark_label] = benchmark_curve
            comparison.append(
                {
                    "strategy": benchmark_label,
                    "equity": benchmark_curve.iloc[-1],
                    "cash": None,
                    "return_pct": (benchmark_curve.iloc[-1] / settings.initial_capital - 1) * 100,
                    "open_positions": None,
                    "is_benchmark": True,
                }
            )

        chart_html = None
        if any(not curve.empty for curve in equity_curves.values()):
            chart_html = build_multi_equity_curve_chart(equity_curves).to_html(
                full_html=False, include_plotlyjs="cdn", div_id="strategy-comparison-chart"
            )

        recent_trades = sorted(all_trades, key=lambda t: t["fill"].timestamp, reverse=True)[:_MAX_RECENT_TRADES]

        return render_template(
            "dashboard.html",
            generated_at=datetime.now(),
            comparison=comparison,
            chart_html=chart_html,
            positions=all_positions,
            trades=recent_trades,
            signals=all_signals,
            risk_summary=risk_rows,
            risk_limits=risk_limits,
        )

    return app


class _StaticPositionsView:
    """Adapts a plain `list[Position]` (from the repository) to the read
    subset of `BrokerInterface` that `position_rows` needs, since the
    dashboard has no live broker/portfolio -- only what's persisted."""

    def __init__(self, positions: list) -> None:
        self._positions = positions

    def get_positions(self) -> list:
        return self._positions

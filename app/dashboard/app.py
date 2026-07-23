"""Lightweight local dashboard — a read-only Flask app over the paper trading database.

Never executes trades or writes to the database: it only reads current
state (via `SqlTradeRepository`) and, for the strategy-signals panel,
calls the configured `Strategy` against live market data. Runs on
localhost only (see `run_dashboard.py`) -- there is no authentication
because it isn't meant to be reachable beyond your own machine.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import Flask, render_template

from app.config.settings import Settings, get_settings
from app.data.factory import build_market_data_provider
from app.data.watchlist import load_watchlist
from app.database.engine import get_session_factory, init_db
from app.database.repository import SqlTradeRepository
from app.reporting.charts import build_equity_curve_chart
from app.reporting.positions import position_rows
from app.risk.rules import RiskLimits
from app.strategies.factory import build_strategy
from app.utils.logging_config import get_logger

logger = get_logger("app")

_SIGNAL_LOOKBACK_DAYS = 250
_MAX_RECENT_TRADES = 25


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    init_db(settings)

    repository = SqlTradeRepository(get_session_factory(settings))
    data_provider = build_market_data_provider(settings)
    strategy = build_strategy(settings.strategy)
    watchlist = load_watchlist(settings)
    risk_limits = RiskLimits.from_settings(settings)

    app = Flask(__name__)

    @app.route("/")
    def index():  # type: ignore[no-untyped-def]
        cash = repository.latest_cash_balance()
        if cash is None:
            cash = settings.initial_capital

        open_positions = repository.list_open_positions()
        broker_view = _StaticPositionsView(open_positions)
        positions = position_rows(broker_view, data_provider)
        positions_value = sum(p["market_value"] for p in positions)
        equity = cash + positions_value

        equity_curve = repository.equity_curve()
        chart_html = None
        if not equity_curve.empty:
            chart_html = build_equity_curve_chart(equity_curve).to_html(
                full_html=False, include_plotlyjs="cdn"
            )

        trades = list(reversed(repository.list_trades()))[:_MAX_RECENT_TRADES]

        signals = []
        end = datetime.now()
        start = end - timedelta(days=_SIGNAL_LOOKBACK_DAYS)
        for symbol in watchlist:
            try:
                data = data_provider.get_history(symbol, start, end)
                if data.empty:
                    continue
                signals.append(strategy.generate_signal(symbol, data))
            except Exception:
                logger.exception("Failed to compute a signal for %s on the dashboard", symbol)

        risk_summary = {
            "allocation_pct": (positions_value / equity * 100) if equity else 0.0,
            "open_positions": len(positions),
            "max_open_positions": risk_limits.max_open_positions,
            "cash_reserve_pct": (cash / equity * 100) if equity else 0.0,
            "stop_loss_pct": risk_limits.stop_loss_pct,
            "take_profit_pct": risk_limits.take_profit_pct,
        }

        return render_template(
            "dashboard.html",
            generated_at=datetime.now(),
            strategy_name=strategy.name,
            equity=equity,
            cash=cash,
            positions_value=positions_value,
            positions=positions,
            chart_html=chart_html,
            trades=trades,
            signals=signals,
            risk_summary=risk_summary,
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

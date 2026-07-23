"""Builds the Jinja2 context dictionaries for the morning/evening email reports.

Deliberately takes its dependencies (broker, data provider, repository,
strategy, watchlist, risk limits) as plain parameters rather than a
bundled orchestration object: `app.scheduler` (which owns that bundling)
sits *above* `app.email` in the dependency graph, so `app.email` must not
import anything from it. This module's only job is "given current state,
produce the data a report needs" -- it doesn't decide when reports run
(`app.scheduler.jobs`) or how they're delivered (`app.email.mailer`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config.settings import Settings
from app.data.base import MarketDataProvider
from app.database.repository import SqlTradeRepository
from app.execution.broker_base import BrokerInterface
from app.models.domain import Signal
from app.models.enums import SignalType
from app.reporting.metrics import compute_realized_pnl_by_fill
from app.reporting.positions import position_rows
from app.risk.rules import RiskLimits
from app.strategies.base import Strategy

_MARKET_MOVERS_LOOKBACK_DAYS = 5
_TOP_MOVERS = 5


def _market_movers(provider: MarketDataProvider, symbols: list[str]) -> list[dict]:
    end = datetime.now()
    start = end - timedelta(days=_MARKET_MOVERS_LOOKBACK_DAYS)
    movers = []
    for symbol in symbols:
        try:
            data = provider.get_history(symbol, start, end)
        except Exception:
            continue
        if len(data) < 2:
            continue
        prev_close = float(data["close"].iloc[-2])
        last_close = float(data["close"].iloc[-1])
        if prev_close == 0:
            continue
        movers.append(
            {"symbol": symbol, "price": last_close, "change_pct": (last_close / prev_close - 1) * 100}
        )
    movers.sort(key=lambda mover: abs(mover["change_pct"]), reverse=True)
    return movers[:_TOP_MOVERS]


def build_morning_report_context(
    settings: Settings,
    broker: BrokerInterface,
    data_provider: MarketDataProvider,
    strategy: Strategy,
    watchlist: list[str],
    signals: list[Signal],
) -> dict:
    account = broker.get_account()
    buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
    sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
    hold_count = len(signals) - len(buy_signals) - len(sell_signals)

    movers = _market_movers(data_provider, watchlist)
    market_summary_pct = sum(m["change_pct"] for m in movers) / len(movers) if movers else 0.0

    plan_lines: list[str] = []
    if buy_signals:
        plan_lines.append(f"{len(buy_signals)} BUY signal(s): {', '.join(s.symbol for s in buy_signals)}")
    if sell_signals:
        plan_lines.append(f"{len(sell_signals)} SELL signal(s): {', '.join(s.symbol for s in sell_signals)}")
    if not buy_signals and not sell_signals:
        plan_lines.append("No new signals today -- holding current positions.")

    return {
        "generated_at": datetime.now(UTC),
        "strategy_name": strategy.name,
        "portfolio_value": account.equity,
        "cash": account.cash,
        "positions": position_rows(broker, data_provider),
        "watchlist": watchlist,
        "buy_signals": buy_signals,
        "sell_signals": sell_signals,
        "hold_count": hold_count,
        "market_movers": movers,
        "market_summary_pct": market_summary_pct,
        "daily_trading_plan": plan_lines,
    }


def build_evening_report_context(
    settings: Settings,
    broker: BrokerInterface,
    data_provider: MarketDataProvider,
    repository: SqlTradeRepository,
    strategy: Strategy,
    watchlist: list[str],
    risk_limits: RiskLimits,
) -> dict:
    account = broker.get_account()
    positions = position_rows(broker, data_provider)

    all_trades = repository.list_trades()
    pnl_by_fill = compute_realized_pnl_by_fill(all_trades)
    # Fill/Account timestamps are always UTC-aware (see PaperBroker), so "today"
    # must be computed in UTC too -- comparing against a local date() would
    # misclassify trades near midnight UTC for any non-UTC local timezone.
    today = datetime.now(UTC).date()
    trades_today = [
        {"fill": fill, "pnl": pnl_by_fill.get(fill.id)}
        for fill in all_trades
        if fill.timestamp.date() == today
    ]

    equity_curve = repository.equity_curve()
    prior_equity = equity_curve[equity_curve.index.date < today]
    starting_equity = float(prior_equity.iloc[-1]) if not prior_equity.empty else settings.initial_capital
    day_pl = account.equity - starting_equity
    day_pl_pct = (day_pl / starting_equity * 100) if starting_equity else 0.0

    best_performer = max(positions, key=lambda p: p["unrealized_pl_pct"], default=None)
    worst_performer = min(positions, key=lambda p: p["unrealized_pl_pct"], default=None)

    equity = account.equity
    risk_summary = {
        "allocation_pct": (account.positions_value / equity * 100) if equity else 0.0,
        "open_positions": len(positions),
        "max_open_positions": risk_limits.max_open_positions,
        "cash_reserve_pct": (account.cash / equity * 100) if equity else 0.0,
        "stop_loss_pct": risk_limits.stop_loss_pct,
        "take_profit_pct": risk_limits.take_profit_pct,
        "daily_loss_limit_pct": risk_limits.daily_loss_limit_pct,
    }

    held_symbols = {p["symbol"] for p in positions}
    next_watchlist = [symbol for symbol in watchlist if symbol not in held_symbols]

    recommendations: list[str] = []
    if len(positions) >= risk_limits.max_open_positions:
        recommendations.append("At the max open positions limit -- no new BUYs will be taken until one closes.")
    if risk_summary["cash_reserve_pct"] < 5:
        recommendations.append("Cash reserve is low relative to equity.")
    if not recommendations:
        recommendations.append("No portfolio-level concerns detected.")

    return {
        "generated_at": datetime.now(UTC),
        "strategy_name": strategy.name,
        "portfolio_value": account.equity,
        "cash": account.cash,
        "day_pl": day_pl,
        "day_pl_pct": day_pl_pct,
        "trades_today": trades_today,
        "positions": positions,
        "best_performer": best_performer,
        "worst_performer": worst_performer,
        "equity_curve": equity_curve,
        "risk_summary": risk_summary,
        "recommendations": recommendations,
        "next_watchlist": next_watchlist,
    }

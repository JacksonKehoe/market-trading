"""Builds the Jinja2 context dictionaries for the morning/evening email reports.

Deliberately takes its dependencies (data provider, repository,
watchlist, risk limits, and a list of per-strategy `StrategyState`) as
plain parameters rather than a bundled orchestration object:
`app.scheduler` (which owns that bundling) sits *above* `app.email` in
the dependency graph, so `app.email` must not import anything from it.
This module's only job is "given current state, produce the data a
report needs" -- it doesn't decide when reports run (`app.scheduler.jobs`)
or how they're delivered (`app.email.mailer`).

Each configured strategy trades its own independent simulated account
(see `app.scheduler.context`), so these reports are built around a
comparison: a summary table plus a combined equity curve, with
per-strategy detail tables (positions, signals, trades) tagged by a
"Strategy" column rather than duplicated per strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pandas as pd

from app.config.settings import Settings
from app.data.base import MarketDataProvider
from app.database.repository import SqlTradeRepository
from app.execution.broker_base import BrokerInterface
from app.models.domain import Signal
from app.models.enums import SignalType
from app.reporting.metrics import compute_realized_pnl_by_fill
from app.reporting.positions import position_rows
from app.risk.rules import RiskLimits

_MARKET_MOVERS_LOOKBACK_DAYS = 5
_TOP_MOVERS = 5


@dataclass(frozen=True, slots=True)
class StrategyState:
    """One strategy's live broker + (for the morning scan) its signals.

    Plain data, not `app.scheduler.context.TradingContext` -- this module
    must not depend on `app.scheduler`, which sits above it.
    """

    name: str
    broker: BrokerInterface
    signals: list[Signal] = field(default_factory=list)


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
    data_provider: MarketDataProvider,
    watchlist: list[str],
    strategies: list[StrategyState],
) -> dict:
    movers = _market_movers(data_provider, watchlist)
    market_summary_pct = sum(m["change_pct"] for m in movers) / len(movers) if movers else 0.0

    comparison: list[dict] = []
    all_positions: list[dict] = []
    all_signals: list[Signal] = []
    plan_lines: list[str] = []

    for state in strategies:
        account = state.broker.get_account()
        buy_signals = [s for s in state.signals if s.signal_type == SignalType.BUY]
        sell_signals = [s for s in state.signals if s.signal_type == SignalType.SELL]

        comparison.append(
            {
                "strategy": state.name,
                "equity": account.equity,
                "cash": account.cash,
                "open_positions": len(state.broker.get_positions()),
                "buy_signals": len(buy_signals),
                "sell_signals": len(sell_signals),
            }
        )

        for row in position_rows(state.broker, data_provider):
            row["strategy"] = state.name
            all_positions.append(row)

        all_signals.extend(state.signals)

        if buy_signals:
            plan_lines.append(
                f"{state.name}: {len(buy_signals)} BUY signal(s) — {', '.join(s.symbol for s in buy_signals)}"
            )
        if sell_signals:
            plan_lines.append(
                f"{state.name}: {len(sell_signals)} SELL signal(s) — {', '.join(s.symbol for s in sell_signals)}"
            )

    if not plan_lines:
        plan_lines.append("No new signals today across any strategy -- holding current positions.")

    buy_signals_all = [s for s in all_signals if s.signal_type == SignalType.BUY]
    sell_signals_all = [s for s in all_signals if s.signal_type == SignalType.SELL]
    hold_count = len(all_signals) - len(buy_signals_all) - len(sell_signals_all)

    return {
        "generated_at": datetime.now(UTC),
        "comparison": comparison,
        "positions": all_positions,
        "watchlist": watchlist,
        "buy_signals": buy_signals_all,
        "sell_signals": sell_signals_all,
        "hold_count": hold_count,
        "market_movers": movers,
        "market_summary_pct": market_summary_pct,
        "daily_trading_plan": plan_lines,
    }


def build_evening_report_context(
    settings: Settings,
    data_provider: MarketDataProvider,
    repository: SqlTradeRepository,
    watchlist: list[str],
    risk_limits: RiskLimits,
    strategies: list[StrategyState],
) -> dict:
    # Fill/Account timestamps are always UTC-aware (see PaperBroker), so "today"
    # must be computed in UTC too -- comparing against a local date() would
    # misclassify trades near midnight UTC for any non-UTC local timezone.
    today = datetime.now(UTC).date()

    comparison: list[dict] = []
    equity_curves: dict[str, pd.Series] = {}
    all_positions: list[dict] = []
    trades_today: list[dict] = []
    risk_rows: list[dict] = []
    recommendations: list[str] = []

    for state in strategies:
        account = state.broker.get_account()
        positions = position_rows(state.broker, data_provider)
        for row in positions:
            row["strategy"] = state.name
            all_positions.append(row)

        strategy_trades = repository.list_trades(strategy_name=state.name)
        pnl_by_fill = compute_realized_pnl_by_fill(strategy_trades)
        for fill in strategy_trades:
            if fill.timestamp.date() == today:
                trades_today.append({"strategy": state.name, "fill": fill, "pnl": pnl_by_fill.get(fill.id)})

        equity_curve = repository.equity_curve(state.name)
        equity_curves[state.name] = equity_curve
        prior_equity = equity_curve[equity_curve.index.date < today]
        starting_equity = float(prior_equity.iloc[-1]) if not prior_equity.empty else settings.initial_capital
        day_pl = account.equity - starting_equity
        day_pl_pct = (day_pl / starting_equity * 100) if starting_equity else 0.0

        equity = account.equity
        risk_rows.append(
            {
                "strategy": state.name,
                "allocation_pct": (account.positions_value / equity * 100) if equity else 0.0,
                "open_positions": len(positions),
                "max_open_positions": risk_limits.max_open_positions,
                "cash_reserve_pct": (account.cash / equity * 100) if equity else 0.0,
            }
        )

        if len(positions) >= risk_limits.max_open_positions:
            recommendations.append(
                f"{state.name}: at the max open positions limit -- no new BUYs will be taken until one closes."
            )

        comparison.append(
            {
                "strategy": state.name,
                "equity": account.equity,
                "cash": account.cash,
                "day_pl": day_pl,
                "day_pl_pct": day_pl_pct,
                "open_positions": len(positions),
            }
        )

    if not recommendations:
        recommendations.append("No portfolio-level concerns detected across any strategy.")

    best_strategy = max(comparison, key=lambda c: c["day_pl_pct"], default=None)
    worst_strategy = min(comparison, key=lambda c: c["day_pl_pct"], default=None)

    return {
        "generated_at": datetime.now(UTC),
        "comparison": comparison,
        "best_strategy": best_strategy,
        "worst_strategy": worst_strategy,
        "trades_today": trades_today,
        "positions": all_positions,
        "equity_curves": equity_curves,
        "risk_limits": risk_limits,
        "risk_summary": risk_rows,
        "recommendations": recommendations,
        "next_watchlist": watchlist,
    }

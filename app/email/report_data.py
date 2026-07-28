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
from app.reporting.benchmark import compute_benchmark_curve
from app.reporting.metrics import compute_realized_pnl_by_fill
from app.reporting.positions import position_rows
from app.risk.rules import RiskLimits
from app.sentiment.service import SentimentService

_MARKET_MOVERS_LOOKBACK_DAYS = 5
_TOP_MOVERS = 5
_MIN_BENCHMARK_LOOKBACK_DAYS = 7
"""Even on a brand-new account (minutes of history), request at least this
much benchmark history -- a narrower window may not contain a single daily bar."""


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


def _sentiment_rows(sentiment_service: SentimentService | None, symbols: list[str]) -> list[dict]:
    if sentiment_service is None:
        return []
    rows = []
    for symbol in symbols:
        score = sentiment_service.get_sentiment(symbol)
        if score is not None:
            rows.append(
                {
                    "symbol": symbol,
                    "label": score.label,
                    "score": score.score,
                    "headline_count": score.headline_count,
                }
            )
    return rows


def build_morning_report_context(
    settings: Settings,
    data_provider: MarketDataProvider,
    watchlist: list[str],
    strategies: list[StrategyState],
    sentiment_service: SentimentService | None = None,
) -> dict:
    movers = _market_movers(data_provider, watchlist)
    market_summary_pct = sum(m["change_pct"] for m in movers) / len(movers) if movers else 0.0

    benchmark_movers = _market_movers(data_provider, [settings.benchmark_symbol])
    benchmark_day_change = benchmark_movers[0] if benchmark_movers else None

    sentiment_scores = _sentiment_rows(sentiment_service, watchlist)

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
        "benchmark_symbol": settings.benchmark_symbol,
        "benchmark_day_change": benchmark_day_change,
        "sentiment_scores": sentiment_scores,
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

    # Computed before the benchmark row is appended to `comparison` below --
    # the benchmark isn't a strategy and shouldn't be eligible to "win".
    best_strategy = max(comparison, key=lambda c: c["day_pl_pct"], default=None)
    worst_strategy = min(comparison, key=lambda c: c["day_pl_pct"], default=None)

    # Equity curve timestamps come back from SQLite as naive datetimes (their
    # underlying value is still UTC, just without tzinfo attached -- see
    # SqlTradeRepository), so the "now" used alongside them here must be
    # naive too. Mixing naive and tz-aware datetimes in a pandas date slice
    # raises ValueError: "Both dates must have the same UTC offset".
    naive_now = datetime.now(UTC).replace(tzinfo=None)
    non_empty_curves = [curve for curve in equity_curves.values() if not curve.empty]
    earliest_snapshot = min(curve.index.min() for curve in non_empty_curves) if non_empty_curves else naive_now
    # On a fresh account, the earliest snapshot can be minutes old -- too
    # narrow a window for a *daily* benchmark bar to exist at all. Always
    # request at least a week so the benchmark works from day one instead of
    # silently doing nothing until several days of history have accumulated.
    benchmark_start = min(earliest_snapshot, naive_now - timedelta(days=_MIN_BENCHMARK_LOOKBACK_DAYS))
    benchmark_curve = compute_benchmark_curve(
        data_provider, settings.benchmark_symbol, benchmark_start, naive_now, settings.initial_capital
    )
    benchmark_label = f"{settings.benchmark_symbol} (Benchmark)"
    if benchmark_curve is not None and not benchmark_curve.empty:
        equity_curves[benchmark_label] = benchmark_curve
        prior_benchmark = benchmark_curve[benchmark_curve.index.date < today]
        benchmark_starting_equity = (
            float(prior_benchmark.iloc[-1]) if not prior_benchmark.empty else settings.initial_capital
        )
        benchmark_day_pl = float(benchmark_curve.iloc[-1]) - benchmark_starting_equity
        benchmark_day_pl_pct = (
            (benchmark_day_pl / benchmark_starting_equity * 100) if benchmark_starting_equity else 0.0
        )
        comparison.append(
            {
                "strategy": benchmark_label,
                "equity": float(benchmark_curve.iloc[-1]),
                "cash": None,
                "day_pl": benchmark_day_pl,
                "day_pl_pct": benchmark_day_pl_pct,
                "open_positions": None,
                "is_benchmark": True,
            }
        )

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

"""Scheduled trading jobs: morning scan+trade, evening wrap-up, optional hourly scan.

Each job takes an optional list of `TradingContext` (building the real,
multi-strategy list via `build_trading_contexts()` if none given) so
they're easy to unit-test with fakes, while `scheduler_service` just
wires trigger times to the no-argument form for real use. All configured
strategies are scanned/traded within the same job run, and their results
are combined into a single comparison report/email.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.config.settings import Settings
from app.email.mailer import send_email
from app.email.renderer import render_evening_report, render_morning_report
from app.email.report_data import StrategyState, build_evening_report_context, build_morning_report_context
from app.models.domain import Signal
from app.scheduler.context import TradingContext, build_trading_contexts
from app.utils.logging_config import get_logger

app_logger = get_logger("app")
scheduler_logger = get_logger("scheduler")

_LOOKBACK_DAYS = 250
"""Enough calendar days of history to warm up every strategy's default indicator window."""


def run_trading_scan(context: TradingContext) -> list[Signal]:
    """Force-check stop-loss/take-profit, then scan the watchlist for new signals.

    Any BUY/SELL signal that clears `RiskManager` is submitted immediately.
    Returns every signal generated (including HOLDs) for reporting.
    """
    context.engine.run_exit_checks()

    end = datetime.now()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    signals: list[Signal] = []

    for symbol in context.watchlist:
        try:
            data = context.data_provider.get_history(symbol, start, end)
        except Exception:
            scheduler_logger.exception("Failed to fetch history for %s; skipping", symbol)
            continue
        if data.empty:
            scheduler_logger.warning("No historical data for %s; skipping", symbol)
            continue

        signal = context.strategy.generate_signal(symbol, data)
        signals.append(signal)
        context.engine.process_signal(signal)

    return signals


def _save_snapshot(context: TradingContext) -> None:
    context.repository.save_account_snapshot(context.broker.get_account(), context.strategy.name)


def morning_job(contexts: list[TradingContext] | None = None) -> None:
    """Before market open: reset each strategy's daily-loss baseline, scan + trade, email a comparison report."""
    contexts = contexts or build_trading_contexts()
    scheduler_logger.info("Morning job starting for %d strategy(ies)", len(contexts))

    strategy_states = []
    for context in contexts:
        context.engine.start_new_trading_day()
        signals = run_trading_scan(context)
        _save_snapshot(context)
        strategy_states.append(StrategyState(context.strategy.name, context.broker, signals))

    first = contexts[0]
    report_context = build_morning_report_context(
        first.settings, first.data_provider, first.watchlist, strategy_states
    )
    html = render_morning_report(report_context)
    _save_and_send(first.settings, html, "morning")

    scheduler_logger.info("Morning job complete")


def evening_job(contexts: list[TradingContext] | None = None) -> None:
    """After market close: mark every strategy's positions to market, email the comparison wrap-up report."""
    contexts = contexts or build_trading_contexts()
    scheduler_logger.info("Evening job starting for %d strategy(ies)", len(contexts))

    strategy_states = []
    for context in contexts:
        context.engine.run_exit_checks()
        _save_snapshot(context)
        strategy_states.append(StrategyState(context.strategy.name, context.broker))

    first = contexts[0]
    report_context = build_evening_report_context(
        first.settings,
        first.data_provider,
        first.repository,
        first.watchlist,
        first.risk_limits,
        strategy_states,
    )
    html = render_evening_report(report_context)
    _save_and_send(first.settings, html, "evening")

    scheduler_logger.info("Evening job complete")


def hourly_scan_job(contexts: list[TradingContext] | None = None) -> None:
    """Optional intraday scan: trades on fresh signals for every strategy, no report/email."""
    contexts = contexts or build_trading_contexts()
    if not contexts[0].settings.hourly_scan_enabled:
        return

    scheduler_logger.info("Hourly scan starting for %d strategy(ies)", len(contexts))
    for context in contexts:
        run_trading_scan(context)
        _save_snapshot(context)
    scheduler_logger.info("Hourly scan complete")


def _save_and_send(settings: Settings, html: str, report_name: str) -> None:
    """Always save the report to disk (so it's available with no email configured); email it if configured."""
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / f"{report_name}_{datetime.now():%Y%m%dT%H%M%S}.html"
    path.write_text(html, encoding="utf-8")

    subject = f"{report_name.title()} Trading Report - {datetime.now():%Y-%m-%d}"
    send_email(settings, subject, html)
    app_logger.info("%s report saved to %s", report_name.title(), path)

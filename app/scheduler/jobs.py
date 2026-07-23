"""Scheduled trading jobs: morning scan+trade, evening wrap-up, optional hourly scan.

Each job takes an optional `TradingContext` (building a real one via
`build_trading_context()` if none is given) so they're easy to unit-test
with a fake context, while `scheduler_service` just wires trigger times
to the no-argument form for real use.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.email.mailer import send_email
from app.email.renderer import render_evening_report, render_morning_report
from app.email.report_data import build_evening_report_context, build_morning_report_context
from app.models.domain import Signal
from app.scheduler.context import TradingContext, build_trading_context
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
    context.repository.save_account_snapshot(context.broker.get_account())


def morning_job(context: TradingContext | None = None) -> None:
    """Runs before market open: resets the daily-loss baseline, scans and trades, emails the report."""
    context = context or build_trading_context()
    scheduler_logger.info("Morning job starting")

    context.engine.start_new_trading_day()
    signals = run_trading_scan(context)
    _save_snapshot(context)

    report_context = build_morning_report_context(
        context.settings, context.broker, context.data_provider, context.strategy, context.watchlist, signals
    )
    html = render_morning_report(report_context)
    _save_and_send(context, html, "morning")

    scheduler_logger.info("Morning job complete: %d signal(s) evaluated", len(signals))


def evening_job(context: TradingContext | None = None) -> None:
    """Runs after market close: marks positions to market, emails the day's wrap-up report."""
    context = context or build_trading_context()
    scheduler_logger.info("Evening job starting")

    context.engine.run_exit_checks()
    _save_snapshot(context)

    report_context = build_evening_report_context(
        context.settings,
        context.broker,
        context.data_provider,
        context.repository,
        context.strategy,
        context.watchlist,
        context.risk_limits,
    )
    html = render_evening_report(report_context)
    _save_and_send(context, html, "evening")

    scheduler_logger.info("Evening job complete")


def hourly_scan_job(context: TradingContext | None = None) -> None:
    """Optional intraday scan: trades on fresh signals, no report/email."""
    context = context or build_trading_context()
    if not context.settings.hourly_scan_enabled:
        return

    scheduler_logger.info("Hourly scan starting")
    signals = run_trading_scan(context)
    _save_snapshot(context)
    scheduler_logger.info("Hourly scan complete: %d signal(s) evaluated", len(signals))


def _save_and_send(context: TradingContext, html: str, report_name: str) -> None:
    """Always save the report to disk (so it's available with no email configured); email it if configured."""
    context.settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = context.settings.reports_dir / f"{report_name}_{datetime.now():%Y%m%dT%H%M%S}.html"
    path.write_text(html, encoding="utf-8")

    subject = f"{report_name.title()} Trading Report - {datetime.now():%Y-%m-%d}"
    send_email(context.settings, subject, html)
    app_logger.info("%s report saved to %s", report_name.title(), path)

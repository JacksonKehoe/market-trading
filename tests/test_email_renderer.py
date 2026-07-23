from datetime import UTC, datetime

import pandas as pd

from app.email.renderer import render_evening_report, render_morning_report
from app.models.domain import Signal
from app.models.enums import SignalType


def _morning_context(**overrides: object) -> dict:
    base = {
        "generated_at": datetime.now(UTC),
        "strategy_name": "sma_crossover_20_50",
        "portfolio_value": 10_500.0,
        "cash": 5_000.0,
        "positions": [],
        "watchlist": ["AAPL", "MSFT"],
        "buy_signals": [Signal("AAPL", SignalType.BUY, datetime.now(UTC), 150.0, "test", "crossed up")],
        "sell_signals": [],
        "hold_count": 1,
        "market_movers": [{"symbol": "AAPL", "price": 150.0, "change_pct": 2.5}],
        "market_summary_pct": 1.2,
        "daily_trading_plan": ["1 BUY signal(s): AAPL"],
    }
    base.update(overrides)
    return base


def _evening_context(**overrides: object) -> dict:
    base = {
        "generated_at": datetime.now(UTC),
        "strategy_name": "sma_crossover_20_50",
        "portfolio_value": 10_500.0,
        "cash": 5_000.0,
        "day_pl": 500.0,
        "day_pl_pct": 5.0,
        "trades_today": [],
        "positions": [],
        "best_performer": None,
        "worst_performer": None,
        "equity_curve": pd.Series([10_000.0, 10_500.0], index=pd.date_range("2026-01-01", periods=2)),
        "risk_summary": {
            "allocation_pct": 40.0,
            "open_positions": 2,
            "max_open_positions": 5,
            "cash_reserve_pct": 60.0,
            "stop_loss_pct": 0.05,
            "take_profit_pct": 0.10,
            "daily_loss_limit_pct": 0.03,
        },
        "recommendations": ["No portfolio-level concerns detected."],
        "next_watchlist": ["MSFT"],
    }
    base.update(overrides)
    return base


def test_render_morning_report_includes_key_data() -> None:
    html = render_morning_report(_morning_context())

    assert "Morning Trading Report" in html
    assert "AAPL" in html
    assert "sma_crossover_20_50" in html
    assert "BUY" in html


def test_render_evening_report_includes_key_data_and_chart() -> None:
    html = render_evening_report(_evening_context())

    assert "Evening Trading Report" in html
    assert "plotly" in html.lower()
    assert "MSFT" in html  # next day's watchlist


def test_render_evening_report_handles_empty_equity_curve() -> None:
    html = render_evening_report(_evening_context(equity_curve=pd.Series(dtype=float)))

    assert "Not enough history yet" in html


def test_render_evening_report_handles_no_best_worst_performer() -> None:
    html = render_evening_report(_evening_context(best_performer=None, worst_performer=None))

    assert "Evening Trading Report" in html

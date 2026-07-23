from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.models.domain import Fill
from app.models.enums import OrderSide
from app.reporting.backtest import BacktestResult
from app.reporting.metrics import compute_metrics
from app.reporting.report_generator import generate_backtest_report


def _curve(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values), freq="D"))


def _fill(symbol: str, side: OrderSide, quantity: float, price: float, day: int) -> Fill:
    return Fill(
        order_id=f"order-{day}",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        commission=0.0,
        timestamp=datetime(2026, 1, day, tzinfo=UTC),
    )


def test_generate_backtest_report_writes_a_self_contained_html_file(tmp_path: Path) -> None:
    equity_curve = _curve([10_000.0, 10_200.0, 9_800.0, 10_500.0])
    trades = [
        _fill("AAPL", OrderSide.BUY, 10, 100.0, day=1),
        _fill("AAPL", OrderSide.SELL, 10, 120.0, day=3),
    ]
    result = BacktestResult(equity_curve=equity_curve, trades=trades, final_positions=[])
    metrics = compute_metrics(equity_curve, trades)

    path = generate_backtest_report(
        result,
        metrics,
        strategy_name="test_strategy",
        symbols=["AAPL"],
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 4),
        output_dir=tmp_path,
    )

    assert path.exists()
    assert path.parent == tmp_path
    html = path.read_text(encoding="utf-8")
    assert "test_strategy" in html
    assert "AAPL" in html
    assert "Backtest Report" in html
    # Plotly should have embedded chart markup, not left the placeholders unrendered.
    assert "plotly" in html.lower()


def test_generate_backtest_report_handles_no_trades(tmp_path: Path) -> None:
    equity_curve = _curve([10_000.0, 10_000.0])
    result = BacktestResult(equity_curve=equity_curve, trades=[], final_positions=[])
    metrics = compute_metrics(equity_curve, [])

    path = generate_backtest_report(
        result,
        metrics,
        strategy_name="idle_strategy",
        symbols=["AAPL"],
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 2),
        output_dir=tmp_path,
    )

    html = path.read_text(encoding="utf-8")
    assert "No trades were executed" in html


def test_generate_backtest_report_handles_infinite_profit_factor(tmp_path: Path) -> None:
    equity_curve = _curve([10_000.0, 10_200.0])
    trades = [
        _fill("AAPL", OrderSide.BUY, 10, 100.0, day=1),
        _fill("AAPL", OrderSide.SELL, 10, 120.0, day=2),
    ]
    result = BacktestResult(equity_curve=equity_curve, trades=trades, final_positions=[])
    metrics = compute_metrics(equity_curve, trades)
    assert metrics.profit_factor == float("inf")

    path = generate_backtest_report(
        result,
        metrics,
        strategy_name="winning_strategy",
        symbols=["AAPL"],
        start=datetime(2026, 1, 1),
        end=datetime(2026, 1, 2),
        output_dir=tmp_path,
    )

    html = path.read_text(encoding="utf-8")
    assert "∞" in html

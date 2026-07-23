from datetime import UTC, datetime

import pandas as pd
import pytest

from app.models.domain import Fill
from app.models.enums import OrderSide
from app.reporting.metrics import (
    average_gain,
    average_loss,
    cagr,
    compute_metrics,
    compute_trade_pnl,
    daily_returns,
    expectancy,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    total_return,
    win_rate,
)


def _curve(values: list[float], start: str = "2026-01-01") -> pd.Series:
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"))


def _fill(symbol: str, side: OrderSide, quantity: float, price: float, day: int, commission: float = 0.0) -> Fill:
    return Fill(
        order_id=f"order-{day}",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        commission=commission,
        timestamp=datetime(2026, 1, day, tzinfo=UTC),
    )


# --- daily_returns / total_return / cagr ----------------------------------------


def test_daily_returns_matches_pct_change() -> None:
    curve = _curve([100.0, 110.0, 99.0])
    returns = daily_returns(curve)

    assert returns.iloc[0] == pytest.approx(0.10)
    assert returns.iloc[1] == pytest.approx(-0.10)


def test_total_return_basic() -> None:
    curve = _curve([100.0, 150.0])
    assert total_return(curve) == pytest.approx(0.5)


def test_total_return_is_zero_for_single_point() -> None:
    assert total_return(_curve([100.0])) == 0.0


def test_cagr_for_a_one_year_doubling() -> None:
    curve = _curve([100.0] + [100.0] * 251 + [200.0])  # 252 trading-day periods = 1 year
    result = cagr(curve, periods_per_year=252)

    assert result == pytest.approx(1.0, abs=1e-6)


def test_cagr_is_zero_for_flat_or_short_curve() -> None:
    assert cagr(_curve([100.0])) == 0.0
    assert cagr(_curve([])) == 0.0


# --- sharpe_ratio ----------------------------------------------------------------


def test_sharpe_ratio_is_zero_for_zero_variance_returns() -> None:
    returns = pd.Series([0.01, 0.01, 0.01])
    assert sharpe_ratio(returns) == 0.0


def test_sharpe_ratio_is_zero_for_empty_returns() -> None:
    assert sharpe_ratio(pd.Series(dtype=float)) == 0.0


def test_sharpe_ratio_is_positive_for_consistently_positive_excess_returns() -> None:
    returns = pd.Series([0.01, 0.02, 0.015, 0.005, 0.012])
    assert sharpe_ratio(returns, risk_free_rate=0.0) > 0


# --- max_drawdown ------------------------------------------------------------------


def test_max_drawdown_known_peak_to_trough() -> None:
    curve = _curve([100.0, 120.0, 90.0, 110.0])
    assert max_drawdown(curve) == pytest.approx(90.0 / 120.0 - 1)


def test_max_drawdown_is_zero_for_monotonically_rising_curve() -> None:
    curve = _curve([100.0, 110.0, 120.0])
    assert max_drawdown(curve) == 0.0


def test_max_drawdown_is_zero_for_empty_curve() -> None:
    assert max_drawdown(_curve([])) == 0.0


# --- trade-level stats -------------------------------------------------------------


def test_win_rate_average_gain_loss_profit_factor_expectancy() -> None:
    trade_pnl = [100.0, -50.0, 200.0, -25.0]

    assert win_rate(trade_pnl) == pytest.approx(0.5)
    assert average_gain(trade_pnl) == pytest.approx(150.0)
    assert average_loss(trade_pnl) == pytest.approx(-37.5)
    assert profit_factor(trade_pnl) == pytest.approx(300.0 / 75.0)
    assert expectancy(trade_pnl) == pytest.approx(sum(trade_pnl) / 4)


def test_trade_stats_handle_empty_list() -> None:
    assert win_rate([]) == 0.0
    assert average_gain([]) == 0.0
    assert average_loss([]) == 0.0
    assert profit_factor([]) == 0.0
    assert expectancy([]) == 0.0


def test_profit_factor_is_infinite_with_no_losses() -> None:
    assert profit_factor([100.0, 50.0]) == float("inf")


# --- compute_trade_pnl -------------------------------------------------------------


def test_compute_trade_pnl_reconstructs_realized_pl_per_sell() -> None:
    trades = [
        _fill("AAPL", OrderSide.BUY, 10, 100.0, day=1),
        _fill("AAPL", OrderSide.SELL, 10, 120.0, day=2),
        _fill("MSFT", OrderSide.BUY, 5, 200.0, day=3),
        _fill("MSFT", OrderSide.SELL, 5, 180.0, day=4),
    ]

    pnl = compute_trade_pnl(trades)

    assert pnl == pytest.approx([200.0, -100.0])


def test_compute_trade_pnl_handles_partial_sells() -> None:
    trades = [
        _fill("AAPL", OrderSide.BUY, 10, 100.0, day=1),
        _fill("AAPL", OrderSide.SELL, 4, 110.0, day=2),
        _fill("AAPL", OrderSide.SELL, 6, 90.0, day=3),
    ]

    pnl = compute_trade_pnl(trades)

    assert pnl == pytest.approx([40.0, -60.0])


def test_compute_trade_pnl_is_empty_with_no_sells() -> None:
    trades = [_fill("AAPL", OrderSide.BUY, 10, 100.0, day=1)]
    assert compute_trade_pnl(trades) == []


# --- compute_metrics (integration) --------------------------------------------------


def test_compute_metrics_bundles_all_fields() -> None:
    curve = _curve([10_000.0, 10_500.0, 10_200.0, 11_000.0])
    trades = [
        _fill("AAPL", OrderSide.BUY, 10, 100.0, day=1),
        _fill("AAPL", OrderSide.SELL, 10, 120.0, day=2),
    ]

    metrics = compute_metrics(curve, trades)

    assert metrics.num_trades == 1
    assert metrics.total_return_pct == pytest.approx(total_return(curve) * 100)
    assert metrics.win_rate_pct == 100.0
    assert metrics.average_loss == 0.0

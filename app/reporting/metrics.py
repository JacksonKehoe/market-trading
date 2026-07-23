"""Performance analytics — pure functions over an equity curve and a trade list.

Nothing here talks to a broker, a database, or the network: every
function takes plain `pandas`/domain data and returns a number (or a
`PerformanceMetrics` bundle of them), which keeps this module trivially
unit-testable against hand-constructed fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.models.domain import Fill
from app.models.enums import OrderSide
from app.portfolio.portfolio import Portfolio

_TRADING_DAYS_PER_YEAR = 252


def compute_realized_pnl_by_fill(trades: list[Fill]) -> dict[str, float]:
    """Reconstruct realized P&L per closed (SELL) trade, keyed by fill id.

    Replays the fills, oldest first, through a scratch `Portfolio` — the
    same average-cost accounting `PaperBroker` uses live — rather than
    re-implementing the cost-basis math here. The scratch ledger is given
    unlimited cash since it exists purely to recover each fill's realized
    P&L, not to validate affordability (that already happened when the
    trade was actually placed).

    Keying by fill id (rather than just returning a plain list, as
    `compute_trade_pnl` does) lets a caller match each P&L figure back to
    *which* trade it belongs to -- e.g. a daily report showing today's
    closed trades alongside their realized gain/loss.
    """
    ledger = Portfolio(cash=float("inf"))
    realized: dict[str, float] = {}
    for fill in sorted(trades, key=lambda f: f.timestamp):
        pnl = ledger.apply_fill(fill)
        if fill.side == OrderSide.SELL:
            realized[fill.id] = pnl
    return realized


def compute_trade_pnl(trades: list[Fill]) -> list[float]:
    """Realized P&L per closed (SELL) trade, in chronological order. See `compute_realized_pnl_by_fill`."""
    return list(compute_realized_pnl_by_fill(trades).values())


def daily_returns(equity_curve: pd.Series) -> pd.Series:
    """Period-over-period percentage change (empty if fewer than 2 points)."""
    return equity_curve.pct_change().dropna()


def total_return(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2 or equity_curve.iloc[0] == 0:
        return 0.0
    return float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)


def cagr(equity_curve: pd.Series, periods_per_year: int = _TRADING_DAYS_PER_YEAR) -> float:
    """Compound Annual Growth Rate, annualized from the number of periods observed."""
    if len(equity_curve) < 2 or equity_curve.iloc[0] <= 0:
        return 0.0
    years = (len(equity_curve) - 1) / periods_per_year
    if years <= 0:
        return 0.0
    growth = equity_curve.iloc[-1] / equity_curve.iloc[0]
    if growth <= 0:
        return -1.0
    return float(growth ** (1 / years) - 1)


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = _TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sharpe ratio. 0.0 for empty or zero-variance return series."""
    if returns.empty or returns.std(ddof=0) == 0:
        return 0.0
    period_risk_free = risk_free_rate / periods_per_year
    excess_returns = returns - period_risk_free
    return float(excess_returns.mean() / returns.std(ddof=0) * (periods_per_year**0.5))


def max_drawdown(equity_curve: pd.Series) -> float:
    """Largest peak-to-trough decline, as a negative fraction (e.g. -0.23 for -23%)."""
    if equity_curve.empty:
        return 0.0
    running_max = equity_curve.cummax()
    drawdown = equity_curve / running_max - 1
    return float(drawdown.min())


def win_rate(trade_pnl: list[float]) -> float:
    if not trade_pnl:
        return 0.0
    wins = sum(1 for pnl in trade_pnl if pnl > 0)
    return wins / len(trade_pnl)


def average_gain(trade_pnl: list[float]) -> float:
    gains = [pnl for pnl in trade_pnl if pnl > 0]
    return sum(gains) / len(gains) if gains else 0.0


def average_loss(trade_pnl: list[float]) -> float:
    """Average losing trade, as a negative number (0.0 if there were no losses)."""
    losses = [pnl for pnl in trade_pnl if pnl < 0]
    return sum(losses) / len(losses) if losses else 0.0


def profit_factor(trade_pnl: list[float]) -> float:
    """Gross profit / gross loss. `inf` if there were profits and zero losses."""
    gross_profit = sum(pnl for pnl in trade_pnl if pnl > 0)
    gross_loss = -sum(pnl for pnl in trade_pnl if pnl < 0)
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def expectancy(trade_pnl: list[float]) -> float:
    """Average realized P&L per closed trade."""
    return sum(trade_pnl) / len(trade_pnl) if trade_pnl else 0.0


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    total_return_pct: float
    cagr_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    average_gain: float
    average_loss: float
    profit_factor: float
    expectancy: float
    num_trades: int
    """Count of *closed* (round-trip) trades -- i.e. SELL fills, not total fills."""


def compute_metrics(
    equity_curve: pd.Series,
    trades: list[Fill],
    risk_free_rate: float = 0.0,
    periods_per_year: int = _TRADING_DAYS_PER_YEAR,
) -> PerformanceMetrics:
    trade_pnl = compute_trade_pnl(trades)
    returns = daily_returns(equity_curve)

    return PerformanceMetrics(
        total_return_pct=total_return(equity_curve) * 100,
        cagr_pct=cagr(equity_curve, periods_per_year) * 100,
        sharpe_ratio=sharpe_ratio(returns, risk_free_rate, periods_per_year),
        max_drawdown_pct=max_drawdown(equity_curve) * 100,
        win_rate_pct=win_rate(trade_pnl) * 100,
        average_gain=average_gain(trade_pnl),
        average_loss=average_loss(trade_pnl),
        profit_factor=profit_factor(trade_pnl),
        expectancy=expectancy(trade_pnl),
        num_trades=len(trade_pnl),
    )

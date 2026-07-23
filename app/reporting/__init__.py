from app.reporting.backtest import Backtester, BacktestResult, ReplayMarketDataProvider
from app.reporting.charts import build_drawdown_chart, build_equity_curve_chart
from app.reporting.metrics import (
    PerformanceMetrics,
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
from app.reporting.report_generator import generate_backtest_report

__all__ = [
    "Backtester",
    "BacktestResult",
    "ReplayMarketDataProvider",
    "build_equity_curve_chart",
    "build_drawdown_chart",
    "PerformanceMetrics",
    "compute_metrics",
    "compute_trade_pnl",
    "daily_returns",
    "total_return",
    "cagr",
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "average_gain",
    "average_loss",
    "profit_factor",
    "expectancy",
    "generate_backtest_report",
]

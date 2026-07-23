#!/usr/bin/env python
"""Run a paper-trading strategy backtest from the command line.

    python run_backtest.py --symbols AAPL,MSFT --strategy sma --start 2024-01-01 --end 2025-01-01

This is a simulation only: it fetches historical market data, replays it
through the same paper trading engine used for live paper trading
(PaperBroker + RiskManager + ExecutionEngine), and saves an HTML report.
It never connects to a brokerage and never places a real trade.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta

from app.config.settings import Settings, get_settings
from app.data.factory import build_market_data_provider
from app.data.watchlist import load_watchlist
from app.reporting.backtest import Backtester
from app.reporting.metrics import compute_metrics
from app.reporting.report_generator import generate_backtest_report
from app.risk.rules import RiskLimits
from app.strategies.base import Strategy
from app.strategies.macd_strategy import MacdStrategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from app.strategies.rsi_strategy import RsiStrategy
from app.utils.logging_config import configure_logging

_STRATEGY_FACTORIES: dict[str, type] = {
    "sma": MovingAverageCrossoverStrategy,
    "rsi": RsiStrategy,
    "macd": MacdStrategy,
}


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbols", default=None, help="Comma-separated symbols (defaults to WATCHLIST)")
    parser.add_argument("--strategy", choices=sorted(_STRATEGY_FACTORIES), default="sma")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD (defaults to one year before --end)")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD (defaults to today)")
    parser.add_argument(
        "--benchmark", default="SPY", help="Benchmark symbol to compare against (empty string to disable)"
    )
    parser.add_argument("--initial-capital", type=float, default=None, help="Defaults to INITIAL_CAPITAL")
    return parser.parse_args(argv)


def _build_strategy(name: str) -> Strategy:
    return _STRATEGY_FACTORIES[name]()


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    args = _parse_args(argv)
    settings = settings or get_settings()
    configure_logging(settings.logs_dir)

    symbols = (
        [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        if args.symbols
        else load_watchlist(settings)
    )
    if not symbols:
        print("No symbols to backtest (empty --symbols and empty WATCHLIST).", file=sys.stderr)
        return 1

    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else end - timedelta(days=365)
    initial_capital = args.initial_capital if args.initial_capital is not None else settings.initial_capital
    benchmark_symbol = args.benchmark.strip().upper() if args.benchmark and args.benchmark.strip() else None

    strategy = _build_strategy(args.strategy)
    provider = build_market_data_provider(settings)
    risk_limits = RiskLimits.from_settings(settings)
    backtester = Backtester(
        data_provider=provider,
        initial_capital=initial_capital,
        risk_limits=risk_limits,
        commission_per_trade=settings.commission_per_trade,
    )

    result = backtester.run(strategy, symbols, start, end, benchmark_symbol=benchmark_symbol)
    metrics = compute_metrics(result.equity_curve, result.trades)
    report_path = generate_backtest_report(
        result, metrics, strategy.name, symbols, start, end, settings.reports_dir
    )

    print(f"Backtest: {strategy.name} on {', '.join(symbols)} from {start:%Y-%m-%d} to {end:%Y-%m-%d}")
    print(f"  Initial capital:  ${initial_capital:,.2f}")
    print(f"  Final equity:     ${result.equity_curve.iloc[-1]:,.2f}")
    print(f"  Total return:     {metrics.total_return_pct:.2f}%")
    print(f"  CAGR:             {metrics.cagr_pct:.2f}%")
    print(f"  Sharpe ratio:     {metrics.sharpe_ratio:.2f}")
    print(f"  Max drawdown:     {metrics.max_drawdown_pct:.2f}%")
    print(f"  Win rate:         {metrics.win_rate_pct:.1f}% ({metrics.num_trades} closed trades)")
    print(f"  Profit factor:    {metrics.profit_factor:.2f}")
    print(f"  Report saved to:  {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

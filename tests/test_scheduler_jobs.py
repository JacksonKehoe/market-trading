from pathlib import Path

from app.config.settings import Settings
from app.execution.engine import ExecutionEngine
from app.execution.paper_broker import PaperBroker
from app.models.enums import SignalType
from app.risk.risk_manager import RiskManager
from app.risk.rules import RiskLimits
from app.scheduler.context import TradingContext
from app.scheduler.jobs import evening_job, hourly_scan_job, morning_job, run_trading_scan
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from tests.conftest import FakeHistoricalMarketDataProvider, build_test_repository, make_price_frame


def _limits(**overrides: object) -> RiskLimits:
    defaults: dict[str, object] = dict(
        max_position_size_pct=1.0,
        max_portfolio_allocation_pct=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.20,
        daily_loss_limit_pct=None,
        max_open_positions=5,
    )
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def _build_context(tmp_path: Path, history: dict, watchlist: list[str], **settings_overrides: object) -> TradingContext:
    settings = Settings(
        database_path=tmp_path / "test.db",
        logs_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
        cache_dir=tmp_path / "cache",
        initial_capital=10_000.0,
        watchlist=watchlist,
        **settings_overrides,  # type: ignore[arg-type]
    )
    provider = FakeHistoricalMarketDataProvider(history)
    repository = build_test_repository(settings.database_path)
    broker = PaperBroker(settings.initial_capital, provider, settings.commission_per_trade)
    risk_limits = _limits()
    engine = ExecutionEngine(broker, provider, RiskManager(risk_limits), repository)
    strategy = MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)

    return TradingContext(
        settings=settings,
        data_provider=provider,
        repository=repository,
        broker=broker,
        engine=engine,
        strategy=strategy,
        watchlist=watchlist,
        risk_limits=risk_limits,
    )


def _crossing_history() -> dict:
    """A short price series whose fast/slow SMA (2/3) crosses up on the very last bar.

    `run_trading_scan` evaluates each symbol once against its *entire*
    fetched history, reacting only if the crossover falls on the last two
    bars -- so the test data needs the cross to land there, not buried
    somewhere in the middle of a longer series.
    """
    return {"AAPL": make_price_frame([5.0, 4.0, 3.0, 2.0, 10.0])}


def test_run_trading_scan_executes_trades_and_returns_signals(tmp_path: Path) -> None:
    context = _build_context(tmp_path, _crossing_history(), ["AAPL"])

    signals = run_trading_scan(context)

    assert len(signals) == 1
    assert signals[0].symbol == "AAPL"
    assert signals[0].signal_type == SignalType.BUY
    assert context.broker.get_positions() != []  # the BUY cleared RiskManager and was submitted


def test_run_trading_scan_skips_symbols_with_no_history(tmp_path: Path) -> None:
    context = _build_context(tmp_path, {}, ["MISSING"])

    signals = run_trading_scan(context)

    assert signals == []


def test_morning_job_persists_report_and_snapshot(tmp_path: Path) -> None:
    context = _build_context(tmp_path, _crossing_history(), ["AAPL"])

    morning_job(context)

    reports = list(context.settings.reports_dir.glob("morning_*.html"))
    assert len(reports) == 1
    assert "Morning Trading Report" in reports[0].read_text(encoding="utf-8")

    equity_curve = context.repository.equity_curve()
    assert not equity_curve.empty


def test_evening_job_persists_report_and_snapshot(tmp_path: Path) -> None:
    context = _build_context(tmp_path, _crossing_history(), ["AAPL"])

    evening_job(context)

    reports = list(context.settings.reports_dir.glob("evening_*.html"))
    assert len(reports) == 1
    assert "Evening Trading Report" in reports[0].read_text(encoding="utf-8")

    equity_curve = context.repository.equity_curve()
    assert not equity_curve.empty


def test_hourly_scan_job_is_noop_when_disabled(tmp_path: Path) -> None:
    context = _build_context(tmp_path, _crossing_history(), ["AAPL"], hourly_scan_enabled=False)

    hourly_scan_job(context)

    assert context.repository.equity_curve().empty  # nothing ran, nothing was saved


def test_hourly_scan_job_trades_when_enabled(tmp_path: Path) -> None:
    context = _build_context(tmp_path, _crossing_history(), ["AAPL"], hourly_scan_enabled=True)

    hourly_scan_job(context)

    assert not context.repository.equity_curve().empty

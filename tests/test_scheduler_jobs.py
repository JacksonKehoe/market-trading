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
from app.strategies.rsi_strategy import RsiStrategy
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


def _build_context(
    settings: Settings,
    provider: FakeHistoricalMarketDataProvider,
    repository,
    watchlist: list[str],
    strategy=None,
) -> TradingContext:
    broker = PaperBroker(settings.initial_capital, provider, settings.commission_per_trade)
    risk_limits = _limits()
    strategy = strategy or MovingAverageCrossoverStrategy(fast_window=2, slow_window=3)
    engine = ExecutionEngine(broker, provider, RiskManager(risk_limits), repository, strategy_name=strategy.name)

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


def _settings(tmp_path: Path, watchlist: list[str], **overrides: object) -> Settings:
    return Settings(
        database_path=tmp_path / "test.db",
        logs_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
        cache_dir=tmp_path / "cache",
        initial_capital=10_000.0,
        watchlist=watchlist,
        **overrides,  # type: ignore[arg-type]
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
    settings = _settings(tmp_path, ["AAPL"])
    provider = FakeHistoricalMarketDataProvider(_crossing_history())
    repository = build_test_repository(settings.database_path)
    context = _build_context(settings, provider, repository, ["AAPL"])

    signals = run_trading_scan(context)

    assert len(signals) == 1
    assert signals[0].symbol == "AAPL"
    assert signals[0].signal_type == SignalType.BUY
    assert context.broker.get_positions() != []  # the BUY cleared RiskManager and was submitted


def test_run_trading_scan_skips_symbols_with_no_history(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ["MISSING"])
    provider = FakeHistoricalMarketDataProvider({})
    repository = build_test_repository(settings.database_path)
    context = _build_context(settings, provider, repository, ["MISSING"])

    signals = run_trading_scan(context)

    assert signals == []


def test_morning_job_persists_comparison_report_and_snapshots(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ["AAPL"])
    provider = FakeHistoricalMarketDataProvider(_crossing_history())
    repository = build_test_repository(settings.database_path)
    sma_context = _build_context(settings, provider, repository, ["AAPL"])
    rsi_context = _build_context(settings, provider, repository, ["AAPL"], strategy=RsiStrategy())

    morning_job([sma_context, rsi_context])

    reports = list(settings.reports_dir.glob("morning_*.html"))
    assert len(reports) == 1
    html = reports[0].read_text(encoding="utf-8")
    assert "Morning Trading Report" in html
    assert sma_context.strategy.name in html
    assert rsi_context.strategy.name in html

    assert not repository.equity_curve(sma_context.strategy.name).empty
    assert not repository.equity_curve(rsi_context.strategy.name).empty


def test_evening_job_persists_comparison_report_and_snapshots(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ["AAPL"])
    provider = FakeHistoricalMarketDataProvider(_crossing_history())
    repository = build_test_repository(settings.database_path)
    sma_context = _build_context(settings, provider, repository, ["AAPL"])
    rsi_context = _build_context(settings, provider, repository, ["AAPL"], strategy=RsiStrategy())

    evening_job([sma_context, rsi_context])

    reports = list(settings.reports_dir.glob("evening_*.html"))
    assert len(reports) == 1
    assert "Evening Trading Report" in reports[0].read_text(encoding="utf-8")

    assert not repository.equity_curve(sma_context.strategy.name).empty
    assert not repository.equity_curve(rsi_context.strategy.name).empty


def test_hourly_scan_job_is_noop_when_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ["AAPL"], hourly_scan_enabled=False)
    provider = FakeHistoricalMarketDataProvider(_crossing_history())
    repository = build_test_repository(settings.database_path)
    context = _build_context(settings, provider, repository, ["AAPL"])

    hourly_scan_job([context])

    assert repository.equity_curve(context.strategy.name).empty  # nothing ran, nothing was saved


def test_hourly_scan_job_trades_when_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ["AAPL"], hourly_scan_enabled=True)
    provider = FakeHistoricalMarketDataProvider(_crossing_history())
    repository = build_test_repository(settings.database_path)
    context = _build_context(settings, provider, repository, ["AAPL"])

    hourly_scan_job([context])

    assert not repository.equity_curve(context.strategy.name).empty


def test_two_strategies_trade_independently_in_the_same_job_run(tmp_path: Path) -> None:
    settings = _settings(tmp_path, ["AAPL"])
    provider = FakeHistoricalMarketDataProvider(_crossing_history())
    repository = build_test_repository(settings.database_path)
    sma_context = _build_context(settings, provider, repository, ["AAPL"])
    rsi_context = _build_context(settings, provider, repository, ["AAPL"], strategy=RsiStrategy())

    morning_job([sma_context, rsi_context])

    # SMA's crossover fires on this data; RSI's oversold-bounce condition does not,
    # so their resulting positions should differ -- independent accounts, independent outcomes.
    sma_positions = repository.list_open_positions(sma_context.strategy.name)
    rsi_positions = repository.list_open_positions(rsi_context.strategy.name)
    assert len(sma_positions) == 1
    assert len(rsi_positions) == 0

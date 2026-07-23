from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings
from app.email.report_data import build_evening_report_context, build_morning_report_context
from app.execution.paper_broker import PaperBroker
from app.models.domain import Order, Signal
from app.models.enums import OrderSide, SignalType
from app.risk.rules import RiskLimits
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from tests.conftest import FakeMarketDataProvider, build_test_repository


def _limits(**overrides: object) -> RiskLimits:
    defaults: dict[str, object] = dict(
        max_position_size_pct=0.5,
        max_portfolio_allocation_pct=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        daily_loss_limit_pct=0.03,
        max_open_positions=5,
    )
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def _signal(symbol: str, signal_type: SignalType, price: float = 150.0) -> Signal:
    return Signal(symbol, signal_type, datetime.now(UTC), price, "test", "test reason")


def test_morning_report_context_summarizes_signals_and_account() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0, "MSFT": 300.0})
    broker = PaperBroker(10_000.0, provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=5))
    strategy = MovingAverageCrossoverStrategy()
    signals = [_signal("AAPL", SignalType.HOLD), _signal("MSFT", SignalType.BUY)]

    context = build_morning_report_context(
        Settings(), broker, provider, strategy, ["AAPL", "MSFT"], signals
    )

    assert context["portfolio_value"] == broker.get_account().equity
    assert len(context["buy_signals"]) == 1
    assert context["buy_signals"][0].symbol == "MSFT"
    assert context["hold_count"] == 1
    assert len(context["positions"]) == 1
    assert context["positions"][0]["symbol"] == "AAPL"
    assert context["daily_trading_plan"]  # non-empty


def test_morning_report_context_default_plan_when_no_signals() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker = PaperBroker(10_000.0, provider)
    strategy = MovingAverageCrossoverStrategy()

    context = build_morning_report_context(Settings(), broker, provider, strategy, ["AAPL"], [])

    assert context["buy_signals"] == []
    assert context["sell_signals"] == []
    assert "No new signals" in context["daily_trading_plan"][0]


def test_evening_report_context_computes_day_pl_and_trades_today(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 160.0})
    broker = PaperBroker(10_000.0, provider)
    repository = build_test_repository(tmp_path / "test.db")
    repository.save_account_snapshot(broker.get_account())  # yesterday's baseline @ $10,000

    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="test")
    fill = broker.submit_order(order)
    repository.save_fill(fill, order)

    strategy = MovingAverageCrossoverStrategy()
    context = build_evening_report_context(
        Settings(), broker, provider, repository, strategy, ["AAPL"], _limits()
    )

    assert context["portfolio_value"] == broker.get_account().equity
    assert len(context["trades_today"]) == 1
    assert context["trades_today"][0]["fill"].symbol == "AAPL"
    assert context["trades_today"][0]["pnl"] is None  # BUY, not a closed trade
    assert context["day_pl"] != 0  # equity moved from the baseline snapshot
    assert context["risk_summary"]["open_positions"] == 1
    assert context["risk_summary"]["max_open_positions"] == 5


def test_evening_report_context_best_worst_performer(tmp_path: Path) -> None:
    entry_provider = FakeMarketDataProvider({"AAPL": 100.0, "MSFT": 100.0})
    broker = PaperBroker(20_000.0, entry_provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10))
    broker.submit_order(Order(symbol="MSFT", side=OrderSide.BUY, quantity=10))

    # Prices move after entry: AAPL up, MSFT down.
    entry_provider.set_price("AAPL", 120.0)
    entry_provider.set_price("MSFT", 90.0)

    repository = build_test_repository(tmp_path / "test.db")
    strategy = MovingAverageCrossoverStrategy()
    context = build_evening_report_context(
        Settings(), broker, entry_provider, repository, strategy, ["AAPL", "MSFT"], _limits()
    )

    assert context["best_performer"]["symbol"] == "AAPL"
    assert context["worst_performer"]["symbol"] == "MSFT"

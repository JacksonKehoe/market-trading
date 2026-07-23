from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings
from app.email.report_data import StrategyState, build_evening_report_context, build_morning_report_context
from app.execution.paper_broker import PaperBroker
from app.models.domain import Order, Signal
from app.models.enums import OrderSide, SignalType
from app.risk.rules import RiskLimits
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


def _signal(symbol: str, signal_type: SignalType, strategy_name: str = "test", price: float = 150.0) -> Signal:
    return Signal(symbol, signal_type, datetime.now(UTC), price, strategy_name, "test reason")


def test_morning_report_context_summarizes_signals_and_comparison() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0, "MSFT": 300.0})
    broker = PaperBroker(10_000.0, provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=5))
    signals = [_signal("AAPL", SignalType.HOLD, "sma"), _signal("MSFT", SignalType.BUY, "sma")]
    strategies = [StrategyState("sma", broker, signals)]

    context = build_morning_report_context(Settings(), provider, ["AAPL", "MSFT"], strategies)

    assert context["comparison"][0]["equity"] == broker.get_account().equity
    assert context["comparison"][0]["buy_signals"] == 1
    assert len(context["buy_signals"]) == 1
    assert context["buy_signals"][0].symbol == "MSFT"
    assert context["hold_count"] == 1
    assert len(context["positions"]) == 1
    assert context["positions"][0]["symbol"] == "AAPL"
    assert context["positions"][0]["strategy"] == "sma"
    assert context["daily_trading_plan"]  # non-empty


def test_morning_report_context_default_plan_when_no_signals() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker = PaperBroker(10_000.0, provider)
    strategies = [StrategyState("sma", broker, [])]

    context = build_morning_report_context(Settings(), provider, ["AAPL"], strategies)

    assert context["buy_signals"] == []
    assert context["sell_signals"] == []
    assert "No new signals" in context["daily_trading_plan"][0]


def test_morning_report_context_combines_multiple_strategies() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker_a = PaperBroker(10_000.0, provider)
    broker_b = PaperBroker(10_000.0, provider)
    strategies = [
        StrategyState("sma", broker_a, [_signal("AAPL", SignalType.BUY, "sma")]),
        StrategyState("rsi", broker_b, [_signal("AAPL", SignalType.HOLD, "rsi")]),
    ]

    context = build_morning_report_context(Settings(), provider, ["AAPL"], strategies)

    assert len(context["comparison"]) == 2
    assert {c["strategy"] for c in context["comparison"]} == {"sma", "rsi"}
    assert len(context["buy_signals"]) == 1


def test_evening_report_context_computes_day_pl_and_trades_today(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 160.0})
    broker = PaperBroker(10_000.0, provider)
    repository = build_test_repository(tmp_path / "test.db")
    repository.save_account_snapshot(broker.get_account(), "sma")  # yesterday's baseline @ $10,000

    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="sma")
    fill = broker.submit_order(order)
    repository.save_fill(fill, order)

    strategies = [StrategyState("sma", broker)]
    context = build_evening_report_context(
        Settings(), provider, repository, ["AAPL"], _limits(), strategies
    )

    assert context["comparison"][0]["equity"] == broker.get_account().equity
    assert len(context["trades_today"]) == 1
    assert context["trades_today"][0]["fill"].symbol == "AAPL"
    assert context["trades_today"][0]["pnl"] is None  # BUY, not a closed trade
    assert context["trades_today"][0]["strategy"] == "sma"
    assert context["comparison"][0]["day_pl"] != 0  # equity moved from the baseline snapshot
    assert context["risk_summary"][0]["open_positions"] == 1
    assert context["risk_summary"][0]["max_open_positions"] == 5


def test_evening_report_context_best_worst_strategy(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 100.0})
    broker_a = PaperBroker(10_000.0, provider)
    broker_b = PaperBroker(10_000.0, provider)
    broker_a.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="sma"))
    broker_b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="rsi"))

    repository = build_test_repository(tmp_path / "test.db")
    repository.save_account_snapshot(broker_a.get_account(), "sma")
    repository.save_account_snapshot(broker_b.get_account(), "rsi")

    # Strategy sma's holding gains, rsi's is flat -- sma should come out ahead today.
    provider.set_price("AAPL", 120.0)

    strategies = [StrategyState("sma", broker_a), StrategyState("rsi", broker_b)]
    context = build_evening_report_context(
        Settings(), provider, repository, ["AAPL"], _limits(), strategies
    )

    assert context["best_strategy"]["strategy"] == "sma"


def test_evening_report_context_recommends_when_at_max_positions(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 100.0})
    broker = PaperBroker(10_000.0, provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=1, strategy_name="sma"))
    repository = build_test_repository(tmp_path / "test.db")
    strategies = [StrategyState("sma", broker)]

    context = build_evening_report_context(
        Settings(), provider, repository, ["AAPL"], _limits(max_open_positions=1), strategies
    )

    assert any("max open positions" in line for line in context["recommendations"])

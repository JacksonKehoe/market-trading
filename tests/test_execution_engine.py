from datetime import UTC, datetime

from app.execution.engine import ExecutionEngine
from app.execution.paper_broker import PaperBroker
from app.models.domain import Signal
from app.models.enums import SignalType
from app.risk.risk_manager import RiskManager
from app.risk.rules import RiskLimits
from tests.conftest import FakeMarketDataProvider


def _limits(**overrides: object) -> RiskLimits:
    defaults: dict[str, object] = dict(
        max_position_size_pct=0.5,
        max_portfolio_allocation_pct=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        daily_loss_limit_pct=None,
        max_open_positions=5,
    )
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def _signal(
    symbol: str = "AAPL", signal_type: SignalType = SignalType.BUY, price: float = 150.0
) -> Signal:
    return Signal(
        symbol=symbol,
        signal_type=signal_type,
        timestamp=datetime.now(UTC),
        price=price,
        strategy_name="test",
    )


def _engine(provider: FakeMarketDataProvider, cash: float = 10_000, **limit_overrides: object):
    broker = PaperBroker(initial_cash=cash, data_provider=provider)
    engine = ExecutionEngine(broker, provider, RiskManager(_limits(**limit_overrides)))
    return engine, broker


def test_process_signal_buys_and_returns_fill() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    engine, broker = _engine(provider)

    fill = engine.process_signal(_signal())

    assert fill is not None
    assert fill.symbol == "AAPL"
    assert broker.get_positions()[0].quantity == fill.quantity


def test_process_signal_hold_is_noop() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    engine, broker = _engine(provider)

    fill = engine.process_signal(_signal(signal_type=SignalType.HOLD))

    assert fill is None
    assert broker.get_positions() == []


def test_process_signal_rejected_by_risk_manager_is_noop() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    engine, broker = _engine(provider, max_open_positions=0)

    fill = engine.process_signal(_signal())

    assert fill is None
    assert broker.get_cash_balance() == 10_000


def test_run_exit_checks_closes_stop_loss_position() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    engine, broker = _engine(provider, stop_loss_pct=0.05)
    engine.process_signal(_signal())  # opens a position

    provider.set_price("AAPL", 140.0)  # -6.7% breach
    fills = engine.run_exit_checks()

    assert len(fills) == 1
    assert fills[0].symbol == "AAPL"
    assert broker.get_positions() == []


def test_daily_loss_limit_blocks_new_buys_after_start_new_trading_day() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0, "MSFT": 100.0})
    engine, broker = _engine(provider, daily_loss_limit_pct=0.03, max_position_size_pct=1.0)
    engine.start_new_trading_day()

    # Simulate a big loss during the day by force-crashing the position value.
    engine.process_signal(_signal(symbol="AAPL"))
    provider.set_price("AAPL", 100.0)  # equity now well below the 3% daily loss threshold

    fill = engine.process_signal(_signal(symbol="MSFT"))

    assert fill is None

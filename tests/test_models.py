from datetime import datetime

from app.models.domain import Account, Fill, Order, Position, Signal
from app.models.enums import OrderSide, OrderStatus, SignalType


def test_signal_is_immutable_and_typed() -> None:
    signal = Signal(
        symbol="AAPL",
        signal_type=SignalType.BUY,
        timestamp=datetime(2026, 1, 2),
        price=150.0,
        strategy_name="sma_crossover",
    )
    assert signal.signal_type == SignalType.BUY
    assert signal.symbol == "AAPL"


def test_order_defaults_to_pending_market_order() -> None:
    order = Order(symbol="MSFT", side=OrderSide.BUY, quantity=10)
    assert order.status == OrderStatus.PENDING
    assert order.id  # auto-generated
    assert order.limit_price is None


def test_position_pl_and_cost_basis() -> None:
    position = Position(symbol="SPY", quantity=10, avg_entry_price=400.0, opened_at=datetime(2026, 1, 1))
    assert position.cost_basis == 4000.0
    assert position.unrealized_pl(420.0) == 200.0
    assert position.unrealized_pl(390.0) == -100.0


def test_account_equity_is_cash_plus_positions() -> None:
    account = Account(timestamp=datetime(2026, 1, 1), cash=5000.0, positions_value=15000.0)
    assert account.equity == 20000.0


def test_fill_carries_a_generated_id() -> None:
    fill = Fill(
        order_id="abc123",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=5,
        price=155.0,
        commission=0.0,
        timestamp=datetime(2026, 1, 2),
    )
    assert fill.id
    assert fill.order_id == "abc123"

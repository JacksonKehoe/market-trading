import pytest

from app.execution.paper_broker import PaperBroker
from app.models.domain import Order
from app.models.enums import OrderSide, OrderStatus
from app.portfolio.portfolio import InsufficientFundsError
from tests.conftest import FakeMarketDataProvider


def test_submit_buy_order_fills_at_market_price_and_updates_state() -> None:
    broker = PaperBroker(initial_cash=10_000, data_provider=FakeMarketDataProvider({"AAPL": 150.0}))
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)

    fill = broker.submit_order(order)

    assert fill.price == 150.0
    assert order.status == OrderStatus.FILLED
    assert broker.get_cash_balance() == 10_000 - 1_500
    assert broker.get_positions() == [broker.portfolio.positions["AAPL"]]


def test_submit_order_beyond_cash_rejects_order_and_raises() -> None:
    broker = PaperBroker(initial_cash=100, data_provider=FakeMarketDataProvider({"AAPL": 150.0}))
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)

    with pytest.raises(InsufficientFundsError):
        broker.submit_order(order)

    assert order.status == OrderStatus.REJECTED
    assert broker.get_positions() == []


def test_get_account_marks_positions_to_current_market_price() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker = PaperBroker(initial_cash=10_000, data_provider=provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10))

    provider.set_price("AAPL", 160.0)
    account = broker.get_account()

    assert account.cash == 8_500
    assert account.positions_value == 1_600
    assert account.equity == 10_100


def test_commission_is_applied_on_fill() -> None:
    broker = PaperBroker(
        initial_cash=10_000,
        data_provider=FakeMarketDataProvider({"AAPL": 150.0}),
        commission_per_trade=1.5,
    )
    fill = broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10))

    assert fill.commission == 1.5
    assert broker.get_cash_balance() == 10_000 - 1_500 - 1.5

from datetime import UTC, datetime

import pytest

from app.models.domain import Fill
from app.models.enums import OrderSide
from app.portfolio.portfolio import InsufficientFundsError, InsufficientSharesError, Portfolio


def _fill(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 10,
    price: float = 100.0,
    commission: float = 0.0,
) -> Fill:
    return Fill(
        order_id="order-1",
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        commission=commission,
        timestamp=datetime.now(UTC),
    )


def test_buy_reduces_cash_and_opens_position() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0))

    assert portfolio.cash == 9_000
    assert portfolio.positions["AAPL"].quantity == 10
    assert portfolio.positions["AAPL"].avg_entry_price == 100.0


def test_buy_averages_entry_price_on_second_fill() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0))
    portfolio.apply_fill(_fill(quantity=10, price=120.0))

    position = portfolio.positions["AAPL"]
    assert position.quantity == 20
    assert position.avg_entry_price == 110.0


def test_buy_beyond_cash_raises_and_leaves_state_unchanged() -> None:
    portfolio = Portfolio(cash=500)
    with pytest.raises(InsufficientFundsError):
        portfolio.apply_fill(_fill(quantity=10, price=100.0))

    assert portfolio.cash == 500
    assert portfolio.positions == {}


def test_commission_is_deducted_on_buy() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0, commission=5.0))
    assert portfolio.cash == 10_000 - 1_000 - 5.0


def test_sell_increases_cash_and_realizes_pl() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0))
    portfolio.apply_fill(_fill(side=OrderSide.SELL, quantity=10, price=120.0))

    assert portfolio.cash == 10_000 - 1_000 + 1_200
    assert portfolio.realized_pl == 200.0
    assert "AAPL" not in portfolio.positions


def test_partial_sell_keeps_remaining_position_at_same_avg_price() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0))
    portfolio.apply_fill(_fill(side=OrderSide.SELL, quantity=4, price=110.0))

    position = portfolio.positions["AAPL"]
    assert position.quantity == 6
    assert position.avg_entry_price == 100.0
    assert portfolio.realized_pl == 40.0


def test_sell_more_than_held_raises() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=5, price=100.0))
    with pytest.raises(InsufficientSharesError):
        portfolio.apply_fill(_fill(side=OrderSide.SELL, quantity=10, price=100.0))


def test_sell_with_no_position_raises() -> None:
    portfolio = Portfolio(cash=10_000)
    with pytest.raises(InsufficientSharesError):
        portfolio.apply_fill(_fill(side=OrderSide.SELL, quantity=1, price=100.0))


def test_equity_and_unrealized_pl() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0))

    prices = {"AAPL": 110.0}
    assert portfolio.equity(prices) == 10_100.0
    assert portfolio.unrealized_pl(prices) == 100.0


def test_to_account_matches_cash_and_positions_value() -> None:
    portfolio = Portfolio(cash=10_000)
    portfolio.apply_fill(_fill(quantity=10, price=100.0))

    account = portfolio.to_account({"AAPL": 105.0}, datetime.now(UTC))
    assert account.cash == 9_000
    assert account.positions_value == 1_050.0
    assert account.equity == 10_050.0

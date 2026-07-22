from datetime import UTC, datetime

from app.models.domain import Account, Position, Signal
from app.models.enums import SignalType
from app.risk.risk_manager import RiskManager
from app.risk.rules import RiskLimits


def _limits(**overrides: object) -> RiskLimits:
    defaults: dict[str, object] = dict(
        max_position_size_pct=0.25,
        max_portfolio_allocation_pct=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        daily_loss_limit_pct=0.03,
        max_open_positions=5,
    )
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def _signal(
    symbol: str = "AAPL", signal_type: SignalType = SignalType.BUY, price: float = 100.0
) -> Signal:
    return Signal(
        symbol=symbol,
        signal_type=signal_type,
        timestamp=datetime.now(UTC),
        price=price,
        strategy_name="test",
    )


def _account(cash: float = 10_000.0, positions_value: float = 0.0) -> Account:
    return Account(timestamp=datetime.now(UTC), cash=cash, positions_value=positions_value)


def _position(symbol: str = "AAPL", quantity: float = 5, avg_entry_price: float = 90.0) -> Position:
    return Position(symbol=symbol, quantity=quantity, avg_entry_price=avg_entry_price, opened_at=datetime.now(UTC))


def test_buy_sizes_order_within_max_position_pct() -> None:
    manager = RiskManager(_limits(max_position_size_pct=0.25))
    decision = manager.evaluate_signal(_signal(price=100.0), 100.0, _account(cash=10_000), [])

    assert decision.approved
    assert decision.order is not None
    assert decision.order.quantity == 25  # 25% of $10,000 equity / $100 price


def test_buy_capped_by_available_allocation_not_just_position_size() -> None:
    manager = RiskManager(_limits(max_position_size_pct=1.0, max_portfolio_allocation_pct=0.5))
    account = _account(cash=10_000, positions_value=4_000)  # equity 14,000, 50% cap = 7,000 already 4,000 invested
    decision = manager.evaluate_signal(_signal(price=100.0), 100.0, account, [])

    assert decision.approved
    assert decision.order is not None
    # available_allocation = 14,000*0.5 - 4,000 = 3,000; capped further by cash (10,000) -> 3,000 -> 30 shares
    assert decision.order.quantity == 30


def test_buy_rejected_if_already_holding() -> None:
    manager = RiskManager(_limits())
    decision = manager.evaluate_signal(_signal(), 100.0, _account(), [_position()])

    assert not decision.approved
    assert "Already holding" in decision.reason


def test_buy_rejected_at_max_open_positions() -> None:
    manager = RiskManager(_limits(max_open_positions=1))
    existing = _position(symbol="MSFT")
    decision = manager.evaluate_signal(_signal(symbol="AAPL"), 100.0, _account(), [existing])

    assert not decision.approved
    assert "Max open positions" in decision.reason


def test_buy_rejected_on_daily_loss_limit() -> None:
    manager = RiskManager(_limits(daily_loss_limit_pct=0.03))
    account = _account(cash=9_600.0)  # equity 9,600 vs start 10,000 -> -4%

    decision = manager.evaluate_signal(_signal(), 100.0, account, [], daily_start_equity=10_000.0)

    assert not decision.approved
    assert "Daily loss limit" in decision.reason


def test_buy_allowed_when_daily_loss_within_limit() -> None:
    manager = RiskManager(_limits(daily_loss_limit_pct=0.03))
    account = _account(cash=9_900.0)  # -1%, within the 3% limit

    decision = manager.evaluate_signal(_signal(), 100.0, account, [], daily_start_equity=10_000.0)

    assert decision.approved


def test_buy_rejected_when_insufficient_capital_for_one_share() -> None:
    manager = RiskManager(_limits(max_position_size_pct=0.01))
    decision = manager.evaluate_signal(_signal(price=10_000.0), 10_000.0, _account(cash=10_000), [])

    assert not decision.approved
    assert "Insufficient capital" in decision.reason


def test_sell_approved_when_holding() -> None:
    manager = RiskManager(_limits())
    position = _position(quantity=10)
    decision = manager.evaluate_signal(
        _signal(signal_type=SignalType.SELL), 100.0, _account(), [position]
    )

    assert decision.approved
    assert decision.order is not None
    assert decision.order.quantity == 10


def test_sell_rejected_when_not_holding() -> None:
    manager = RiskManager(_limits())
    decision = manager.evaluate_signal(_signal(signal_type=SignalType.SELL), 100.0, _account(), [])

    assert not decision.approved
    assert "No open position" in decision.reason


def test_hold_signal_is_never_approved() -> None:
    manager = RiskManager(_limits())
    decision = manager.evaluate_signal(_signal(signal_type=SignalType.HOLD), 100.0, _account(), [])

    assert not decision.approved


def test_check_exits_triggers_stop_loss_and_take_profit_but_not_small_moves() -> None:
    manager = RiskManager(_limits(stop_loss_pct=0.05, take_profit_pct=0.10))
    positions = [
        _position(symbol="AAPL", avg_entry_price=100.0),  # priced at -6% -> stop loss
        _position(symbol="MSFT", avg_entry_price=100.0),  # priced at +12% -> take profit
        _position(symbol="SPY", avg_entry_price=100.0),  # priced at +1% -> no action
    ]
    prices = {"AAPL": 94.0, "MSFT": 112.0, "SPY": 101.0}

    orders = manager.check_exits(positions, prices)

    symbols = {order.symbol for order in orders}
    assert symbols == {"AAPL", "MSFT"}
    for order in orders:
        assert order.strategy_name.startswith("risk:")

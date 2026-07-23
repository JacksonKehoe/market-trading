from datetime import UTC, datetime
from pathlib import Path

from app.models.domain import Account, Fill, Order
from app.models.enums import OrderSide
from tests.conftest import build_test_repository


def test_save_fill_persists_trade_and_upserts_position(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="test")
    fill = Fill(
        order_id=order.id,
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=150.0,
        commission=1.0,
        timestamp=datetime.now(UTC),
    )

    repo.save_fill(fill, order)

    trades = repo.list_trades()
    assert len(trades) == 1
    assert trades[0].symbol == "AAPL"
    assert trades[0].commission == 1.0

    positions = repo.list_open_positions("test")
    assert len(positions) == 1
    assert positions[0].quantity == 10
    assert positions[0].avg_entry_price == 150.0


def test_second_buy_averages_position_entry_price(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    first = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="test")
    repo.save_fill(
        Fill(order_id=first.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0, commission=0.0, timestamp=datetime.now(UTC)),
        first,
    )
    second = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="test")
    repo.save_fill(
        Fill(order_id=second.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=120.0, commission=0.0, timestamp=datetime.now(UTC)),
        second,
    )

    positions = repo.list_open_positions("test")
    assert len(positions) == 1
    assert positions[0].quantity == 20
    assert positions[0].avg_entry_price == 110.0


def test_sell_reduces_and_removes_position(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    buy_order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="test")
    repo.save_fill(
        Fill(order_id=buy_order.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0, commission=0.0, timestamp=datetime.now(UTC)),
        buy_order,
    )
    sell_order = Order(symbol="AAPL", side=OrderSide.SELL, quantity=10, strategy_name="test")
    repo.save_fill(
        Fill(order_id=sell_order.id, symbol="AAPL", side=OrderSide.SELL, quantity=10, price=160.0, commission=0.0, timestamp=datetime.now(UTC)),
        sell_order,
    )

    assert repo.list_open_positions("test") == []
    assert len(repo.list_trades()) == 2
    assert len(repo.list_trades(symbol="AAPL")) == 2
    assert repo.list_trades(symbol="MSFT") == []


def test_positions_are_isolated_per_strategy(tmp_path: Path) -> None:
    """Two strategies can each hold their own position in the same symbol."""
    repo = build_test_repository(tmp_path / "test.db")
    order_a = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="strategy_a")
    repo.save_fill(
        Fill(order_id=order_a.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0, commission=0.0, timestamp=datetime.now(UTC)),
        order_a,
    )
    order_b = Order(symbol="AAPL", side=OrderSide.BUY, quantity=5, strategy_name="strategy_b")
    repo.save_fill(
        Fill(order_id=order_b.id, symbol="AAPL", side=OrderSide.BUY, quantity=5, price=200.0, commission=0.0, timestamp=datetime.now(UTC)),
        order_b,
    )

    positions_a = repo.list_open_positions("strategy_a")
    positions_b = repo.list_open_positions("strategy_b")

    assert len(positions_a) == 1 and positions_a[0].quantity == 10 and positions_a[0].avg_entry_price == 100.0
    assert len(positions_b) == 1 and positions_b[0].quantity == 5 and positions_b[0].avg_entry_price == 200.0

    # Selling all of strategy_a's AAPL must not touch strategy_b's position.
    sell_a = Order(symbol="AAPL", side=OrderSide.SELL, quantity=10, strategy_name="strategy_a")
    repo.save_fill(
        Fill(order_id=sell_a.id, symbol="AAPL", side=OrderSide.SELL, quantity=10, price=110.0, commission=0.0, timestamp=datetime.now(UTC)),
        sell_a,
    )
    assert repo.list_open_positions("strategy_a") == []
    assert len(repo.list_open_positions("strategy_b")) == 1


def test_save_account_snapshot_does_not_raise(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    repo.save_account_snapshot(
        Account(timestamp=datetime.now(UTC), cash=9_000.0, positions_value=1_000.0), "test"
    )

    assert (tmp_path / "test.db").exists()


def test_latest_cash_balance_is_none_with_no_snapshots(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    assert repo.latest_cash_balance("test") is None


def test_latest_cash_balance_returns_most_recent_snapshot(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    repo.save_account_snapshot(Account(timestamp=datetime(2026, 1, 1, tzinfo=UTC), cash=9_000.0, positions_value=0.0), "test")
    repo.save_account_snapshot(Account(timestamp=datetime(2026, 1, 2, tzinfo=UTC), cash=9_500.0, positions_value=0.0), "test")

    assert repo.latest_cash_balance("test") == 9_500.0


def test_latest_cash_balance_is_isolated_per_strategy(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    repo.save_account_snapshot(Account(timestamp=datetime.now(UTC), cash=7_000.0, positions_value=0.0), "strategy_a")
    repo.save_account_snapshot(Account(timestamp=datetime.now(UTC), cash=12_000.0, positions_value=0.0), "strategy_b")

    assert repo.latest_cash_balance("strategy_a") == 7_000.0
    assert repo.latest_cash_balance("strategy_b") == 12_000.0


def test_equity_curve_reflects_saved_snapshots_in_order(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    repo.save_account_snapshot(Account(timestamp=datetime(2026, 1, 2, tzinfo=UTC), cash=10_500.0, positions_value=0.0), "test")
    repo.save_account_snapshot(Account(timestamp=datetime(2026, 1, 1, tzinfo=UTC), cash=10_000.0, positions_value=0.0), "test")

    curve = repo.equity_curve("test")

    assert list(curve.values) == [10_000.0, 10_500.0]
    assert curve.index.is_monotonic_increasing


def test_equity_curve_is_empty_series_with_no_snapshots(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    curve = repo.equity_curve("test")
    assert curve.empty


def test_equity_curve_is_isolated_per_strategy(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    repo.save_account_snapshot(Account(timestamp=datetime.now(UTC), cash=10_000.0, positions_value=0.0), "strategy_a")
    repo.save_account_snapshot(Account(timestamp=datetime.now(UTC), cash=20_000.0, positions_value=0.0), "strategy_b")

    assert list(repo.equity_curve("strategy_a").values) == [10_000.0]
    assert list(repo.equity_curve("strategy_b").values) == [20_000.0]


def test_list_trades_since_filters_by_timestamp(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    old_order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1)
    repo.save_fill(
        Fill(order_id=old_order.id, symbol="AAPL", side=OrderSide.BUY, quantity=1, price=100.0, commission=0.0, timestamp=datetime(2026, 1, 1, tzinfo=UTC)),
        old_order,
    )
    new_order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1)
    repo.save_fill(
        Fill(order_id=new_order.id, symbol="AAPL", side=OrderSide.BUY, quantity=1, price=110.0, commission=0.0, timestamp=datetime(2026, 1, 10, tzinfo=UTC)),
        new_order,
    )

    recent = repo.list_trades(since=datetime(2026, 1, 5, tzinfo=UTC))

    assert len(recent) == 1
    assert recent[0].price == 110.0


def test_list_trades_filters_by_strategy_name(tmp_path: Path) -> None:
    repo = build_test_repository(tmp_path / "test.db")
    order_a = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1, strategy_name="strategy_a")
    repo.save_fill(
        Fill(order_id=order_a.id, symbol="AAPL", side=OrderSide.BUY, quantity=1, price=100.0, commission=0.0, timestamp=datetime.now(UTC)),
        order_a,
    )
    order_b = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1, strategy_name="strategy_b")
    repo.save_fill(
        Fill(order_id=order_b.id, symbol="AAPL", side=OrderSide.BUY, quantity=1, price=200.0, commission=0.0, timestamp=datetime.now(UTC)),
        order_b,
    )

    assert len(repo.list_trades(strategy_name="strategy_a")) == 1
    assert repo.list_trades(strategy_name="strategy_a")[0].price == 100.0
    assert len(repo.list_trades()) == 2

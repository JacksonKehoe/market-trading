from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.engine import Base
from app.database.repository import SqlTradeRepository
from app.models.domain import Account, Fill, Order
from app.models.enums import OrderSide


def _session_factory(db_path: Path) -> sessionmaker:
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_save_fill_persists_trade_and_upserts_position(tmp_path: Path) -> None:
    repo = SqlTradeRepository(_session_factory(tmp_path / "test.db"))
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

    positions = repo.list_open_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 10
    assert positions[0].avg_entry_price == 150.0


def test_second_buy_averages_position_entry_price(tmp_path: Path) -> None:
    repo = SqlTradeRepository(_session_factory(tmp_path / "test.db"))
    first = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    repo.save_fill(
        Fill(order_id=first.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=100.0, commission=0.0, timestamp=datetime.now(UTC)),
        first,
    )
    second = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    repo.save_fill(
        Fill(order_id=second.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=120.0, commission=0.0, timestamp=datetime.now(UTC)),
        second,
    )

    positions = repo.list_open_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 20
    assert positions[0].avg_entry_price == 110.0


def test_sell_reduces_and_removes_position(tmp_path: Path) -> None:
    repo = SqlTradeRepository(_session_factory(tmp_path / "test.db"))
    buy_order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    repo.save_fill(
        Fill(order_id=buy_order.id, symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0, commission=0.0, timestamp=datetime.now(UTC)),
        buy_order,
    )
    sell_order = Order(symbol="AAPL", side=OrderSide.SELL, quantity=10)
    repo.save_fill(
        Fill(order_id=sell_order.id, symbol="AAPL", side=OrderSide.SELL, quantity=10, price=160.0, commission=0.0, timestamp=datetime.now(UTC)),
        sell_order,
    )

    assert repo.list_open_positions() == []
    assert len(repo.list_trades()) == 2
    assert len(repo.list_trades(symbol="AAPL")) == 2
    assert repo.list_trades(symbol="MSFT") == []


def test_save_account_snapshot_does_not_raise(tmp_path: Path) -> None:
    repo = SqlTradeRepository(_session_factory(tmp_path / "test.db"))
    repo.save_account_snapshot(Account(timestamp=datetime.now(UTC), cash=9_000.0, positions_value=1_000.0))

    assert (tmp_path / "test.db").exists()

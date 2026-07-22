"""SQLAlchemy-backed persistence, adapting `app.models.domain` <-> ORM rows.

`SqlTradeRepository` satisfies `app.execution.repository.TradeRepository`
structurally (matching method signatures, no shared base class) so that
`ExecutionEngine` can persist through it without this module — or
SQLAlchemy — being a dependency of the execution layer.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.database.orm_models import AccountSnapshotRecord, PositionRecord, TradeRecord
from app.models.domain import Account, Fill, Order, Position
from app.models.enums import OrderSide

_EPSILON = 1e-9


class SqlTradeRepository:
    """Persists fills, keeps a live positions table, and records equity snapshots."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save_fill(self, fill: Fill, order: Order) -> None:
        with self._session_factory() as session:
            session.add(
                TradeRecord(
                    id=fill.id,
                    order_id=fill.order_id,
                    symbol=fill.symbol,
                    side=fill.side.value,
                    quantity=fill.quantity,
                    price=fill.price,
                    commission=fill.commission,
                    strategy_name=order.strategy_name,
                    timestamp=fill.timestamp,
                )
            )
            self._upsert_position(session, fill)
            session.commit()

    def _upsert_position(self, session: Session, fill: Fill) -> None:
        record = session.get(PositionRecord, fill.symbol)
        if fill.side == OrderSide.BUY:
            if record is None:
                session.add(
                    PositionRecord(
                        symbol=fill.symbol,
                        quantity=fill.quantity,
                        avg_entry_price=fill.price,
                        opened_at=fill.timestamp,
                        updated_at=fill.timestamp,
                    )
                )
            else:
                total_quantity = record.quantity + fill.quantity
                record.avg_entry_price = (
                    record.quantity * record.avg_entry_price + fill.quantity * fill.price
                ) / total_quantity
                record.quantity = total_quantity
                record.updated_at = fill.timestamp
        else:
            if record is not None:
                record.quantity -= fill.quantity
                record.updated_at = fill.timestamp
                if record.quantity <= _EPSILON:
                    session.delete(record)

    def save_account_snapshot(self, account: Account) -> None:
        with self._session_factory() as session:
            session.add(
                AccountSnapshotRecord(
                    timestamp=account.timestamp,
                    cash=account.cash,
                    positions_value=account.positions_value,
                    equity=account.equity,
                )
            )
            session.commit()

    def list_trades(self, symbol: str | None = None) -> list[Fill]:
        with self._session_factory() as session:
            query = session.query(TradeRecord)
            if symbol is not None:
                query = query.filter_by(symbol=symbol)
            return [self._to_fill(record) for record in query.order_by(TradeRecord.timestamp).all()]

    def list_open_positions(self) -> list[Position]:
        with self._session_factory() as session:
            return [
                Position(
                    symbol=record.symbol,
                    quantity=record.quantity,
                    avg_entry_price=record.avg_entry_price,
                    opened_at=record.opened_at,
                )
                for record in session.query(PositionRecord).all()
            ]

    @staticmethod
    def _to_fill(record: TradeRecord) -> Fill:
        return Fill(
            order_id=record.order_id,
            symbol=record.symbol,
            side=OrderSide(record.side),
            quantity=record.quantity,
            price=record.price,
            commission=record.commission,
            timestamp=record.timestamp,
            id=record.id,
        )

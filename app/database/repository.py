"""SQLAlchemy-backed persistence, adapting `app.models.domain` <-> ORM rows.

`SqlTradeRepository` satisfies `app.execution.repository.TradeRepository`
structurally (matching method signatures, no shared base class) so that
`ExecutionEngine` can persist through it without this module — or
SQLAlchemy — being a dependency of the execution layer.

Positions and account snapshots are scoped by `strategy_name`: each
strategy trades its own independent simulated account (see
`app.scheduler.context`), so two strategies can each hold a position in
the same symbol, or have entirely different equity curves, at once.
Trades were already tagged with `strategy_name` (via `Order.strategy_name`)
since Phase 2, so `save_fill`/`list_trades` didn't need to change shape.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
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
            self._upsert_position(session, fill, order.strategy_name)
            session.commit()

    def _upsert_position(self, session: Session, fill: Fill, strategy_name: str) -> None:
        record = session.get(PositionRecord, (strategy_name, fill.symbol))
        if fill.side == OrderSide.BUY:
            if record is None:
                session.add(
                    PositionRecord(
                        strategy_name=strategy_name,
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

    def save_account_snapshot(self, account: Account, strategy_name: str) -> None:
        with self._session_factory() as session:
            session.add(
                AccountSnapshotRecord(
                    strategy_name=strategy_name,
                    timestamp=account.timestamp,
                    cash=account.cash,
                    positions_value=account.positions_value,
                    equity=account.equity,
                )
            )
            session.commit()

    def list_trades(
        self, symbol: str | None = None, since: datetime | None = None, strategy_name: str | None = None
    ) -> list[Fill]:
        with self._session_factory() as session:
            query = session.query(TradeRecord)
            if symbol is not None:
                query = query.filter_by(symbol=symbol)
            if since is not None:
                query = query.filter(TradeRecord.timestamp >= since)
            if strategy_name is not None:
                query = query.filter_by(strategy_name=strategy_name)
            return [self._to_fill(record) for record in query.order_by(TradeRecord.timestamp).all()]

    def list_open_positions(self, strategy_name: str) -> list[Position]:
        with self._session_factory() as session:
            return [
                Position(
                    symbol=record.symbol,
                    quantity=record.quantity,
                    avg_entry_price=record.avg_entry_price,
                    opened_at=record.opened_at,
                )
                for record in session.query(PositionRecord).filter_by(strategy_name=strategy_name).all()
            ]

    def latest_cash_balance(self, strategy_name: str) -> float | None:
        """Cash from the most recent account snapshot for `strategy_name`, or `None` if none exists yet.

        Used on startup to resume a strategy's paper trading account
        across process restarts instead of silently resetting to
        `INITIAL_CAPITAL` every time the scheduler or dashboard starts.
        """
        with self._session_factory() as session:
            record = (
                session.query(AccountSnapshotRecord)
                .filter_by(strategy_name=strategy_name)
                .order_by(AccountSnapshotRecord.timestamp.desc())
                .first()
            )
            return None if record is None else record.cash

    def equity_curve(self, strategy_name: str, since: datetime | None = None) -> pd.Series:
        """Persisted equity snapshots for `strategy_name` as a `pandas.Series` indexed by timestamp."""
        with self._session_factory() as session:
            query = session.query(AccountSnapshotRecord).filter_by(strategy_name=strategy_name)
            if since is not None:
                query = query.filter(AccountSnapshotRecord.timestamp >= since)
            records = query.order_by(AccountSnapshotRecord.timestamp).all()

        series = pd.Series(
            [record.equity for record in records],
            index=pd.DatetimeIndex([record.timestamp for record in records]),
            dtype=float,
        )
        series.index.name = "timestamp"
        return series

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

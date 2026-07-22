"""SQLAlchemy ORM models — the persistence-layer mirror of `app.models.domain`.

Kept deliberately separate from the domain dataclasses: business logic in
`portfolio`/`risk`/`execution` never imports SQLAlchemy, and these tables
can evolve (indexes, columns, migrations) without touching the domain
model that the rest of the app is written against. `app.database
.repository` is the only place that converts between the two.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.engine import Base


class TradeRecord(Base):
    """One row per executed fill — the permanent, append-only trade log."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(String, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    strategy_name: Mapped[str] = mapped_column(String, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


class PositionRecord(Base):
    """Current open positions, kept in sync (upserted/deleted) on every fill."""

    __tablename__ = "positions"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    quantity: Mapped[float] = mapped_column(Float)
    avg_entry_price: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class AccountSnapshotRecord(Base):
    """A point-in-time (cash, positions_value, equity) snapshot for the equity curve."""

    __tablename__ = "account_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    cash: Mapped[float] = mapped_column(Float)
    positions_value: Mapped[float] = mapped_column(Float)
    equity: Mapped[float] = mapped_column(Float)

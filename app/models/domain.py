"""Core domain dataclasses.

These types are the "nouns" of the system. They are plain, framework-free
dataclasses (no SQLAlchemy, no pandas dependency beyond typing) so that
strategies, the execution engine, and reporting can all share a single
vocabulary without coupling to how any of them persists or displays data.

Persistence-layer models (app/database/orm_models.py) are separate and are
converted to/from these dataclasses at the repository boundary. This keeps
business logic testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from app.models.enums import OrderSide, OrderStatus, OrderType, SignalType


@dataclass(frozen=True, slots=True)
class Bar:
    """A single OHLCV candle for a symbol."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True, slots=True)
class Signal:
    """A strategy's opinion on a symbol at a point in time.

    Strategies only ever produce these — they never touch the database,
    the broker, or the portfolio directly.
    """

    symbol: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    strategy_name: str
    reason: str = ""


@dataclass(slots=True)
class Order:
    """An instruction to trade, prior to being filled by a broker."""

    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    strategy_name: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(frozen=True, slots=True)
class Fill:
    """The result of a broker executing an order (a completed trade)."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    timestamp: datetime
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass(slots=True)
class Position:
    """A currently held position in a single symbol."""

    symbol: str
    quantity: float
    avg_entry_price: float
    opened_at: datetime

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_entry_price

    def unrealized_pl(self, current_price: float) -> float:
        return (current_price - self.avg_entry_price) * self.quantity


@dataclass(frozen=True, slots=True)
class Account:
    """A point-in-time snapshot of the paper trading account."""

    timestamp: datetime
    cash: float
    positions_value: float

    @property
    def equity(self) -> float:
        return self.cash + self.positions_value

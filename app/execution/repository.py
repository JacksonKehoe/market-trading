"""Persistence port for the execution layer.

Defined here — in `execution`, the consumer — rather than in `database`,
so `ExecutionEngine` depends only on this narrow structural interface and
never imports SQLAlchemy. `app.database.repository.SqlTradeRepository`
satisfies this `Protocol` by matching method signatures; no inheritance
or import back into `database` is required.
"""

from __future__ import annotations

from typing import Protocol

from app.models.domain import Account, Fill, Order


class TradeRepository(Protocol):
    def save_fill(self, fill: Fill, order: Order) -> None: ...

    def save_account_snapshot(self, account: Account, strategy_name: str) -> None: ...

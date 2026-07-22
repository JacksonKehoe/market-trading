"""Broker interface — the seam between the trading system and *any* venue.

This is the single most important abstraction for the "future expansion"
requirement. The execution engine, risk manager, and portfolio talk to a
`BrokerInterface`, never to a concrete broker. In this phase the only
implementation is `PaperBroker` (an in-memory simulator with no network
access and no credentials). Adding Alpaca, Interactive Brokers, or
Robinhood later means writing a new class that implements this same
interface — nothing in the rest of the codebase changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.domain import Account, Fill, Order, Position


class BrokerInterface(ABC):
    """Base class for anything capable of executing orders and reporting state."""

    @abstractmethod
    def submit_order(self, order: Order) -> Fill:
        """Execute `order` and return the resulting Fill.

        Implementations are responsible for updating their own internal
        cash/position bookkeeping. A broker that cannot fill an order
        (e.g. insufficient cash) should raise rather than return a partial
        or fabricated Fill.
        """
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def get_account(self) -> Account:
        raise NotImplementedError

    @abstractmethod
    def get_cash_balance(self) -> float:
        raise NotImplementedError

"""In-memory portfolio ledger.

`Portfolio` is the bookkeeping engine `PaperBroker` uses to simulate an
account: it applies fills and answers questions about current cash,
positions, and P/L. It has no knowledge of strategies, risk rules,
brokers, or persistence — those are separate layers that use it (or, for
risk/execution, read plain `Account`/`Position` data derived from it) —
which keeps this class trivially unit-testable and reusable if a future
live broker ever needs a local mirror of remote account state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from app.models.domain import Account, Fill, Position
from app.models.enums import OrderSide

_EPSILON = 1e-9


class InsufficientFundsError(Exception):
    """Raised when a BUY fill would spend more cash than the portfolio has."""


class InsufficientSharesError(Exception):
    """Raised when a SELL fill would sell more shares than the portfolio holds."""


@dataclass(slots=True)
class Portfolio:
    """Tracks cash, open positions, and cumulative realized P/L."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pl: float = 0.0

    def position_value(self, symbol: str, price: float) -> float:
        position = self.positions.get(symbol)
        return 0.0 if position is None else position.quantity * price

    def positions_value(self, prices: dict[str, float]) -> float:
        return sum(
            self.position_value(symbol, prices[symbol])
            for symbol in self.positions
            if symbol in prices
        )

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + self.positions_value(prices)

    def unrealized_pl(self, prices: dict[str, float]) -> float:
        return sum(
            position.unrealized_pl(prices[symbol])
            for symbol, position in self.positions.items()
            if symbol in prices
        )

    def to_account(self, prices: dict[str, float], timestamp: datetime) -> Account:
        return Account(timestamp=timestamp, cash=self.cash, positions_value=self.positions_value(prices))

    def apply_fill(self, fill: Fill) -> float:
        """Update cash/positions/realized P&L for a completed trade.

        Returns the P&L realized *by this specific fill* (always 0.0 for a
        BUY; the closed-out gain/loss for a SELL). Reporting uses this to
        reconstruct per-trade P&L for win rate / profit factor / etc.
        without duplicating this accounting logic elsewhere.

        Raises `InsufficientFundsError` / `InsufficientSharesError` rather
        than silently clamping — callers (PaperBroker) should never be
        asked to apply a fill the account can't actually afford, since
        that would fabricate money or shares that don't exist.
        """
        if fill.side == OrderSide.BUY:
            self._apply_buy(fill)
            return 0.0
        return self._apply_sell(fill)

    def _apply_buy(self, fill: Fill) -> None:
        cost = fill.quantity * fill.price + fill.commission
        if cost > self.cash + _EPSILON:
            raise InsufficientFundsError(
                f"Cannot buy {fill.quantity} {fill.symbol} @ {fill.price:.2f}: "
                f"cost {cost:.2f} exceeds cash balance {self.cash:.2f}"
            )
        self.cash -= cost
        existing = self.positions.get(fill.symbol)
        if existing is None:
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=fill.quantity,
                avg_entry_price=fill.price,
                opened_at=fill.timestamp,
            )
        else:
            total_quantity = existing.quantity + fill.quantity
            existing.avg_entry_price = (
                existing.quantity * existing.avg_entry_price + fill.quantity * fill.price
            ) / total_quantity
            existing.quantity = total_quantity

    def _apply_sell(self, fill: Fill) -> float:
        existing = self.positions.get(fill.symbol)
        if existing is None or existing.quantity < fill.quantity - _EPSILON:
            held = 0.0 if existing is None else existing.quantity
            raise InsufficientSharesError(
                f"Cannot sell {fill.quantity} {fill.symbol}: only {held} held"
            )
        proceeds = fill.quantity * fill.price - fill.commission
        self.cash += proceeds
        realized = (fill.price - existing.avg_entry_price) * fill.quantity - fill.commission
        self.realized_pl += realized
        existing.quantity -= fill.quantity
        if existing.quantity <= _EPSILON:
            del self.positions[fill.symbol]
        return realized

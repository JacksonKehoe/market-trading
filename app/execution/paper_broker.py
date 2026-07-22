"""The (only) `BrokerInterface` implementation in this version of the system.

`PaperBroker` fills every order immediately at the current market price
from a `MarketDataProvider`, using an in-memory `Portfolio` as its ledger.
It makes no network calls to any brokerage and requires no credentials —
there is no live-trading code path here at all.

A future live broker (Alpaca, IBKR, ...) implements the exact same
`BrokerInterface` and can be swapped in without changing `RiskManager`,
`ExecutionEngine`, or anything above them.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.data.base import MarketDataProvider
from app.execution.broker_base import BrokerInterface
from app.models.domain import Account, Fill, Order, Position
from app.models.enums import OrderStatus
from app.portfolio.portfolio import InsufficientFundsError, InsufficientSharesError, Portfolio
from app.utils.logging_config import get_logger

logger = get_logger("trades")


class PaperBroker(BrokerInterface):
    """Simulated broker: no network access, no credentials, no real money."""

    def __init__(
        self,
        initial_cash: float,
        data_provider: MarketDataProvider,
        commission_per_trade: float = 0.0,
    ) -> None:
        self.portfolio = Portfolio(cash=initial_cash)
        self._data_provider = data_provider
        self._commission_per_trade = commission_per_trade

    def submit_order(self, order: Order) -> Fill:
        price = self._data_provider.get_latest_price(order.symbol)
        fill = Fill(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            commission=self._commission_per_trade,
            timestamp=datetime.now(UTC),
        )
        try:
            self.portfolio.apply_fill(fill)
        except (InsufficientFundsError, InsufficientSharesError):
            order.status = OrderStatus.REJECTED
            logger.warning(
                "REJECTED %s %s %s @ %.2f", order.side.value, order.quantity, order.symbol, price
            )
            raise

        order.status = OrderStatus.FILLED
        logger.info(
            "FILLED %s %s %s @ %.2f (commission=%.2f, strategy=%s)",
            fill.side.value,
            fill.quantity,
            fill.symbol,
            fill.price,
            fill.commission,
            order.strategy_name or "manual",
        )
        return fill

    def get_positions(self) -> list[Position]:
        return list(self.portfolio.positions.values())

    def get_account(self) -> Account:
        prices = {
            symbol: self._data_provider.get_latest_price(symbol) for symbol in self.portfolio.positions
        }
        return self.portfolio.to_account(prices, datetime.now(UTC))

    def get_cash_balance(self) -> float:
        return self.portfolio.cash

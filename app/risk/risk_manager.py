"""Risk enforcement — the gate every Signal must pass before it becomes an Order.

`RiskManager` operates on plain domain objects (`Account`, `Position`,
`Signal`) rather than a concrete broker or portfolio class. That keeps it
fully broker-agnostic: `ExecutionEngine` supplies whatever `Account`/
`Position` data it got from `BrokerInterface.get_account()` /
`get_positions()`, so the exact same risk logic works unchanged whether
the account behind it is `PaperBroker` or a future live broker.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.domain import Account, Order, Position, Signal
from app.models.enums import OrderSide, SignalType
from app.risk.rules import RiskLimits

_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """The outcome of evaluating a signal (or an exit check) against RiskLimits."""

    approved: bool
    reason: str
    order: Order | None = None


class RiskManager:
    """Enforces `RiskLimits` between strategy signals and the broker."""

    def __init__(self, limits: RiskLimits) -> None:
        self.limits = limits

    def evaluate_signal(
        self,
        signal: Signal,
        current_price: float,
        account: Account,
        positions: list[Position],
        daily_start_equity: float | None = None,
    ) -> RiskDecision:
        """Decide whether `signal` may proceed, and size the resulting Order.

        `daily_start_equity` is the account's equity at the start of the
        trading day (see `ExecutionEngine.start_new_trading_day`); pass
        `None` to skip the daily-loss-limit check (e.g. in tests, or
        before the first day boundary has been recorded).
        """
        if signal.signal_type == SignalType.HOLD:
            return RiskDecision(False, "HOLD signal requires no action")

        if signal.signal_type == SignalType.SELL:
            return self._evaluate_sell(signal, positions)

        return self._evaluate_buy(signal, current_price, account, positions, daily_start_equity)

    def _evaluate_sell(self, signal: Signal, positions: list[Position]) -> RiskDecision:
        position = next((p for p in positions if p.symbol == signal.symbol), None)
        if position is None or position.quantity <= _EPSILON:
            return RiskDecision(False, f"No open position in {signal.symbol} to sell")

        order = Order(
            symbol=signal.symbol,
            side=OrderSide.SELL,
            quantity=position.quantity,
            strategy_name=signal.strategy_name,
        )
        return RiskDecision(True, f"Exit approved: sell {position.quantity} {signal.symbol}", order)

    def _evaluate_buy(
        self,
        signal: Signal,
        current_price: float,
        account: Account,
        positions: list[Position],
        daily_start_equity: float | None,
    ) -> RiskDecision:
        if any(p.symbol == signal.symbol for p in positions):
            return RiskDecision(False, f"Already holding a position in {signal.symbol}")

        if len(positions) >= self.limits.max_open_positions:
            return RiskDecision(False, f"Max open positions ({self.limits.max_open_positions}) reached")

        if self.limits.daily_loss_limit_pct is not None and daily_start_equity:
            daily_pl_pct = (account.equity - daily_start_equity) / daily_start_equity
            if daily_pl_pct <= -self.limits.daily_loss_limit_pct:
                return RiskDecision(
                    False, f"Daily loss limit of {self.limits.daily_loss_limit_pct:.1%} reached"
                )

        equity = account.equity
        if equity <= 0 or current_price <= 0:
            return RiskDecision(False, "No equity available or invalid price")

        max_position_value = equity * self.limits.max_position_size_pct
        available_allocation = equity * self.limits.max_portfolio_allocation_pct - account.positions_value
        order_value = min(max_position_value, available_allocation, account.cash)
        if order_value <= 0:
            return RiskDecision(False, "No capital available under current allocation limits")

        quantity = math.floor(order_value / current_price)
        if quantity < 1:
            return RiskDecision(
                False, f"Insufficient capital for 1 share of {signal.symbol} within risk limits"
            )

        order = Order(
            symbol=signal.symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            strategy_name=signal.strategy_name,
        )
        return RiskDecision(True, f"Approved: buy {quantity} shares of {signal.symbol}", order)

    def check_exits(self, positions: list[Position], current_prices: dict[str, float]) -> list[Order]:
        """Generate forced-exit SELL orders for positions past stop-loss/take-profit.

        This is independent of strategy signals — it's the account-level
        safety net the execution engine runs every cycle, matching the
        spec's "Stop loss / Take profit" risk controls.
        """
        orders: list[Order] = []
        for position in positions:
            price = current_prices.get(position.symbol)
            if price is None or position.avg_entry_price <= 0:
                continue

            change_pct = (price - position.avg_entry_price) / position.avg_entry_price
            if self.limits.stop_loss_pct is not None and change_pct <= -self.limits.stop_loss_pct:
                orders.append(
                    Order(
                        symbol=position.symbol,
                        side=OrderSide.SELL,
                        quantity=position.quantity,
                        strategy_name="risk:stop_loss",
                    )
                )
            elif self.limits.take_profit_pct is not None and change_pct >= self.limits.take_profit_pct:
                orders.append(
                    Order(
                        symbol=position.symbol,
                        side=OrderSide.SELL,
                        quantity=position.quantity,
                        strategy_name="risk:take_profit",
                    )
                )
        return orders

"""Orchestrates: Signal -> risk check -> broker fill -> persistence.

`ExecutionEngine` only knows about the `BrokerInterface` and `RiskManager`
contracts (plus `MarketDataProvider` for pricing and the `TradeRepository`
port for optional persistence) — never a concrete broker. It works
unchanged against `PaperBroker` today and any future live broker later.
Strategies and scheduling are supplied by the caller; this class does not
loop over a watchlist itself, so it can be reused as-is by a backtester,
a scheduler job, or a one-off manual script.
"""

from __future__ import annotations

from app.data.base import MarketDataProvider
from app.execution.broker_base import BrokerInterface
from app.execution.repository import TradeRepository
from app.models.domain import Fill, Order, Signal
from app.models.enums import SignalType
from app.risk.risk_manager import RiskManager
from app.utils.logging_config import get_logger

app_logger = get_logger("app")
errors_logger = get_logger("errors")


class ExecutionEngine:
    def __init__(
        self,
        broker: BrokerInterface,
        data_provider: MarketDataProvider,
        risk_manager: RiskManager,
        repository: TradeRepository | None = None,
        strategy_name: str = "",
    ) -> None:
        self.broker = broker
        self.data_provider = data_provider
        self.risk_manager = risk_manager
        self.repository = repository
        self.strategy_name = strategy_name
        self._daily_start_equity: float | None = None

    def start_new_trading_day(self) -> None:
        """Record today's starting equity so the daily loss limit can be enforced."""
        self._daily_start_equity = self.broker.get_account().equity

    def process_signal(self, signal: Signal) -> Fill | None:
        """Risk-check `signal` and submit the resulting order, if approved.

        Returns `None` for HOLD signals and for signals the risk manager
        rejects — callers should treat `None` as "no trade happened",
        not as an error.
        """
        if signal.signal_type == SignalType.HOLD:
            return None

        current_price = self.data_provider.get_latest_price(signal.symbol)
        account = self.broker.get_account()
        positions = self.broker.get_positions()

        decision = self.risk_manager.evaluate_signal(
            signal, current_price, account, positions, self._daily_start_equity
        )
        if not decision.approved or decision.order is None:
            app_logger.info(
                "Signal rejected: %s %s - %s", signal.symbol, signal.signal_type.value, decision.reason
            )
            return None

        return self._submit(decision.order)

    def run_exit_checks(self) -> list[Fill]:
        """Force-close any position that has hit its stop-loss or take-profit."""
        positions = self.broker.get_positions()
        prices = {p.symbol: self.data_provider.get_latest_price(p.symbol) for p in positions}
        orders = self.risk_manager.check_exits(positions, prices)
        fills = [self._submit(order) for order in orders]
        return [fill for fill in fills if fill is not None]

    def _submit(self, order: Order) -> Fill | None:
        try:
            fill = self.broker.submit_order(order)
        except Exception:
            errors_logger.exception(
                "Order submission failed: %s %s %s", order.side.value, order.quantity, order.symbol
            )
            return None

        if self.repository is not None:
            self.repository.save_fill(fill, order)
            self.repository.save_account_snapshot(self.broker.get_account(), self.strategy_name)

        return fill

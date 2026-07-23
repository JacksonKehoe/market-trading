"""Turns broker positions into display-ready rows.

Shared by the live email reports (`app.email.report_data`) and the
dashboard (`app.dashboard`) so the two don't duplicate (or drift on) how
a position's current price and unrealized P&L are computed for display.
"""

from __future__ import annotations

from app.data.base import MarketDataProvider
from app.execution.broker_base import BrokerInterface


def position_rows(broker: BrokerInterface, provider: MarketDataProvider) -> list[dict]:
    rows = []
    for position in broker.get_positions():
        try:
            price = provider.get_latest_price(position.symbol)
        except Exception:
            price = position.avg_entry_price
        rows.append(
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_entry_price": position.avg_entry_price,
                "current_price": price,
                "market_value": position.quantity * price,
                "unrealized_pl": position.unrealized_pl(price),
                "unrealized_pl_pct": (price / position.avg_entry_price - 1) * 100
                if position.avg_entry_price
                else 0.0,
            }
        )
    return rows

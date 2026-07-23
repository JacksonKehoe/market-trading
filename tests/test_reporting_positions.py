from datetime import UTC, datetime

import pytest

from app.models.domain import Position
from app.reporting.positions import position_rows
from tests.conftest import FakeMarketDataProvider


class _FakeBroker:
    def __init__(self, positions: list[Position]) -> None:
        self._positions = positions

    def get_positions(self) -> list[Position]:
        return self._positions


def _position(symbol: str, quantity: float, avg_entry_price: float) -> Position:
    return Position(symbol=symbol, quantity=quantity, avg_entry_price=avg_entry_price, opened_at=datetime.now(UTC))


def test_position_rows_computes_market_value_and_unrealized_pl() -> None:
    broker = _FakeBroker([_position("AAPL", 10, 100.0)])
    provider = FakeMarketDataProvider({"AAPL": 120.0})

    rows = position_rows(broker, provider)

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "AAPL"
    assert row["current_price"] == 120.0
    assert row["market_value"] == 1200.0
    assert row["unrealized_pl"] == 200.0
    assert row["unrealized_pl_pct"] == pytest.approx(20.0)


def test_position_rows_falls_back_to_entry_price_when_lookup_fails() -> None:
    broker = _FakeBroker([_position("AAPL", 10, 100.0)])
    provider = FakeMarketDataProvider({})  # no price configured -> KeyError inside

    rows = position_rows(broker, provider)

    assert rows[0]["current_price"] == 100.0
    assert rows[0]["unrealized_pl"] == 0.0


def test_position_rows_empty_for_no_positions() -> None:
    broker = _FakeBroker([])
    provider = FakeMarketDataProvider({})

    assert position_rows(broker, provider) == []

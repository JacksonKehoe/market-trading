from datetime import UTC, datetime
from pathlib import Path

import app.dashboard.app as dashboard_app
from app.config.settings import Settings
from app.models.domain import Account, Fill, Order
from app.models.enums import OrderSide
from tests.conftest import FakeHistoricalMarketDataProvider, build_test_repository, make_price_frame


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    defaults: dict[str, object] = dict(
        database_path=tmp_path / "test.db",
        logs_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
        cache_dir=tmp_path / "cache",
        watchlist=["AAPL"],
        initial_capital=10_000.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def test_index_returns_200_on_empty_database(tmp_path: Path, monkeypatch) -> None:
    history = {"AAPL": make_price_frame([100.0 + i for i in range(30)])}
    monkeypatch.setattr(
        dashboard_app, "build_market_data_provider", lambda settings: FakeHistoricalMarketDataProvider(history)
    )
    app = dashboard_app.create_app(_settings(tmp_path))
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"No open positions" in response.data
    assert b"No trades yet" in response.data


def test_index_shows_positions_trades_and_signals(tmp_path: Path, monkeypatch) -> None:
    history = {"AAPL": make_price_frame([100.0 + i for i in range(30)])}
    monkeypatch.setattr(
        dashboard_app, "build_market_data_provider", lambda settings: FakeHistoricalMarketDataProvider(history)
    )
    settings = _settings(tmp_path)

    repository = build_test_repository(settings.database_path)
    repository.save_account_snapshot(Account(timestamp=datetime.now(UTC), cash=8_500.0, positions_value=1_500.0))
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10)
    fill = Fill(
        order_id=order.id,
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        price=150.0,
        commission=0.0,
        timestamp=datetime.now(UTC),
    )
    repository.save_fill(fill, order)

    app = dashboard_app.create_app(settings)
    client = app.test_client()

    response = client.get("/")
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "AAPL" in body
    assert "150.00" in body  # avg entry price rendered somewhere
    assert "Strategy Signals" in body


def test_index_survives_a_watchlist_symbol_with_no_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_app, "build_market_data_provider", lambda settings: FakeHistoricalMarketDataProvider({})
    )
    app = dashboard_app.create_app(_settings(tmp_path, watchlist=["MISSING"]))
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200

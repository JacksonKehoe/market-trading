from datetime import UTC, datetime
from pathlib import Path

import app.scheduler.context as context_module
from app.config.settings import Settings
from app.models.domain import Account, Fill, Order
from app.models.enums import OrderSide
from app.strategies.factory import build_strategy
from tests.conftest import FakeMarketDataProvider, build_test_repository


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


def test_build_trading_context_starts_fresh_with_no_prior_state(tmp_path: Path, monkeypatch) -> None:
    fake_provider = FakeMarketDataProvider({"AAPL": 150.0})
    monkeypatch.setattr(context_module, "build_market_data_provider", lambda settings: fake_provider)
    settings = _settings(tmp_path)

    context = context_module.build_trading_context(settings, strategy_name="sma")

    assert context.broker.get_cash_balance() == 10_000.0
    assert context.broker.get_positions() == []
    assert context.watchlist == ["AAPL"]
    assert context.strategy.name.startswith("sma_crossover")


def test_build_trading_context_rehydrates_cash_and_positions_from_repository(
    tmp_path: Path, monkeypatch
) -> None:
    fake_provider = FakeMarketDataProvider({"AAPL": 150.0})
    monkeypatch.setattr(context_module, "build_market_data_provider", lambda settings: fake_provider)
    settings = _settings(tmp_path)
    strategy_name = build_strategy("sma").name

    # Simulate a prior process having persisted an account snapshot + an open position.
    repository = build_test_repository(settings.database_path)
    repository.save_account_snapshot(
        Account(timestamp=datetime.now(UTC), cash=7_500.0, positions_value=1_500.0), strategy_name
    )
    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name=strategy_name)
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

    context = context_module.build_trading_context(settings, strategy_name="sma")

    assert context.broker.get_cash_balance() == 7_500.0
    positions = context.broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == 10


def test_build_trading_context_strategy_follows_strategy_name(tmp_path: Path, monkeypatch) -> None:
    fake_provider = FakeMarketDataProvider({"AAPL": 150.0})
    monkeypatch.setattr(context_module, "build_market_data_provider", lambda settings: fake_provider)
    settings = _settings(tmp_path)

    context = context_module.build_trading_context(settings, strategy_name="rsi")

    assert context.strategy.name.startswith("rsi_")


def test_build_trading_contexts_builds_one_per_configured_strategy(tmp_path: Path, monkeypatch) -> None:
    fake_provider = FakeMarketDataProvider({"AAPL": 150.0})
    monkeypatch.setattr(context_module, "build_market_data_provider", lambda settings: fake_provider)
    settings = _settings(tmp_path, strategies=["sma", "rsi"])

    contexts = context_module.build_trading_contexts(settings)

    assert len(contexts) == 2
    names = {c.strategy.name for c in contexts}
    assert any(n.startswith("sma_crossover") for n in names)
    assert any(n.startswith("rsi_") for n in names)


def test_build_trading_contexts_gives_each_strategy_independent_capital(tmp_path: Path, monkeypatch) -> None:
    fake_provider = FakeMarketDataProvider({"AAPL": 150.0})
    monkeypatch.setattr(context_module, "build_market_data_provider", lambda settings: fake_provider)
    settings = _settings(tmp_path, strategies=["sma", "rsi"], initial_capital=5_000.0)

    contexts = context_module.build_trading_contexts(settings)

    for context in contexts:
        assert context.broker.get_cash_balance() == 5_000.0

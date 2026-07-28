from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.email.report_data import StrategyState, build_evening_report_context, build_morning_report_context
from app.execution.paper_broker import PaperBroker
from app.models.domain import Account, Order, Signal
from app.models.enums import OrderSide, SentimentLabel, SignalType
from app.risk.rules import RiskLimits
from tests.conftest import FakeHistoricalMarketDataProvider, FakeMarketDataProvider, build_test_repository, make_price_frame


def _limits(**overrides: object) -> RiskLimits:
    defaults: dict[str, object] = dict(
        max_position_size_pct=0.5,
        max_portfolio_allocation_pct=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.10,
        daily_loss_limit_pct=0.03,
        max_open_positions=5,
    )
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def _signal(symbol: str, signal_type: SignalType, strategy_name: str = "test", price: float = 150.0) -> Signal:
    return Signal(symbol, signal_type, datetime.now(UTC), price, strategy_name, "test reason")


def test_morning_report_context_summarizes_signals_and_comparison() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0, "MSFT": 300.0})
    broker = PaperBroker(10_000.0, provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=5))
    signals = [_signal("AAPL", SignalType.HOLD, "sma"), _signal("MSFT", SignalType.BUY, "sma")]
    strategies = [StrategyState("sma", broker, signals)]

    context = build_morning_report_context(Settings(), provider, ["AAPL", "MSFT"], strategies)

    assert context["comparison"][0]["equity"] == broker.get_account().equity
    assert context["comparison"][0]["buy_signals"] == 1
    assert len(context["buy_signals"]) == 1
    assert context["buy_signals"][0].symbol == "MSFT"
    assert context["hold_count"] == 1
    assert len(context["positions"]) == 1
    assert context["positions"][0]["symbol"] == "AAPL"
    assert context["positions"][0]["strategy"] == "sma"
    assert context["daily_trading_plan"]  # non-empty


def test_morning_report_context_default_plan_when_no_signals() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker = PaperBroker(10_000.0, provider)
    strategies = [StrategyState("sma", broker, [])]

    context = build_morning_report_context(Settings(), provider, ["AAPL"], strategies)

    assert context["buy_signals"] == []
    assert context["sell_signals"] == []
    assert "No new signals" in context["daily_trading_plan"][0]


def test_morning_report_context_combines_multiple_strategies() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker_a = PaperBroker(10_000.0, provider)
    broker_b = PaperBroker(10_000.0, provider)
    strategies = [
        StrategyState("sma", broker_a, [_signal("AAPL", SignalType.BUY, "sma")]),
        StrategyState("rsi", broker_b, [_signal("AAPL", SignalType.HOLD, "rsi")]),
    ]

    context = build_morning_report_context(Settings(), provider, ["AAPL"], strategies)

    assert len(context["comparison"]) == 2
    assert {c["strategy"] for c in context["comparison"]} == {"sma", "rsi"}
    assert len(context["buy_signals"]) == 1


def test_morning_report_context_includes_sentiment_scores_when_service_provided() -> None:
    from app.models.domain import SentimentScore

    class _FixedSentimentService:
        def get_sentiment(self, symbol: str):
            return SentimentScore(
                symbol=symbol, label=SentimentLabel.BULLISH, score=0.42, headline_count=5, timestamp=datetime.now(UTC)
            )

    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker = PaperBroker(10_000.0, provider)
    strategies = [StrategyState("sma", broker, [])]

    context = build_morning_report_context(
        Settings(), provider, ["AAPL"], strategies, sentiment_service=_FixedSentimentService()
    )

    assert len(context["sentiment_scores"]) == 1
    assert context["sentiment_scores"][0]["symbol"] == "AAPL"
    assert context["sentiment_scores"][0]["label"] == SentimentLabel.BULLISH
    assert context["sentiment_scores"][0]["score"] == 0.42


def test_morning_report_context_sentiment_scores_empty_without_service() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})
    broker = PaperBroker(10_000.0, provider)
    strategies = [StrategyState("sma", broker, [])]

    context = build_morning_report_context(Settings(), provider, ["AAPL"], strategies)

    assert context["sentiment_scores"] == []


def test_morning_report_context_computes_benchmark_day_change() -> None:
    # _market_movers looks back a few days from the real "now", so the fixture
    # dates must be recent (not the make_price_frame default of Jan 2026).
    recent_start = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    spy_history = make_price_frame([400.0, 404.0], start=recent_start)  # +1% day
    provider = FakeHistoricalMarketDataProvider({"AAPL": spy_history, "SPY": spy_history})
    broker = PaperBroker(10_000.0, provider)
    strategies = [StrategyState("sma", broker, [])]

    context = build_morning_report_context(Settings(benchmark_symbol="SPY"), provider, ["AAPL"], strategies)

    assert context["benchmark_symbol"] == "SPY"
    assert context["benchmark_day_change"] is not None
    assert context["benchmark_day_change"]["change_pct"] == pytest.approx(1.0)


def test_morning_report_context_benchmark_day_change_none_when_unavailable() -> None:
    provider = FakeMarketDataProvider({"AAPL": 150.0})  # no history at all -> no benchmark data
    broker = PaperBroker(10_000.0, provider)
    strategies = [StrategyState("sma", broker, [])]

    context = build_morning_report_context(Settings(benchmark_symbol="SPY"), provider, ["AAPL"], strategies)

    assert context["benchmark_day_change"] is None


def test_evening_report_context_computes_day_pl_and_trades_today(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 160.0})
    broker = PaperBroker(10_000.0, provider)
    repository = build_test_repository(tmp_path / "test.db")
    repository.save_account_snapshot(broker.get_account(), "sma")  # yesterday's baseline @ $10,000

    order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="sma")
    fill = broker.submit_order(order)
    repository.save_fill(fill, order)

    strategies = [StrategyState("sma", broker)]
    context = build_evening_report_context(
        Settings(), provider, repository, ["AAPL"], _limits(), strategies
    )

    assert context["comparison"][0]["equity"] == broker.get_account().equity
    assert len(context["trades_today"]) == 1
    assert context["trades_today"][0]["fill"].symbol == "AAPL"
    assert context["trades_today"][0]["pnl"] is None  # BUY, not a closed trade
    assert context["trades_today"][0]["strategy"] == "sma"
    assert context["comparison"][0]["day_pl"] != 0  # equity moved from the baseline snapshot
    assert context["risk_summary"][0]["open_positions"] == 1
    assert context["risk_summary"][0]["max_open_positions"] == 5


def test_evening_report_context_best_worst_strategy(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 100.0})
    broker_a = PaperBroker(10_000.0, provider)
    broker_b = PaperBroker(10_000.0, provider)
    broker_a.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="sma"))
    broker_b.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, strategy_name="rsi"))

    repository = build_test_repository(tmp_path / "test.db")
    repository.save_account_snapshot(broker_a.get_account(), "sma")
    repository.save_account_snapshot(broker_b.get_account(), "rsi")

    # Strategy sma's holding gains, rsi's is flat -- sma should come out ahead today.
    provider.set_price("AAPL", 120.0)

    strategies = [StrategyState("sma", broker_a), StrategyState("rsi", broker_b)]
    context = build_evening_report_context(
        Settings(), provider, repository, ["AAPL"], _limits(), strategies
    )

    assert context["best_strategy"]["strategy"] == "sma"


def test_evening_report_context_adds_benchmark_row_and_chart_series(tmp_path: Path) -> None:
    spy_history = make_price_frame([400.0 + i for i in range(30)], start="2026-01-01")
    provider = FakeHistoricalMarketDataProvider({"SPY": spy_history, "AAPL": spy_history})
    broker = PaperBroker(10_000.0, provider)
    repository = build_test_repository(tmp_path / "test.db")
    # Snapshot timestamp inside the SPY fixture's Jan-2026 range so the ranges overlap.
    repository.save_account_snapshot(
        Account(timestamp=datetime(2026, 1, 15, tzinfo=UTC), cash=10_000.0, positions_value=0.0), "sma"
    )
    strategies = [StrategyState("sma", broker)]

    context = build_evening_report_context(
        Settings(benchmark_symbol="SPY"), provider, repository, ["AAPL"], _limits(), strategies
    )

    benchmark_rows = [c for c in context["comparison"] if c.get("is_benchmark")]
    assert len(benchmark_rows) == 1
    assert benchmark_rows[0]["strategy"] == "SPY (Benchmark)"
    assert benchmark_rows[0]["cash"] is None
    assert "SPY (Benchmark)" in context["equity_curves"]


def test_evening_report_context_benchmark_is_excluded_from_best_worst(tmp_path: Path) -> None:
    spy_history = make_price_frame([100.0 + i * 10 for i in range(30)], start="2026-01-01")  # huge benchmark gain
    provider = FakeHistoricalMarketDataProvider({"SPY": spy_history, "AAPL": spy_history})
    broker = PaperBroker(10_000.0, provider)
    repository = build_test_repository(tmp_path / "test.db")
    repository.save_account_snapshot(
        Account(timestamp=datetime(2026, 1, 15, tzinfo=UTC), cash=10_000.0, positions_value=0.0), "sma"
    )
    strategies = [StrategyState("sma", broker)]

    context = build_evening_report_context(
        Settings(benchmark_symbol="SPY"), provider, repository, ["AAPL"], _limits(), strategies
    )

    # Even though the benchmark's normalized gain is huge, it must never be "best_strategy".
    assert context["best_strategy"]["strategy"] == "sma"


def test_evening_report_context_omits_benchmark_when_unavailable(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 160.0})  # no SPY history at all
    broker = PaperBroker(10_000.0, provider)
    repository = build_test_repository(tmp_path / "test.db")
    strategies = [StrategyState("sma", broker)]

    context = build_evening_report_context(
        Settings(benchmark_symbol="SPY"), provider, repository, ["AAPL"], _limits(), strategies
    )

    assert not any(c.get("is_benchmark") for c in context["comparison"])
    assert "SPY (Benchmark)" not in context["equity_curves"]


def test_evening_report_context_recommends_when_at_max_positions(tmp_path: Path) -> None:
    provider = FakeMarketDataProvider({"AAPL": 100.0})
    broker = PaperBroker(10_000.0, provider)
    broker.submit_order(Order(symbol="AAPL", side=OrderSide.BUY, quantity=1, strategy_name="sma"))
    repository = build_test_repository(tmp_path / "test.db")
    strategies = [StrategyState("sma", broker)]

    context = build_evening_report_context(
        Settings(), provider, repository, ["AAPL"], _limits(max_open_positions=1), strategies
    )

    assert any("max open positions" in line for line in context["recommendations"])

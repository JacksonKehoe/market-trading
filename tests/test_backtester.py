from datetime import UTC, datetime

import pandas as pd
import pytest

from app.models.domain import Signal
from app.models.enums import SignalType
from app.reporting.backtest import Backtester, ReplayMarketDataProvider
from app.risk.rules import RiskLimits
from app.strategies.base import Strategy
from app.strategies.moving_average_crossover import MovingAverageCrossoverStrategy
from tests.conftest import FakeHistoricalMarketDataProvider, make_price_frame


def _limits(**overrides: object) -> RiskLimits:
    defaults: dict[str, object] = dict(
        max_position_size_pct=1.0,
        max_portfolio_allocation_pct=1.0,
        stop_loss_pct=0.05,
        take_profit_pct=0.20,
        daily_loss_limit_pct=None,
        max_open_positions=5,
    )
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


class _AlwaysHoldStrategy(Strategy):
    @property
    def name(self) -> str:
        return "test_always_hold"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        return self._hold(symbol, data.index[-1], float(data["close"].iloc[-1]), "never trades")


class _BuyOnceStrategy(Strategy):
    """BUYs exactly once, on a specific date; HOLDs every other day."""

    def __init__(self, buy_on_date: str) -> None:
        self._buy_on_date = pd.Timestamp(buy_on_date)

    @property
    def name(self) -> str:
        return "test_buy_once"

    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Signal:
        timestamp = data.index[-1]
        price = float(data["close"].iloc[-1])
        if timestamp == self._buy_on_date:
            return Signal(symbol, SignalType.BUY, timestamp, price, self.name, "scheduled test buy")
        return self._hold(symbol, timestamp, price, "not the scheduled buy date")


# --- ReplayMarketDataProvider ------------------------------------------------------


def test_replay_provider_only_serves_data_up_to_current_date() -> None:
    data = make_price_frame([100.0, 101.0, 102.0, 103.0])
    provider = ReplayMarketDataProvider({"AAPL": data})

    provider.advance_to(data.index[1])
    assert provider.get_latest_price("AAPL") == 101.0

    provider.advance_to(data.index[3])
    assert provider.get_latest_price("AAPL") == 103.0


def test_replay_provider_raises_before_any_data_is_available() -> None:
    data = make_price_frame([100.0], start="2026-02-01")
    provider = ReplayMarketDataProvider({"AAPL": data})
    provider.advance_to(pd.Timestamp("2026-01-01"))

    with pytest.raises(ValueError):
        provider.get_latest_price("AAPL")


# --- Backtester ----------------------------------------------------------------------


def test_backtester_with_hold_only_strategy_produces_flat_equity_curve() -> None:
    data = make_price_frame([100.0 + i for i in range(30)])
    provider = FakeHistoricalMarketDataProvider({"AAPL": data})
    backtester = Backtester(provider, initial_capital=10_000.0, risk_limits=_limits())

    result = backtester.run(
        _AlwaysHoldStrategy(), ["AAPL"], data.index[0], data.index[-1]
    )

    assert result.trades == []
    assert (result.equity_curve == 10_000.0).all()


def test_backtester_executes_trades_and_moves_equity() -> None:
    decline = list(range(50, 20, -1))
    rise = list(range(20, 60))
    data = make_price_frame([float(p) for p in decline + rise])
    provider = FakeHistoricalMarketDataProvider({"AAPL": data})
    backtester = Backtester(provider, initial_capital=10_000.0, risk_limits=_limits())

    result = backtester.run(
        MovingAverageCrossoverStrategy(fast_window=3, slow_window=10),
        ["AAPL"],
        data.index[0],
        data.index[-1],
    )

    assert len(result.trades) > 0
    assert len(result.equity_curve) == len(data)
    assert result.equity_curve.iloc[0] == 10_000.0
    # The strategy caught the uptrend, so the account should have grown.
    assert result.equity_curve.iloc[-1] > 10_000.0


def test_backtester_enforces_stop_loss_even_without_a_sell_signal() -> None:
    prices = [100.0] * 20 + [80.0] * 10  # flat, then a cliff after the buy
    data = make_price_frame(prices)
    buy_date = data.index[19]
    provider = FakeHistoricalMarketDataProvider({"AAPL": data})
    backtester = Backtester(provider, initial_capital=10_000.0, risk_limits=_limits(stop_loss_pct=0.05))

    result = backtester.run(_BuyOnceStrategy(buy_date), ["AAPL"], data.index[0], data.index[-1])

    assert result.final_positions == []
    sides = [fill.side.value for fill in result.trades]
    assert sides == ["BUY", "SELL"]


def test_backtester_benchmark_curve_is_buy_and_hold_from_same_capital() -> None:
    data = make_price_frame([100.0 + i for i in range(30)])
    benchmark_data = make_price_frame([200.0 + 2 * i for i in range(30)])
    provider = FakeHistoricalMarketDataProvider({"AAPL": data, "SPY": benchmark_data})
    backtester = Backtester(provider, initial_capital=10_000.0, risk_limits=_limits())

    result = backtester.run(
        _AlwaysHoldStrategy(), ["AAPL"], data.index[0], data.index[-1], benchmark_symbol="SPY"
    )

    assert result.benchmark_curve is not None
    assert result.benchmark_curve.iloc[0] == pytest.approx(10_000.0)
    expected_final = 10_000.0 * (benchmark_data["close"].iloc[-1] / benchmark_data["close"].iloc[0])
    assert result.benchmark_curve.iloc[-1] == pytest.approx(expected_final)


def test_backtester_raises_when_no_historical_data_available() -> None:
    provider = FakeHistoricalMarketDataProvider({})
    backtester = Backtester(provider, initial_capital=10_000.0, risk_limits=_limits())

    with pytest.raises(ValueError):
        backtester.run(
            _AlwaysHoldStrategy(), ["AAPL"], datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
        )

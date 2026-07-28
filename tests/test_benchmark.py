from datetime import UTC, datetime

from app.reporting.benchmark import compute_benchmark_curve
from tests.conftest import FakeHistoricalMarketDataProvider, make_price_frame


def test_compute_benchmark_curve_normalizes_to_initial_capital() -> None:
    data = make_price_frame([100.0, 110.0, 120.0])
    provider = FakeHistoricalMarketDataProvider({"SPY": data})

    curve = compute_benchmark_curve(provider, "SPY", data.index[0], data.index[-1], 10_000.0)

    assert curve is not None
    assert curve.iloc[0] == 10_000.0
    assert curve.iloc[-1] == 12_000.0  # 120/100 * 10,000


def test_compute_benchmark_curve_returns_none_for_no_data() -> None:
    provider = FakeHistoricalMarketDataProvider({})

    curve = compute_benchmark_curve(
        provider, "SPY", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC), 10_000.0
    )

    assert curve is None


def test_compute_benchmark_curve_returns_none_for_non_positive_first_close() -> None:
    data = make_price_frame([0.0, 10.0, 20.0])
    provider = FakeHistoricalMarketDataProvider({"SPY": data})

    curve = compute_benchmark_curve(provider, "SPY", data.index[0], data.index[-1], 10_000.0)

    assert curve is None

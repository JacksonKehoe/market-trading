import pandas as pd
import pytest

from app.reporting.charts import build_drawdown_chart, build_equity_curve_chart


def _curve(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values), freq="D"))


def test_equity_curve_chart_has_one_trace_without_benchmark() -> None:
    fig = build_equity_curve_chart(_curve([100.0, 105.0, 110.0]))
    assert len(fig.data) == 1
    assert fig.data[0].name == "Portfolio"


def test_equity_curve_chart_has_two_traces_with_benchmark() -> None:
    fig = build_equity_curve_chart(_curve([100.0, 105.0, 110.0]), _curve([100.0, 102.0, 104.0]))
    assert len(fig.data) == 2
    assert {trace.name for trace in fig.data} == {"Portfolio", "Benchmark"}


def test_equity_curve_chart_ignores_empty_benchmark() -> None:
    fig = build_equity_curve_chart(_curve([100.0, 105.0]), pd.Series(dtype=float))
    assert len(fig.data) == 1


def test_equity_curve_chart_raises_on_empty_series() -> None:
    with pytest.raises(ValueError):
        build_equity_curve_chart(pd.Series(dtype=float))


def test_drawdown_chart_reflects_known_drawdown() -> None:
    fig = build_drawdown_chart(_curve([100.0, 120.0, 90.0, 110.0]))
    y = list(fig.data[0].y)
    assert y[1] == pytest.approx(0.0)
    assert y[2] == pytest.approx(-25.0)  # 90/120 - 1 = -25%


def test_drawdown_chart_raises_on_empty_series() -> None:
    with pytest.raises(ValueError):
        build_drawdown_chart(pd.Series(dtype=float))

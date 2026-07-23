"""Plotly chart builders for backtest (and, later, email/dashboard) reports.

Each function takes plain data and returns a `plotly.graph_objects.Figure`
— building HTML, saving files, or deciding how to embed the chart is left
to the caller (`report_generator`), so this module stays a pure
"data -> figure" layer with no filesystem or templating concerns.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_equity_curve_chart(
    equity_curve: pd.Series,
    benchmark_curve: pd.Series | None = None,
    title: str = "Portfolio Equity Curve",
) -> go.Figure:
    if equity_curve.empty:
        raise ValueError("Cannot chart an empty equity curve")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=equity_curve.index, y=equity_curve.values, mode="lines", name="Portfolio"))
    if benchmark_curve is not None and not benchmark_curve.empty:
        fig.add_trace(
            go.Scatter(
                x=benchmark_curve.index,
                y=benchmark_curve.values,
                mode="lines",
                name="Benchmark",
                line={"dash": "dot"},
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        template="plotly_white",
        hovermode="x unified",
    )
    return fig


def build_multi_equity_curve_chart(
    curves: dict[str, pd.Series],
    title: str = "Strategy Comparison — Equity Curves",
) -> go.Figure:
    """One line per named series (e.g. strategy name) on a shared equity chart.

    Unlike `build_equity_curve_chart` (one portfolio + an optional single
    benchmark line), this supports an arbitrary number of series — the
    comparison view for running several strategies side by side.
    """
    non_empty = {name: series for name, series in curves.items() if series is not None and not series.empty}
    if not non_empty:
        raise ValueError("Cannot chart when no series has any equity history")

    fig = go.Figure()
    for name, series in non_empty.items():
        fig.add_trace(go.Scatter(x=series.index, y=series.values, mode="lines", name=name))

    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Equity ($)",
        template="plotly_white",
        hovermode="x unified",
    )
    return fig


def build_drawdown_chart(equity_curve: pd.Series, title: str = "Drawdown") -> go.Figure:
    if equity_curve.empty:
        raise ValueError("Cannot chart an empty equity curve")

    running_max = equity_curve.cummax()
    drawdown_pct = (equity_curve / running_max - 1) * 100

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=drawdown_pct.index,
            y=drawdown_pct.values,
            mode="lines",
            fill="tozeroy",
            name="Drawdown",
            line={"color": "crimson"},
        )
    )
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Drawdown (%)", template="plotly_white")
    return fig

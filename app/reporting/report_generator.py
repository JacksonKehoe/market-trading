"""Renders a self-contained HTML backtest report and saves it to disk.

Charts are built with `app.reporting.charts` and embedded as inline HTML
(Plotly's JS is pulled from a CDN once, on the first chart, and reused by
the second) so the whole report is a single file with no other assets to
ship alongside it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.reporting.backtest import BacktestResult
from app.reporting.charts import build_drawdown_chart, build_equity_curve_chart
from app.reporting.metrics import PerformanceMetrics

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(enabled_extensions=("j2", "html")),
)


def generate_backtest_report(
    result: BacktestResult,
    metrics: PerformanceMetrics,
    strategy_name: str,
    symbols: list[str],
    start: datetime,
    end: datetime,
    output_dir: Path,
) -> Path:
    """Render the report and write it to `output_dir`. Returns the file path."""
    equity_fig = build_equity_curve_chart(result.equity_curve, result.benchmark_curve)
    drawdown_fig = build_drawdown_chart(result.equity_curve)

    template = _env.get_template("backtest_report.html.j2")
    html = template.render(
        strategy_name=strategy_name,
        symbols=symbols,
        start=start,
        end=end,
        generated_at=datetime.now(UTC),
        metrics=metrics,
        profit_factor_display="∞" if metrics.profit_factor == float("inf") else f"{metrics.profit_factor:.2f}",
        trades=sorted(result.trades, key=lambda fill: fill.timestamp),
        equity_chart_html=equity_fig.to_html(full_html=False, include_plotlyjs="cdn"),
        drawdown_chart_html=drawdown_fig.to_html(full_html=False, include_plotlyjs=False),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"backtest_{strategy_name}_{datetime.now(UTC):%Y%m%dT%H%M%S}.html"
    path = output_dir / filename
    path.write_text(html, encoding="utf-8")
    return path

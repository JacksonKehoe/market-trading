"""Renders the morning/evening report contexts into HTML via Jinja2.

Chart figures are built here rather than in `report_data.py`, so that
module stays purely about *data*; and here rather than in
`app.scheduler.jobs`, so report rendering is one self-contained,
independently testable step.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.reporting.charts import build_equity_curve_chart

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(enabled_extensions=("j2", "html")),
)


def render_morning_report(context: dict) -> str:
    return _env.get_template("morning_report.html.j2").render(**context)


def render_evening_report(context: dict) -> str:
    equity_curve = context.get("equity_curve")
    equity_chart_html = None
    if equity_curve is not None and not equity_curve.empty:
        equity_chart_html = build_equity_curve_chart(equity_curve).to_html(
            full_html=False, include_plotlyjs="cdn"
        )

    render_context = {k: v for k, v in context.items() if k != "equity_curve"}
    return _env.get_template("evening_report.html.j2").render(
        **render_context, equity_chart_html=equity_chart_html
    )

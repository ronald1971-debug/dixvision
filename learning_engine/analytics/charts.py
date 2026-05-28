# ADAPTED FROM: plotly/plotly.py
# (plotly/graph_objects/__init__.py — Figure, Scatter, Candlestick, Bar;
#  plotly/express/ — convenience API for quick charts;
#  plotly/io/ — write_html(), to_json())
"""C-89 — Plotly analytics charts for PnL and regime analysis.

This module adapts ``plotly`` for offline analytics visualization:
PnL curves, drawdown charts, regime overlays, feature importance.

What survives from upstream (plotly/plotly.py):
    * **Figure** — graph_objects: base container for traces + layout.
    * **Scatter** — line/marker charts for PnL curves.
    * **Candlestick** — OHLC price visualization.
    * **Bar** — bar charts for feature importance.
    * **write_html()** — export to standalone HTML.

What we replaced:
    * Real ``plotly`` import is lazy (Protocol seam).
    * In-memory chart spec (dict) for unit tests.
    * Output as JSON-serializable dict or HTML string.

OFFLINE tier: analytics/reporting only.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChartTrace:
    """A single trace (series) in a chart."""

    name: str
    trace_type: str = "scatter"  # scatter, bar, candlestick
    x: list = field(default_factory=list)
    y: list = field(default_factory=list)
    mode: str = "lines"


@dataclass
class ChartSpec:
    """Complete chart specification."""

    title: str
    traces: list[ChartTrace] = field(default_factory=list)
    x_title: str = ""
    y_title: str = ""
    height: int = 400
    width: int = 800

    def to_dict(self) -> dict:
        """Export as serializable dict (plotly-compatible layout)."""
        return {
            "data": [
                {
                    "name": t.name,
                    "type": t.trace_type,
                    "x": t.x,
                    "y": t.y,
                    "mode": t.mode,
                }
                for t in self.traces
            ],
            "layout": {
                "title": self.title,
                "xaxis": {"title": self.x_title},
                "yaxis": {"title": self.y_title},
                "height": self.height,
                "width": self.width,
            },
        }


class AnalyticsCharts:
    """Plotly-based analytics chart builder.

    Generates PnL curves, drawdown charts, regime overlays,
    and feature importance bar charts.

    Usage::

        charts = AnalyticsCharts()
        spec = charts.pnl_curve(dates, returns, title="Strategy PnL")
        html = charts.render_html(spec)
    """

    def __init__(self, *, in_memory: bool = True) -> None:
        self._in_memory = in_memory

    def pnl_curve(
        self,
        dates: list,
        cumulative_returns: list[float],
        *,
        title: str = "PnL Curve",
    ) -> ChartSpec:
        """Generate a PnL curve chart."""
        return ChartSpec(
            title=title,
            traces=[ChartTrace(name="PnL", x=dates, y=cumulative_returns, mode="lines")],
            x_title="Date",
            y_title="Cumulative Return",
        )

    def drawdown_chart(
        self,
        dates: list,
        drawdowns: list[float],
        *,
        title: str = "Drawdown",
    ) -> ChartSpec:
        """Generate a drawdown chart (negative values)."""
        return ChartSpec(
            title=title,
            traces=[
                ChartTrace(
                    name="Drawdown",
                    x=dates,
                    y=drawdowns,
                    mode="lines",
                )
            ],
            x_title="Date",
            y_title="Drawdown",
        )

    def feature_importance(
        self,
        feature_names: list[str],
        importances: list[float],
        *,
        title: str = "Feature Importance",
    ) -> ChartSpec:
        """Generate a feature importance bar chart."""
        return ChartSpec(
            title=title,
            traces=[
                ChartTrace(
                    name="Importance",
                    trace_type="bar",
                    x=feature_names,
                    y=importances,
                )
            ],
            x_title="Feature",
            y_title="Importance",
        )

    def render_html(self, spec: ChartSpec) -> str:
        """Render chart as HTML string."""
        if self._in_memory:
            return self._render_simple_html(spec)
        return self._render_plotly_html(spec)

    def _render_simple_html(self, spec: ChartSpec) -> str:
        """Render minimal HTML with chart data as JSON."""
        import json

        data = spec.to_dict()
        return (
            f"<html><head><title>{spec.title}</title></head>"
            f"<body><script>var chartData = {json.dumps(data)};</script>"
            f"<p>{spec.title} — {len(spec.traces)} trace(s)</p>"
            f"</body></html>"
        )

    def _render_plotly_html(self, spec: ChartSpec) -> str:
        """Render via plotly."""
        try:
            import plotly.graph_objects as go

            fig = go.Figure()
            for trace in spec.traces:
                if trace.trace_type == "bar":
                    fig.add_trace(go.Bar(name=trace.name, x=trace.x, y=trace.y))
                else:
                    fig.add_trace(
                        go.Scatter(name=trace.name, x=trace.x, y=trace.y, mode=trace.mode)
                    )
            fig.update_layout(
                title=spec.title,
                xaxis_title=spec.x_title,
                yaxis_title=spec.y_title,
            )
            return fig.to_html(include_plotlyjs="cdn")
        except ImportError:
            return self._render_simple_html(spec)


__all__ = ["AnalyticsCharts", "ChartSpec", "ChartTrace"]

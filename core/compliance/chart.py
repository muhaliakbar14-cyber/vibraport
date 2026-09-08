"""Plotly chart shared by Data Overview and the PDF report."""

import numpy as np
import plotly.graph_objects as go

from .evaluator import evaluate_point
from .standards import (
    category_options,
    chart_title,
    curve_points,
    format_limit,
    get_standard,
    limit_at_frequency,
    reference_values,
)


CURVE_STYLES = (
    dict(color="#1565C0", dash="dot"),
    dict(color="#2E7D32", dash="dashdot"),
    dict(color="#F57F17", dash="dash"),
    dict(color="#6A1B9A", dash="longdash"),
    dict(color="#B71C1C", dash="solid"),
)

PPV_MARKERS = {
    "Transversal": dict(symbol="cross", color="#E53935", size=12, line_width=2),
    "Vertical": dict(symbol="x", color="#00897B", size=12, line_width=2),
    "Longitudinal": dict(symbol="circle-open", color="#1E88E5", size=12, line_width=2),
    "Transversal B2": dict(symbol="cross", color="#EF9A9A", size=10, line_width=2),
    "Vertical B2": dict(symbol="x", color="#26A69A", size=10, line_width=2),
    "Longitudinal B2": dict(symbol="circle-open", color="#90CAF9", size=10, line_width=2),
}


def _band_labels(standard_id: str, assessment: str) -> list[tuple[float, str]]:
    if standard_id == "sni_7571_2023":
        return [(np.sqrt(5), "0-5 Hz"), (10, "5-20 Hz"), (np.sqrt(2000), "20-100 Hz")]
    if standard_id == "din_4150_3_2016" and assessment == "short_term":
        return [(5.5, "1-10 Hz"), (30, "10-50 Hz"), (75, "50-100 Hz")]
    if standard_id == "bs_7385_2_1993":
        return [(2, "<4 Hz: displacement check"), (np.sqrt(60), "4-15 Hz"),
                (np.sqrt(600), "15-40 Hz"), (np.sqrt(4000), "40-100 Hz")]
    return [(10, "All frequencies")]


def _uses_linear_frequency_axis(standard_id: str) -> bool:
    return standard_id == "din_4150_3_2016"


def _frequency_axis_position(value: float, standard_id: str) -> float:
    if _uses_linear_frequency_axis(standard_id):
        return value
    return np.log10(value)


def _uses_linear_ppv_axis(standard_id: str) -> bool:
    return standard_id == "din_4150_3_2016"


def _ppv_axis_position(value: float, standard_id: str) -> float:
    if _uses_linear_ppv_axis(standard_id):
        return value
    return np.log10(value)


def build_compliance_chart(
    ppv_points: list[dict],
    standard_id: str,
    assessment: str,
    selected_category: int,
    compact: bool = False,
) -> go.Figure:
    spec = get_standard(standard_id)
    fig = go.Figure()

    label_frequency = 35.0 if standard_id == "bs_7385_2_1993" else spec.x_range[1] * 0.95
    for index, category in enumerate(category_options(standard_id)):
        x_values, y_values = curve_points(standard_id, assessment, category.id)
        style = CURVE_STYLES[index]
        fig.add_trace(go.Scatter(
            x=x_values, y=y_values, mode="lines", name=category.label,
            line=dict(color=style["color"], dash=style["dash"], width=1.1 if compact else 1.35),
            showlegend=False,
            hovertemplate=(f"<b>{category.label}</b><br>Frequency: %{{x:.1f}} Hz"
                           "<br>Limit: %{y:.2f} mm/s<extra></extra>"),
        ))
        label_limit = limit_at_frequency(standard_id, assessment, category.id, label_frequency)
        if label_limit is not None:
            fig.add_annotation(
                x=_frequency_axis_position(label_frequency, standard_id),
                y=_ppv_axis_position(label_limit, standard_id), xref="x", yref="y",
                text=category.short_label, showarrow=False,
                font=dict(size=7 if compact else 10, color=style["color"]),
                xanchor="right", yanchor="bottom",
            )

    linear_ppv_axis = _uses_linear_ppv_axis(standard_id)
    y_floor = 0.0 if linear_ppv_axis else 1.0
    for point in ppv_points:
        channel = str(point["channel"])
        ppv = float(point["ppv"])
        freq = float(point["freq"])
        block = int(point.get("block", 1))
        marker = PPV_MARKERS.get(channel, dict(symbol="diamond", color="#20242A", size=10, line_width=2))
        result = evaluate_point(point, standard_id, assessment, selected_category)
        display_ppv = max(ppv, y_floor)
        below_floor = ppv < y_floor
        short_label = {
            "Vertical": "V", "Longitudinal": "L", "Transversal": "T",
            "Vertical B2": "V2", "Longitudinal B2": "L2", "Transversal B2": "T2",
        }.get(channel, channel[:2])
        text_position = {
            "Vertical": "top left", "Longitudinal": "bottom right", "Transversal": "top right",
            "Vertical B2": "bottom left", "Longitudinal B2": "top right", "Transversal B2": "bottom right",
        }.get(channel, "top right")
        label = f"Blk{block} {channel}" if block == 2 else channel
        limit_line = f"Limit: {format_limit(result.limit)} mm/s<br>" if result.limit is not None else ""
        floor_note = f" (shown at {y_floor:.0f})" if below_floor else ""
        fig.add_trace(go.Scatter(
            x=[freq], y=[display_ppv], mode="markers+text", name=label,
            text=[short_label], textposition=text_position,
            textfont=dict(size=7 if compact else 10, color=marker["color"]),
            marker=dict(
                symbol=marker["symbol"], color=marker["color"],
                size=7 if compact else marker["size"],
                line=dict(color=marker["color"], width=1.2 if compact else marker["line_width"]),
                opacity=0.55 if below_floor else 1.0,
            ),
            showlegend=False,
            hovertemplate=(f"<b>{label}</b><br>PPV: {ppv:.3f} mm/s{floor_note}<br>"
                           f"Frequency: {freq:.1f} Hz<br>{limit_line}Result: {result.status}<extra></extra>"),
        ))

    ticks = reference_values(standard_id, assessment)
    if linear_ppv_axis:
        ticks = tuple(sorted({0.0, 60.0, *(value for value in ticks if 1.0 < value < 60.0)}))
    linear_frequency_axis = _uses_linear_frequency_axis(standard_id)
    plot_y_min = 0.0 if linear_ppv_axis else 1.0
    plot_y_max = 60.0 if linear_ppv_axis else 100.0
    fig.update_layout(
        title=dict(
            text=chart_title(standard_id, assessment), x=0.5, xanchor="center",
            font=dict(family="Inter SemiBold, Inter, Arial, sans-serif",
                      size=11 if compact else 19, color="#20242A"),
        ),
        xaxis=dict(
            type="linear" if linear_frequency_axis else "log", title="Frequency (Hz)",
            range=(list(spec.x_range) if linear_frequency_axis else
                   [np.log10(spec.x_range[0]), np.log10(spec.x_range[1])]),
            tickvals=list(spec.x_ticks), ticktext=[format_limit(v) for v in spec.x_ticks],
            showgrid=False, minor=dict(showgrid=False),
            tickfont=dict(size=7 if compact else 10), title_font=dict(size=8 if compact else 12),
            linecolor="#4D535A", mirror=True,
        ),
        yaxis=dict(
            type="linear" if linear_ppv_axis else "log", title="PPV (mm/s)",
            range=[plot_y_min, plot_y_max] if linear_ppv_axis else [0, 2],
            tickvals=list(ticks), ticktext=[format_limit(v) for v in ticks],
            showgrid=False, minor=dict(showgrid=False),
            tickfont=dict(size=7 if compact else 10), title_font=dict(size=8 if compact else 12),
            linecolor="#4D535A", mirror=True,
        ),
        height=500, hovermode="closest", showlegend=False,
        margin=dict(t=30 if compact else 58, b=34 if compact else 58,
                    l=38 if compact else 62, r=10 if compact else 28),
        font=dict(family="Inter, Arial, sans-serif", size=7 if compact else 10, color="#30343B"),
        plot_bgcolor="white", paper_bgcolor="white",
    )

    active_breakpoints = () if (
        standard_id == "din_4150_3_2016" and assessment == "long_term"
    ) else spec.breakpoints
    for x_value in active_breakpoints:
        fig.add_shape(type="line", x0=x_value, x1=x_value, y0=plot_y_min, y1=plot_y_max,
                      xref="x", yref="y", layer="below",
                      line=dict(color="rgba(80, 90, 100, 0.28)", width=0.7))
    for y_value in ticks:
        fig.add_shape(type="line", x0=spec.x_range[0], x1=spec.x_range[1], y0=y_value, y1=y_value,
                      xref="x", yref="y", layer="below",
                      line=dict(color="rgba(80, 90, 100, 0.20)", width=0.55))
    if standard_id == "bs_7385_2_1993":
        fig.add_shape(type="rect", x0=1, x1=4, y0=1, y1=100, xref="x", yref="y", layer="below",
                      fillcolor="rgba(120, 128, 138, 0.07)", line=dict(width=0))
    band_label_ppv = 58.0 if linear_ppv_axis else 93.0
    for x_mid, label in _band_labels(standard_id, assessment):
        fig.add_annotation(
            x=_frequency_axis_position(x_mid, standard_id),
            y=_ppv_axis_position(band_label_ppv, standard_id),
            xref="x", yref="y", text=label, showarrow=False,
            font=dict(size=5.5 if compact else 8.5, color="#68717B"),
            xanchor="center", yanchor="top",
        )
    return fig

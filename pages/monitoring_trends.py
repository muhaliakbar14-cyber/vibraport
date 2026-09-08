"""Time-aggregated trend analysis for SIS bargraph recordings."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from core.monitoring import (
    aggregate_monitoring_trends,
    get_bargraph_channels,
    infer_monitoring_interval,
    peak_preserving_downsample,
    summarize_channel,
)


CHANNEL_COLORS = {
    "Vertical": "#00897B",
    "Longitudinal": "#E53935",
    "Transversal": "#5C6BC0",
    "X": "#00897B",
    "Y": "#E53935",
    "Z": "#5C6BC0",
    "Pressure": "#FFB300",
    "KBf": "#8E24AA",
}

STATISTICS = {
    "Maximum": "maximum",
    "P95": "p95",
    "P99": "p99",
    "Mean": "mean",
    "Median": "median",
}

MAX_DISPLAY_POINTS = 1_800
MAX_TABLE_ROWS = 2_000


def render(df, time_axis, metadata, sampling_rate):
    st.title("📈 Monitoring Trends")
    st.caption(
        "Review how stored bargraph measurements change across selectable time windows"
    )
    st.divider()

    if metadata.get("is_waveform", True):
        st.info(
            "This page is for **Bargraph** recordings only. "
            "The current file is a Waveform recording."
        )
        return

    channels = get_bargraph_channels(df, metadata)
    if not channels:
        st.warning("No bargraph amplitude data found in file.")
        return

    times = np.asarray(time_axis, dtype=float)
    interval_seconds = metadata.get("Monitoring interval seconds")
    if not interval_seconds:
        interval_seconds = (
            infer_monitoring_interval(times, fallback=sampling_rate) or 1.0
        )
    duration_seconds = _recording_duration(times, interval_seconds)

    channel_labels = [channel["label"] for channel in channels]
    selected_labels = st.multiselect(
        "Channels",
        options=channel_labels,
        default=channel_labels,
        key="monitoring_trend_channels",
    )
    if not selected_labels:
        st.warning("Select at least one channel to build a trend.")
        return
    selected_channels = [
        channel for channel in channels if channel["label"] in selected_labels
    ]

    shared_axis_compatible = _shared_axis_compatible(selected_channels)
    control_1, control_2, control_3 = st.columns(3)
    window_options = _aggregation_window_options(
        duration_seconds, interval_seconds
    )
    default_window = "1 minute" if "1 minute" in window_options else next(
        iter(window_options)
    )
    window_label = control_1.selectbox(
        "Aggregation window",
        options=list(window_options),
        index=list(window_options).index(default_window),
        help=(
            "Each output bucket is calculated from the original stored intervals. "
            "Native interval keeps one point per recorded bar."
        ),
        key="monitoring_trend_window",
    )
    statistic_label = control_2.selectbox(
        "Trend statistic",
        options=list(STATISTICS),
        help="Select which bucket statistic is drawn in every channel panel.",
        key="monitoring_trend_statistic",
    )
    layout_options = ["Stacked panels"]
    if shared_axis_compatible:
        layout_options.append("Combined overlay")
    chart_layout = control_3.selectbox(
        "Chart layout",
        options=layout_options,
        help=(
            "Combined overlay is available only when all selected channels "
            "have the same physical quantity and unit."
        ),
        key="monitoring_trend_chart_layout",
    )

    synchronize_y_axis = False
    if chart_layout == "Stacked panels":
        synchronize_y_axis = st.checkbox(
            "Synchronize Y-axis between channels",
            value=False,
            disabled=not shared_axis_compatible,
            help=(
                "Use one common Y-axis range so channel amplitudes can be "
                "compared directly. Available only for matching quantities and units."
            ),
            key="monitoring_trend_sync_y_axis",
        )
        if not shared_axis_compatible:
            synchronize_y_axis = False
    else:
        st.caption(
            "Click a channel name in the chart legend to hide or show that trace."
        )
    if not shared_axis_compatible:
        st.caption(
            "The selected channels use different quantities or units, so a shared "
            "Y-axis and combined overlay would be misleading."
        )

    if window_label == "Custom":
        bucket_seconds = st.number_input(
            "Custom aggregation window (seconds)",
            min_value=float(interval_seconds),
            value=float(max(interval_seconds, min(60.0, duration_seconds))),
            step=float(max(interval_seconds, 1.0)),
            key="monitoring_trend_custom_seconds",
        )
    else:
        bucket_seconds = window_options[window_label]

    st.info(
        "Maximum, mean, median, P95, and P99 describe the stored interval "
        f"**{_stored_statistics_label(selected_channels)}** values inside each "
        "time bucket. They are not reconstructed waveform RMS or VDV."
    )

    records = aggregate_monitoring_trends(
        df,
        times,
        selected_channels,
        float(bucket_seconds),
        interval_seconds=float(interval_seconds),
    )
    if not records:
        st.warning("No finite time values are available for trend analysis.")
        return

    trend_key = STATISTICS[statistic_label]
    rendered_points, figure = _build_trend_figure(
        records,
        selected_channels,
        trend_key,
        statistic_label,
        chart_layout=chart_layout,
        synchronize_y_axis=synchronize_y_axis,
    )

    source_intervals = sum(
        len(df[channel["amplitude_column"]]) for channel in selected_channels
    )
    valid_source = sum(record["valid_count"] for record in records)
    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Source interval values", f"{source_intervals:,}")
    metric_2.metric("Valid values", f"{valid_source:,}")
    metric_3.metric("Trend buckets", f"{len(records):,}")
    metric_4.metric("Bucket width", _format_window(bucket_seconds))

    st.markdown("## Aggregated Trend")
    st.plotly_chart(
        figure,
        width="stretch",
        config={"scrollZoom": False, "displaylogo": False},
    )
    st.caption(
        f"Calculated {len(records):,} channel buckets from {source_intervals:,} "
        f"original interval values; {rendered_points:,} points are sent to the "
        "browser. Plot reduction is display-only."
    )

    st.markdown("## Full-Recording Channel Summary")
    st.caption(
        "These statistics use every original stored interval and do not change "
        "with the aggregation-window selector."
    )
    st.dataframe(
        pd.DataFrame(_full_recording_summary(df, selected_channels)),
        width="stretch",
        hide_index=True,
    )

    st.markdown("## Aggregated Data")
    trend_table = _trend_dataframe(records)
    hidden_rows = max(0, len(trend_table) - MAX_TABLE_ROWS)
    st.dataframe(
        trend_table.head(MAX_TABLE_ROWS),
        width="stretch",
        hide_index=True,
    )
    if hidden_rows:
        st.caption(
            f"Showing {MAX_TABLE_ROWS:,} of {len(trend_table):,} aggregated "
            "rows. The CSV export contains every bucket."
        )

    filename = metadata.get("_filename", "bargraph").rsplit(".", 1)[0]
    st.download_button(
        "⬇️ Export aggregated trends as CSV",
        data=trend_table.to_csv(index=False).encode("utf-8"),
        file_name=f"{filename}-trends-{_filename_window(bucket_seconds)}.csv",
        mime="text/csv",
    )


def _aggregation_window_options(duration_seconds, interval_seconds):
    native_label = f"Native interval ({interval_seconds:g} s)"
    options = {native_label: float(interval_seconds)}
    for label, seconds in (
        ("1 minute", 60.0),
        ("5 minutes", 300.0),
        ("15 minutes", 900.0),
        ("1 hour", 3600.0),
    ):
        if seconds >= interval_seconds and duration_seconds >= seconds:
            options[label] = seconds
    options["Custom"] = None
    return options


def _build_trend_figure(
    records,
    channels,
    trend_key,
    statistic_label,
    *,
    chart_layout="Stacked panels",
    synchronize_y_axis=False,
):
    if chart_layout == "Combined overlay":
        return _build_overlay_trend_figure(
            records, channels, trend_key, statistic_label
        )

    vertical_spacing = min(0.10, 0.36 / max(1, len(channels)))
    subplot_titles = [
        f"{channel['label']} · {statistic_label} · {channel['unit']}"
        for channel in channels
    ]
    figure = make_subplots(
        rows=len(channels),
        cols=1,
        shared_xaxes=True,
        shared_yaxes=synchronize_y_axis,
        vertical_spacing=vertical_spacing,
        subplot_titles=subplot_titles,
    )
    rendered_points = 0

    for row, channel in enumerate(channels, start=1):
        channel_records = [
            record for record in records if record["channel"] == channel["label"]
        ]
        x_values = np.asarray(
            [record["midpoint_seconds"] / 60 for record in channel_records],
            dtype=float,
        )
        y_values = np.asarray(
            [
                record[trend_key]
                if record[trend_key] is not None
                else np.nan
                for record in channel_records
            ],
            dtype=float,
        )
        display_x, display_y = peak_preserving_downsample(
            x_values,
            y_values,
            max_points=MAX_DISPLAY_POINTS,
        )
        rendered_points += display_x.size
        color = CHANNEL_COLORS.get(channel["axis"], "#607D8B")
        figure.add_trace(
            go.Scattergl(
                x=display_x,
                y=display_y,
                mode="lines+markers" if display_x.size <= 240 else "lines",
                line=dict(color=color, width=1.5),
                marker=dict(color=color, size=5),
                connectgaps=False,
                showlegend=False,
                hovertemplate=(
                    "Time=%{x:.2f} min<br>"
                    f"{statistic_label}=%{{y:.4f}} {channel['unit']}"
                    "<extra></extra>"
                ),
            ),
            row=row,
            col=1,
        )

    figure.update_xaxes(title_text="Elapsed time (min)", row=len(channels), col=1)
    figure.update_yaxes(rangemode="tozero", tickfont=dict(size=10))
    if synchronize_y_axis:
        for row in range(2, len(channels) + 1):
            figure.update_yaxes(matches="y", row=row, col=1)
    figure.update_layout(
        height=max(430, 235 * len(channels)),
        hovermode="x",
        showlegend=False,
        margin=dict(t=45, b=60, l=60, r=35),
        plot_bgcolor="white",
        uirevision=f"trends-{trend_key}",
    )
    for annotation in figure.layout.annotations:
        annotation.update(font=dict(size=12))
    return rendered_points, figure


def _build_overlay_trend_figure(records, channels, trend_key, statistic_label):
    figure = go.Figure()
    rendered_points = 0
    unit = channels[0]["unit"] if channels else ""

    for channel in channels:
        channel_records = [
            record for record in records if record["channel"] == channel["label"]
        ]
        x_values = np.asarray(
            [record["midpoint_seconds"] / 60 for record in channel_records],
            dtype=float,
        )
        y_values = np.asarray(
            [
                record[trend_key]
                if record[trend_key] is not None
                else np.nan
                for record in channel_records
            ],
            dtype=float,
        )
        display_x, display_y = peak_preserving_downsample(
            x_values,
            y_values,
            max_points=MAX_DISPLAY_POINTS,
        )
        rendered_points += display_x.size
        color = CHANNEL_COLORS.get(channel["axis"], "#607D8B")
        figure.add_trace(
            go.Scattergl(
                x=display_x,
                y=display_y,
                mode="lines+markers" if display_x.size <= 240 else "lines",
                name=channel["label"],
                line=dict(color=color, width=1.5),
                marker=dict(color=color, size=5),
                connectgaps=False,
                hovertemplate=(
                    f"<b>{channel['label']}</b><br>Time=%{{x:.2f}} min<br>"
                    f"{statistic_label}=%{{y:.4f}} {unit}<extra></extra>"
                ),
            )
        )

    figure.update_layout(
        height=500,
        xaxis_title="Elapsed time (min)",
        yaxis_title=f"{statistic_label} ({unit})" if unit else statistic_label,
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        margin=dict(t=70, b=60, l=60, r=35),
        plot_bgcolor="white",
        uirevision=f"trends-overlay-{trend_key}",
    )
    figure.update_yaxes(rangemode="tozero", tickfont=dict(size=10))
    return rendered_points, figure


def _full_recording_summary(df, channels):
    rows = []
    for channel in channels:
        frequency_column = channel.get("frequency_column")
        frequencies = (
            df[frequency_column].to_numpy(dtype=float)
            if frequency_column and frequency_column in df.columns
            else None
        )
        summary = summarize_channel(
            df[channel["amplitude_column"]].to_numpy(dtype=float),
            frequencies,
        )
        rows.append(
            {
                "Channel": channel["label"],
                "Stored statistic": channel["statistic"],
                "Unit": channel["unit"],
                "Valid intervals": summary["valid_count"],
                "Maximum": _round(summary["maximum"]),
                "Frequency at maximum (Hz)": _round(
                    summary["frequency_at_peak"], 3
                ),
                "Mean": _round(summary["mean"]),
                "Median": _round(summary["median"]),
                "P95": _round(summary["p95"]),
                "P99": _round(summary["p99"]),
            }
        )
    return rows


def _trend_dataframe(records):
    return pd.DataFrame(
        [
            {
                "Channel": record["channel"],
                "Quantity": record["quantity"],
                "Stored statistic": record["statistic"],
                "Unit": record["unit"],
                "Start (min)": round(record["start_seconds"] / 60, 5),
                "End (min)": round(record["end_seconds"] / 60, 5),
                "Intervals": record["interval_count"],
                "Valid": record["valid_count"],
                "Maximum": _round(record["maximum"]),
                "Frequency at maximum (Hz)": _round(
                    record["frequency_at_max"], 3
                ),
                "Mean": _round(record["mean"]),
                "Median": _round(record["median"]),
                "P95": _round(record["p95"]),
                "P99": _round(record["p99"]),
            }
            for record in records
        ]
    )


def _stored_statistics_label(channels):
    statistics = sorted({channel["statistic"] for channel in channels})
    return " / ".join(statistics)


def _shared_axis_compatible(channels):
    if len(channels) < 2:
        return False
    quantities = {
        str(channel.get("quantity", "")).strip().casefold()
        for channel in channels
    }
    units = {
        str(channel.get("unit", "")).replace(" ", "").casefold()
        for channel in channels
    }
    return len(quantities) == 1 and len(units) == 1 and "" not in units


def _recording_duration(times, interval_seconds):
    finite = times[np.isfinite(times)]
    if not finite.size:
        return float(interval_seconds)
    return float(finite[-1] - finite[0] + interval_seconds)


def _format_window(seconds):
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds / 3600:g} h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds / 60:g} min"
    return f"{seconds:g} s"


def _filename_window(seconds):
    return f"{seconds:g}s".replace(".", "p")


def _round(value, digits=4):
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), digits)

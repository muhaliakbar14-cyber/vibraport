"""Long-term Monitoring page for SIS bargraph recordings."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from core import detect_equipment_model
from core.monitoring import (
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
    "Other": "#607D8B",
}

MAX_DISPLAY_POINTS = 1800
MAX_ALERT_MARKERS = 400


def render(df, time_axis, metadata, sampling_rate):
    st.title("📊 Bargraph Monitoring")
    st.caption("Interval summaries for long-term monitoring records")
    st.divider()

    if metadata.get("is_waveform", True):
        st.info(
            "This page is for **Bargraph** recordings only. "
            "The current file is a Waveform recording."
        )
        return

    channels = get_display_channels(df, metadata)
    if not channels:
        st.warning("No bargraph amplitude data found in file.")
        return

    times = np.asarray(time_axis, dtype=float)
    interval_seconds = metadata.get("Monitoring interval seconds")
    if not interval_seconds:
        interval_seconds = infer_monitoring_interval(times, fallback=sampling_rate) or 0.0

    _render_data_overview(df, times, metadata, channels, interval_seconds)
    st.divider()

    thresholds = render_threshold_controls(channels)
    st.divider()

    _render_timeline(df, times, metadata, channels, thresholds, interval_seconds)
    st.divider()

    _render_statistics(df, channels, thresholds)
    _render_frequency_distribution(df, channels)


def get_display_channels(df, metadata=None):
    channels = get_bargraph_channels(df, metadata)
    for channel in channels:
        color_key = (
            channel["quantity"]
            if channel["quantity"] in ("Pressure", "KBf")
            else channel["axis"]
        )
        channel["color"] = CHANNEL_COLORS.get(color_key, CHANNEL_COLORS["Other"])
    return channels


def _render_data_overview(df, times, metadata, channels, interval_seconds):
    st.markdown("## Data Overview")

    sample_count = len(times)
    duration_seconds = sample_count * interval_seconds if interval_seconds else 0.0
    serial = metadata.get("Serial number", "")
    equipment = metadata.get("Equipment") or detect_equipment_model(serial)
    equipment_short = equipment.removeprefix("Vibracord ")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Equipment", equipment_short)
    c2.metric("Duration", _format_duration(duration_seconds))
    c3.metric("Monitoring interval", _format_interval(interval_seconds))
    c4.metric("Intervals / channels", f"{sample_count:,} / {len(channels)}")

    quality_rows = []
    total_invalid = 0
    any_over_range = False
    for channel in channels:
        values = df[channel["amplitude_column"]].to_numpy(dtype=float)
        summary = summarize_channel(values)
        total_invalid += summary["invalid_count"]
        any_over_range = any_over_range or channel["over_range"]
        quality_rows.append(
            {
                "Channel": channel["label"],
                "Quantity": channel["quantity"],
                "Statistic": channel["statistic"],
                "Unit": channel["unit"] or "—",
                "Transducer": channel["transducer_type"],
                "Dominant frequency": (
                    "Available" if channel["frequency_available"] else "Unavailable"
                ),
                "Over-range": "Yes" if channel["over_range"] else "No",
                "Invalid intervals": summary["invalid_count"],
            }
        )

    if any_over_range:
        st.error(
            "One or more channels carry an instrument over-range flag. "
            "Treat their maxima as incomplete."
        )
    elif total_invalid:
        st.warning(f"The recording contains {total_invalid:,} non-finite channel values.")
    else:
        st.success(
            "Data-quality check passed: no over-range flags or non-finite amplitudes were found."
        )

    st.caption(
        "Statistic labels come from the SIS channel configuration. "
        "Unflagged bargraph values are treated as instrument-reported interval peaks, not RMS."
    )

    with st.expander("Channel capabilities and recording details", expanded=False):
        st.dataframe(pd.DataFrame(quality_rows), width="stretch", hide_index=True)
        detail_1, detail_2, detail_3, detail_4 = st.columns(4)
        detail_1.metric("Serial number", serial or "N/A")
        detail_2.metric("Date", metadata.get("Date", "N/A"))
        detail_3.metric("Start time", metadata.get("Time", "N/A"))
        detail_4.metric(
            "End time", _format_end_time(metadata.get("Bargraph end time"))
        )

        st.caption(f"Calibration date: {metadata.get('Calibration date', 'N/A')}")
        for index in range(1, 4):
            note = metadata.get(f"Note {index}", "")
            if note:
                st.caption(f"Note {index}: {note}")


def render_threshold_controls(channels):
    st.markdown("## Operational Alert Thresholds")
    st.caption(
        "These are user-defined screening alarms. They are not regulatory compliance limits."
    )

    quantities = {channel["quantity"] for channel in channels}
    thresholds = {}
    control_columns = st.columns(2)

    if "Velocity" in quantities:
        with control_columns[0]:
            st.markdown("**Velocity (mm/s)**")
            yellow_col, red_col = st.columns(2)
            yellow = yellow_col.number_input(
                "⚠️ Yellow",
                min_value=0.0,
                value=1.0,
                step=0.1,
                format="%.1f",
                key="vel_yellow",
            )
            red = red_col.number_input(
                "🚨 Red",
                min_value=0.0,
                value=5.0,
                step=0.1,
                format="%.1f",
                key="vel_red",
            )
            thresholds["Velocity"] = (yellow, red)

    if "Pressure" in quantities:
        with control_columns[1]:
            st.markdown("**Pressure (Pa)**")
            yellow_col, red_col = st.columns(2)
            yellow = yellow_col.number_input(
                "⚠️ Yellow",
                min_value=0.0,
                value=50.0,
                step=1.0,
                format="%.1f",
                key="pa_yellow",
            )
            red = red_col.number_input(
                "🚨 Red",
                min_value=0.0,
                value=100.0,
                step=1.0,
                format="%.1f",
                key="pa_red",
            )
            thresholds["Pressure"] = (yellow, red)

    if not thresholds:
        st.info(
            "No velocity or pressure channels are available for operational threshold alarms."
        )

    for quantity, (yellow, red) in thresholds.items():
        if yellow > 0 and red > 0 and red <= yellow:
            st.warning(
                f"{quantity}: the red threshold should be greater than the yellow threshold."
            )
    return thresholds


@st.cache_data(show_spinner=False)
def _cached_display_series(times, amplitudes, max_points):
    return peak_preserving_downsample(times, amplitudes, max_points=max_points)


def _render_timeline(
    df, times, metadata, channels, thresholds, interval_seconds
):
    st.markdown("## Timeline")

    if times.size == 0:
        st.warning("The recording has no monitoring intervals.")
        return

    duration_seconds = (
        float(times[-1] + interval_seconds)
        if interval_seconds
        else float(times[-1])
    )
    widget_suffix = hashlib.sha1(
        str(metadata.get("_filename", "active-bargraph")).encode("utf-8")
    ).hexdigest()[:10]

    range_options = ["Full recording"]
    if duration_seconds > 15 * 60:
        range_options.append("Last 15 minutes")
    if duration_seconds > 60 * 60:
        range_options.append("Last 60 minutes")
    if duration_seconds > max(2 * interval_seconds, 60):
        range_options.append("Custom range")

    controls_1, controls_2 = st.columns([2, 1])
    range_mode = controls_1.selectbox(
        "Displayed range",
        range_options,
        key=f"monitor_range_mode_{widget_suffix}",
    )
    show_alert_markers = controls_2.checkbox(
        "Show alert markers",
        value=True,
        key=f"monitor_alert_markers_{widget_suffix}",
    )

    start_seconds = 0.0
    end_seconds = duration_seconds
    if range_mode == "Last 15 minutes":
        start_seconds = max(0.0, duration_seconds - 15 * 60)
    elif range_mode == "Last 60 minutes":
        start_seconds = max(0.0, duration_seconds - 60 * 60)
    elif range_mode == "Custom range":
        duration_minutes = duration_seconds / 60
        start_minute, end_minute = st.slider(
            "Time window (minutes)",
            min_value=0.0,
            max_value=float(duration_minutes),
            value=(0.0, float(duration_minutes)),
            step=max(
                0.1,
                min(1.0, interval_seconds / 60 if interval_seconds else 0.1),
            ),
            key=f"monitor_custom_range_{widget_suffix}",
        )
        start_seconds, end_seconds = start_minute * 60, end_minute * 60

    window_mask = (times >= start_seconds) & (times <= end_seconds)
    window_times = times[window_mask]
    if window_times.size == 0:
        st.warning("No monitoring intervals fall inside the selected range.")
        return

    figure = make_subplots(
        rows=len(channels),
        cols=1,
        shared_xaxes=True,
        subplot_titles=[
            (
                f"{channel['label']} · {channel['statistic']} · "
                f"{channel['unit'] or 'unit not specified'}"
            )
            for channel in channels
        ],
        vertical_spacing=min(0.10, 0.36 / max(len(channels), 1)),
    )

    any_yellow = False
    any_red = False
    rendered_points = 0
    marker_limit_applied = False

    for row, channel in enumerate(channels, start=1):
        all_amplitudes = df[channel["amplitude_column"]].to_numpy(dtype=float)
        window_amplitudes = all_amplitudes[window_mask]
        display_times, display_amplitudes = _cached_display_series(
            window_times, window_amplitudes, MAX_DISPLAY_POINTS
        )
        rendered_points += len(display_times)

        figure.add_trace(
            go.Scattergl(
                x=display_times / 60,
                y=display_amplitudes,
                mode="lines",
                name=channel["label"],
                line=dict(color=channel["color"], width=1.25),
                showlegend=False,
                connectgaps=False,
                hovertemplate=(
                    f"t=%{{x:.2f}} min<br>{channel['label']}: "
                    f"%{{y:.3f}} {channel['unit']}<extra></extra>"
                ),
            ),
            row=row,
            col=1,
        )

        limits = thresholds.get(channel["quantity"])
        if not limits:
            continue
        yellow_limit, red_limit = limits

        if yellow_limit > 0:
            figure.add_hline(
                y=yellow_limit,
                line=dict(color="#FFC107", dash="dash", width=1.3),
                row=row,
                col=1,
            )
        if red_limit > 0:
            figure.add_hline(
                y=red_limit,
                line=dict(color="#E53935", dash="dash", width=1.3),
                row=row,
                col=1,
            )

        finite_all = np.isfinite(all_amplitudes)
        red_mask_all = (
            finite_all & (all_amplitudes >= red_limit)
            if red_limit > 0
            else np.zeros_like(finite_all)
        )
        if red_limit > yellow_limit > 0:
            yellow_mask_all = (
                finite_all
                & (all_amplitudes >= yellow_limit)
                & (all_amplitudes < red_limit)
            )
        elif yellow_limit > 0:
            yellow_mask_all = finite_all & (all_amplitudes >= yellow_limit)
        else:
            yellow_mask_all = np.zeros_like(finite_all)
        any_yellow = any_yellow or bool(np.any(yellow_mask_all))
        any_red = any_red or bool(np.any(red_mask_all))

        if not show_alert_markers:
            continue

        for mask, color, alert_name in (
            (yellow_mask_all[window_mask], "#FFC107", "YELLOW"),
            (red_mask_all[window_mask], "#E53935", "RED"),
        ):
            marker_indices = np.flatnonzero(mask)
            if marker_indices.size > MAX_ALERT_MARKERS:
                local_values = window_amplitudes[marker_indices]
                keep = np.argpartition(
                    local_values, -MAX_ALERT_MARKERS
                )[-MAX_ALERT_MARKERS:]
                marker_indices = np.sort(marker_indices[keep])
                marker_limit_applied = True
            if not marker_indices.size:
                continue
            figure.add_trace(
                go.Scattergl(
                    x=window_times[marker_indices] / 60,
                    y=window_amplitudes[marker_indices],
                    mode="markers",
                    marker=dict(color=color, size=7, symbol="triangle-up"),
                    showlegend=False,
                    hovertemplate=(
                        f"{alert_name}<br>t=%{{x:.2f}} min<br>{channel['label']}: "
                        f"%{{y:.3f}} {channel['unit']}<extra></extra>"
                    ),
                ),
                row=row,
                col=1,
            )

    figure.update_xaxes(title_text="Time (min)", row=len(channels), col=1)
    figure.update_yaxes(tickfont=dict(size=10), rangemode="tozero")
    figure.update_layout(
        height=max(420, 235 * len(channels)),
        hovermode="x",
        showlegend=False,
        margin=dict(t=45, b=60, l=60, r=35),
        plot_bgcolor="white",
        uirevision=widget_suffix,
    )
    for annotation in figure.layout.annotations:
        annotation.update(font=dict(size=12))

    st.plotly_chart(
        figure,
        width="stretch",
        config={"scrollZoom": False, "displaylogo": False},
    )
    st.caption(
        f"Displaying {window_times.size:,} of {times.size:,} intervals using "
        f"{rendered_points:,} peak-preserving line points across {len(channels)} channels. "
        "All statistics and alert counts use the complete, full-resolution recording."
    )
    if marker_limit_applied:
        st.caption(
            f"Alert markers were limited to the {MAX_ALERT_MARKERS} highest visible "
            "values per alert level and channel."
        )

    if any_red:
        st.error(
            "🚨 The red operational threshold is exceeded in one or more channels."
        )
    elif any_yellow:
        st.warning(
            "⚠️ The yellow operational threshold is exceeded in one or more channels."
        )
    elif thresholds:
        st.success(
            "✅ All eligible channels remain within the operational thresholds."
        )


def _render_statistics(df, channels, thresholds):
    st.markdown("## Full-Resolution Statistics")
    rows = []

    for channel in channels:
        amplitudes = df[channel["amplitude_column"]].to_numpy(dtype=float)
        frequency_column = channel.get("frequency_column")
        frequencies = (
            df[frequency_column].to_numpy(dtype=float)
            if frequency_column and frequency_column in df.columns
            else None
        )
        summary = summarize_channel(amplitudes, frequencies)
        yellow_count = 0
        red_count = 0
        limits = thresholds.get(channel["quantity"])
        finite = np.isfinite(amplitudes)
        if limits:
            yellow_limit, red_limit = limits
            red_count = (
                int(np.sum(finite & (amplitudes >= red_limit)))
                if red_limit > 0
                else 0
            )
            if red_limit > yellow_limit > 0:
                yellow_count = int(
                    np.sum(
                        finite
                        & (amplitudes >= yellow_limit)
                        & (amplitudes < red_limit)
                    )
                )
            elif yellow_limit > 0:
                yellow_count = int(
                    np.sum(finite & (amplitudes >= yellow_limit))
                )

        rows.append(
            {
                "Channel": channel["label"],
                "Statistic": channel["statistic"],
                "Maximum": _format_measurement(
                    summary["maximum"], channel["unit"]
                ),
                "Frequency at maximum": _format_frequency(
                    summary["frequency_at_peak"]
                ),
                "Mean": _format_measurement(summary["mean"], channel["unit"]),
                "Median": _format_measurement(
                    summary["median"], channel["unit"]
                ),
                "P95": _format_measurement(summary["p95"], channel["unit"]),
                "P99": _format_measurement(summary["p99"], channel["unit"]),
                "Yellow intervals": yellow_count if limits else "—",
                "Red intervals": red_count if limits else "—",
                "Invalid": summary["invalid_count"],
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_frequency_distribution(df, channels):
    frequency_channels = [
        channel
        for channel in channels
        if channel.get("frequency_available")
        and channel.get("frequency_column") in df.columns
    ]
    if not frequency_channels:
        return

    st.divider()
    st.markdown("## Dominant Frequency Distribution")

    frequencies_by_channel = []
    active_channels = []
    for channel in frequency_channels:
        values = df[channel["frequency_column"]].to_numpy(dtype=float)
        values = values[np.isfinite(values) & (values > 0)]
        if values.size:
            active_channels.append(channel)
            frequencies_by_channel.append(values)
    if not frequencies_by_channel:
        st.info(
            "The file has frequency columns, but no positive dominant-frequency values."
        )
        return

    maximum_frequency = max(
        float(np.max(values)) for values in frequencies_by_channel
    )
    total_values = sum(len(values) for values in frequencies_by_channel)
    bin_count = min(40, max(10, int(np.sqrt(total_values))))
    edges = np.linspace(0, maximum_frequency, bin_count + 1)
    centers = (edges[:-1] + edges[1:]) / 2

    figure = go.Figure()
    for channel, frequencies in zip(active_channels, frequencies_by_channel):
        counts, _ = np.histogram(frequencies, bins=edges)
        figure.add_trace(
            go.Bar(
                x=centers,
                y=counts,
                width=np.diff(edges),
                name=channel["label"],
                marker_color=channel["color"],
                opacity=0.6,
                hovertemplate=(
                    "Frequency=%{x:.1f} Hz<br>Intervals=%{y}"
                    "<extra>%{fullData.name}</extra>"
                ),
            )
        )

    figure.update_layout(
        xaxis_title="Dominant frequency (Hz)",
        yaxis_title="Intervals",
        barmode="overlay",
        height=320,
        legend=dict(orientation="h", y=-0.25),
        margin=dict(t=20, b=70),
    )
    st.plotly_chart(
        figure, width="stretch", config={"displaylogo": False}
    )


def _format_duration(seconds):
    if not seconds or not np.isfinite(seconds):
        return "N/A"
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs} s"


def _format_interval(seconds):
    if not seconds or not np.isfinite(seconds):
        return "Unknown"
    return f"{seconds:g} s"


def _format_end_time(value):
    if isinstance(value, (tuple, list)) and len(value) == 3 and any(value):
        return "{:02d}:{:02d}:{:02d}".format(*value)
    if isinstance(value, str) and value:
        return value
    return "Unavailable"


def _format_measurement(value, unit):
    if value is None or not np.isfinite(value):
        return "—"
    suffix = f" {unit}" if unit else ""
    return f"{value:.3f}{suffix}"


def _format_frequency(value):
    if value is None or not np.isfinite(value) or value <= 0:
        return "—"
    return f"{value:g} Hz"

"""Operational event review for SIS bargraph recordings."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.monitoring import detect_events_for_channels, infer_monitoring_interval
from pages.monitoring import get_display_channels, render_threshold_controls


def render(df, time_axis, metadata, sampling_rate):
    st.title("🚨 Events & Thresholds")
    st.caption(
        "Group full-resolution bargraph exceedances into reviewable monitoring events"
    )
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
        interval_seconds = (
            infer_monitoring_interval(times, fallback=sampling_rate) or 1.0
        )

    thresholds = render_threshold_controls(channels)
    if not thresholds:
        return

    st.divider()
    st.markdown("## Event Grouping")
    st.caption(
        "An event starts at the yellow threshold. Hysteresis prevents rapid "
        "on/off switching, while gap tolerance can join brief quiet intervals."
    )

    settings_1, settings_2, settings_3 = st.columns(3)
    minimum_duration = settings_1.number_input(
        "Minimum event duration (s)",
        min_value=0.0,
        value=float(interval_seconds),
        step=float(interval_seconds),
        help="Events shorter than this duration are excluded.",
    )
    gap_tolerance = settings_2.number_input(
        "Quiet-gap tolerance (s)",
        min_value=0.0,
        value=0.0,
        step=float(interval_seconds),
        help="Join exceedances separated by no more than this quiet duration.",
    )
    hysteresis_percent = settings_3.slider(
        "Release hysteresis (%)",
        min_value=0,
        max_value=50,
        value=10,
        step=1,
        help=(
            "After an event starts, it remains active until the signal falls "
            "this percentage below the yellow threshold."
        ),
    )

    events = detect_events_for_channels(
        df,
        times,
        channels,
        thresholds,
        interval_seconds=interval_seconds,
        gap_tolerance_seconds=gap_tolerance,
        hysteresis_percent=hysteresis_percent,
        minimum_duration_seconds=minimum_duration,
    )

    if not events:
        st.success("No events match the current thresholds and grouping settings.")
        return

    red_events = [event for event in events if event["severity"] == "Red"]
    longest_event = max(event["duration_seconds"] for event in events)
    highest_event = max(events, key=lambda event: event["peak"])

    summary_1, summary_2, summary_3, summary_4 = st.columns(4)
    summary_1.metric("Total events", f"{len(events):,}")
    summary_2.metric("Red events", f"{len(red_events):,}")
    summary_3.metric("Longest event", _format_duration(longest_event))
    summary_4.metric(
        "Highest event peak",
        f"{highest_event['peak']:.3f} {highest_event['unit']}",
    )

    event_rows = []
    for number, event in enumerate(events, start=1):
        event_rows.append(
            {
                "Event": f"E{number:04d}",
                "Severity": event["severity"],
                "Channel": event["channel"],
                "Start (min)": round(event["start_seconds"] / 60, 3),
                "End (min)": round(event["end_seconds"] / 60, 3),
                "Duration (s)": round(event["duration_seconds"], 3),
                "Peak": round(event["peak"], 4),
                "Unit": event["unit"],
                "Peak time (min)": round(event["peak_seconds"] / 60, 3),
                "Frequency at peak (Hz)": (
                    event["frequency_at_peak"]
                    if event["frequency_at_peak"] is not None
                    else "—"
                ),
                "Event intervals": event["interval_count"],
                "Exceeding intervals": event["exceedance_intervals"],
            }
        )

    event_table = pd.DataFrame(event_rows)
    st.dataframe(event_table, width="stretch", hide_index=True)

    filename = metadata.get("_filename", "bargraph")
    export_name = filename.rsplit(".", 1)[0] + "-events.csv"
    st.download_button(
        "⬇️ Export events as CSV",
        data=event_table.to_csv(index=False).encode("utf-8"),
        file_name=export_name,
        mime="text/csv",
    )

    st.divider()
    st.markdown("## Event Detail")
    event_labels = [
        (
            f"E{number:04d} · {event['severity']} · {event['channel']} · "
            f"{event['start_seconds'] / 60:.2f} min"
        )
        for number, event in enumerate(events, start=1)
    ]
    selected_label = st.selectbox("Jump to event", event_labels)
    selected_index = event_labels.index(selected_label)
    _render_event_detail(
        df,
        times,
        channels,
        events[selected_index],
        interval_seconds,
    )


def _render_event_detail(df, times, channels, event, interval_seconds):
    channel = next(
        channel for channel in channels if channel["label"] == event["channel"]
    )
    amplitudes = df[channel["amplitude_column"]].to_numpy(dtype=float)
    padding = max(30.0, event["duration_seconds"] * 0.5)
    window_start = max(0.0, event["start_seconds"] - padding)
    window_end = event["end_seconds"] + interval_seconds + padding
    mask = (times >= window_start) & (times <= window_end)

    figure = go.Figure()
    figure.add_trace(
        go.Scattergl(
            x=times[mask] / 60,
            y=amplitudes[mask],
            mode="lines",
            line=dict(color=channel["color"], width=1.5),
            name=channel["label"],
            hovertemplate=(
                f"t=%{{x:.3f}} min<br>%{{y:.3f}} {channel['unit']}"
                "<extra></extra>"
            ),
        )
    )
    figure.add_hline(
        y=event["yellow_threshold"],
        line=dict(color="#FFC107", dash="dash"),
        annotation_text="Yellow",
        annotation_position="top left",
    )
    if event["red_threshold"] is not None:
        figure.add_hline(
            y=event["red_threshold"],
            line=dict(color="#E53935", dash="dash"),
            annotation_text="Red",
            annotation_position="top left",
        )
    figure.add_vrect(
        x0=event["start_seconds"] / 60,
        x1=(event["end_seconds"] + interval_seconds) / 60,
        fillcolor="#E53935" if event["severity"] == "Red" else "#FFC107",
        opacity=0.10,
        line_width=0,
    )
    figure.add_trace(
        go.Scattergl(
            x=[event["peak_seconds"] / 60],
            y=[event["peak"]],
            mode="markers",
            marker=dict(
                color="#E53935" if event["severity"] == "Red" else "#FFC107",
                size=11,
                symbol="diamond",
            ),
            name=f"{event['severity']} peak",
            hovertemplate=(
                f"Peak=%{{y:.3f}} {event['unit']}<br>"
                "t=%{x:.3f} min<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=(
            f"{event['channel']} · {event['severity']} event · "
            f"{_format_duration(event['duration_seconds'])}"
        ),
        xaxis_title="Time (min)",
        yaxis_title=event["unit"],
        height=390,
        hovermode="x",
        margin=dict(t=55, b=55, l=60, r=30),
        showlegend=False,
        plot_bgcolor="white",
    )
    figure.update_yaxes(rangemode="tozero")
    st.plotly_chart(
        figure,
        width="stretch",
        config={"scrollZoom": False, "displaylogo": False},
    )

    frequency_text = (
        f"{event['frequency_at_peak']:g} Hz"
        if event["frequency_at_peak"] is not None
        else "Unavailable"
    )
    st.caption(
        f"Peak: {event['peak']:.3f} {event['unit']} at "
        f"{event['peak_seconds'] / 60:.3f} min · "
        f"Dominant frequency: {frequency_text} · "
        f"{event['exceedance_intervals']} threshold-exceeding intervals."
    )


def _format_duration(seconds):
    if seconds >= 60:
        minutes, remainder = divmod(seconds, 60)
        return f"{int(minutes)}m {remainder:.1f}s"
    return f"{seconds:.1f}s"

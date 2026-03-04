# pages/monitoring.py
"""
Long-term Monitoring page — Bargraph mode recordings.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from core import detect_equipment_model


BLOCK_COLORS = {
    'Vertical':     '#00897B',
    'Longitudinal': '#E53935',
    'Transversal':  '#5C6BC0',
    'Pressure':     '#FFB300',
    'KBf':          '#8E24AA',
    'Other':        '#607D8B',
}

AXIS_LABEL = {
    'Vertical': 'Vertical', 'X': 'Vertical',
    'Longitudinal': 'Longitudinal', 'Y': 'Longitudinal',
    'Transverse': 'Transversal', 'Transversal': 'Transversal', 'Z': 'Transversal',
    'Not affected': 'Pressure',
}


def render(df, time_axis, metadata, sampling_rate):
    st.title("📊 Bargraph Monitoring")
    st.divider()

    if metadata.get('is_waveform', True):
        st.info("This page is for **Bargraph** recordings only. The current file is a Waveform recording.")
        return

    # ── Recording Info (same as Data Overview) ─────────────────────────────────
    _render_recording_info(metadata, time_axis, sampling_rate)
    st.divider()

    # ── Threshold controls ─────────────────────────────────────────────────────
    st.markdown("## Alert Thresholds")
    channels = _get_bargraph_channels(df)
    has_pressure = any(ch['unit'] == 'Pa' for ch in channels)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Velocity (mm/s)**")
        c1, c2 = st.columns(2)
        vel_yellow = c1.number_input("⚠️ Yellow", min_value=0.0, value=1.0, step=0.1,
                                      format="%.2f", key="vel_yellow")
        vel_red    = c2.number_input("🚨 Red",    min_value=0.0, value=5.0, step=0.1,
                                      format="%.2f", key="vel_red")
    with col2 if has_pressure else st.container():
        if has_pressure:
            st.markdown("**Pressure (Pa)**")
            c3, c4 = st.columns(2)
            pa_yellow = c3.number_input("⚠️ Yellow", min_value=0.0, value=50.0,  step=1.0,
                                         format="%.1f", key="pa_yellow")
            pa_red    = c4.number_input("🚨 Red",    min_value=0.0, value=100.0, step=1.0,
                                         format="%.1f", key="pa_red")
        else:
            pa_yellow, pa_red = 0.0, 0.0

    st.divider()

    # ── Timeline chart ─────────────────────────────────────────────────────────
    st.markdown("## Timeline")
    if not channels:
        st.warning("No bargraph amplitude data found in file.")
        return

    time_min = time_axis / 60

    fig = make_subplots(
        rows=len(channels), cols=1,
        shared_xaxes=True,
        subplot_titles=[ch['label'] for ch in channels],
        vertical_spacing=0.04,
    )

    any_yellow = False
    any_red    = False

    for i, ch in enumerate(channels, start=1):
        amp   = df[ch['amp_col']].values
        color = ch['color']
        unit  = ch['unit']

        is_pressure = (unit == 'Pa')
        y_thresh    = (pa_yellow, pa_red) if is_pressure else (vel_yellow, vel_red)
        yellow_lim, red_lim = y_thresh

        # Bar chart
        fig.add_trace(go.Bar(
            x=time_min, y=amp,
            name=ch['label'],
            marker_color=color,
            opacity=0.7,
            showlegend=False,
            hovertemplate=f"t=%{{x:.1f}} min<br>{ch['label']}: %{{y:.3f}} {unit}<extra></extra>",
        ), row=i, col=1)

        # Yellow threshold line
        if yellow_lim > 0:
            fig.add_hline(y=yellow_lim, line=dict(color='#FFC107', dash='dash', width=1.5),
                          row=i, col=1)

        # Red threshold line
        if red_lim > 0:
            fig.add_hline(y=red_lim, line=dict(color='#E53935', dash='dash', width=1.5),
                          row=i, col=1)

        # Yellow exceedance markers
        y_mask = (amp >= yellow_lim) & (amp < red_lim) if red_lim > yellow_lim else (amp >= yellow_lim)
        if yellow_lim > 0 and y_mask.any():
            any_yellow = True
            fig.add_trace(go.Scatter(
                x=time_min[y_mask], y=amp[y_mask],
                mode='markers',
                marker=dict(color='#FFC107', size=8, symbol='triangle-up'),
                showlegend=False,
                hovertemplate=f"⚠️ YELLOW<br>t=%{{x:.1f}} min<br>{ch['label']}: %{{y:.3f}} {unit}<extra></extra>",
            ), row=i, col=1)

        # Red exceedance markers
        r_mask = amp >= red_lim
        if red_lim > 0 and r_mask.any():
            any_red = True
            fig.add_trace(go.Scatter(
                x=time_min[r_mask], y=amp[r_mask],
                mode='markers',
                marker=dict(color='#E53935', size=9, symbol='triangle-up'),
                showlegend=False,
                hovertemplate=f"🚨 RED<br>t=%{{x:.1f}} min<br>{ch['label']}: %{{y:.3f}} {unit}<extra></extra>",
            ), row=i, col=1)

    fig.update_xaxes(title_text="Time (min)", row=len(channels), col=1)
    fig.update_yaxes(tickfont=dict(size=10))
    fig.update_layout(
        height=max(200, 140 * len(channels)),
        hovermode="x unified",
        showlegend=False,
        margin=dict(t=40, b=60, l=60, r=40),
        plot_bgcolor='white',
    )
    for ann in fig.layout.annotations:
        ann.update(font=dict(size=12))

    st.plotly_chart(fig, use_container_width=True)

    # ── Alert banner ───────────────────────────────────────────────────────────
    if any_red:
        st.error("🚨 Red threshold exceeded in one or more channels.")
    elif any_yellow:
        st.warning("⚠️ Yellow threshold exceeded in one or more channels.")
    else:
        st.success("✅ All channels within thresholds.")

    st.divider()

    # ── Statistics table ───────────────────────────────────────────────────────
    st.markdown("## Statistics")

    rows = []
    for ch in channels:
        amp       = df[ch['amp_col']].values
        unit      = ch['unit']
        is_pres   = (unit == 'Pa')
        y_lim     = pa_yellow if is_pres else vel_yellow
        r_lim     = pa_red    if is_pres else vel_red
        y_count   = int((amp >= y_lim).sum()) if y_lim > 0 else 0
        r_count   = int((amp >= r_lim).sum()) if r_lim > 0 else 0
        rows.append({
            'Channel':       ch['label'],
            'Max':           f"{amp.max():.3f} {unit}",
            'Mean':          f"{amp.mean():.3f} {unit}",
            'Std Dev':       f"{amp.std():.3f} {unit}",
            '⚠️ Yellow':     y_count,
            '🚨 Red':        r_count,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Frequency histogram ────────────────────────────────────────────────────
    freq_channels = [ch for ch in channels if ch.get('freq_col') and ch['freq_col'] in df.columns]
    if freq_channels:
        st.divider()
        st.markdown("## Dominant Frequency Distribution")
        freq_fig = go.Figure()
        for ch in freq_channels:
            freqs = df[ch['freq_col']].values.astype(float)
            freqs = freqs[freqs > 0]
            if len(freqs) == 0:
                continue
            freq_fig.add_trace(go.Histogram(
                x=freqs, name=ch['label'],
                marker_color=ch['color'], opacity=0.6, nbinsx=30,
            ))
        freq_fig.update_layout(
            xaxis_title="Frequency (Hz)", yaxis_title="Count",
            barmode='overlay', height=300,
            legend=dict(orientation='h', y=-0.25),
            margin=dict(t=20, b=60),
        )
        st.plotly_chart(freq_fig, use_container_width=True)


# ── Recording Info ─────────────────────────────────────────────────────────────

def _render_recording_info(metadata, time_axis, sampling_rate):
    st.markdown("## Recording Info")
    serial = metadata.get('Serial number', '')
    model  = detect_equipment_model(serial)

    n_bars     = len(time_axis)
    total_min  = round(n_bars * sampling_rate / 60, 1)
    duration   = f"{total_min} min ({n_bars} bars × {sampling_rate}s)"

    # ── Primary fields — always visible ───────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Equipment", model)
        st.metric("Serial Number", serial or "N/A")
    with c2:
        st.metric("Date", metadata.get('Date', 'N/A'))
        st.metric("Record Type", metadata.get('Record type', 'N/A'))
    with c3:
        st.metric("Start", metadata.get('Time', 'N/A'))
        st.metric("End", "{:02d}:{:02d}:{:02d}".format(*metadata.get('Bargraph end time', (0,0,0))))
    with c4:
        st.metric("Duration", f"{total_min} min")
        st.metric("Interval", f"{metadata.get('Sampling rate', 'N/A').split()[0]} seconds")
        
    # ── Secondary fields — collapsed by default ────────────────────────────────
    with st.expander("More Details", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Calibration Date", metadata.get('Calibration date', 'N/A'))
            gps_source = metadata.get('GPS source', 'Not set')
            lat = metadata.get('Latitude')
            lon = metadata.get('Longitude')
            if gps_source != 'Not set' and lat is not None:
                st.metric("GPS", f"{lat:.4f}, {lon:.4f}")
            else: 
                st.metric("GPS Source", gps_source)
        with c2:
            st.metric("Clock Source", metadata.get('Clock source', 'N/A'))

        with c3:
            notes = [metadata.get(f'Note {i}', '') for i in range(1, 4)]
            for i, note in enumerate(notes, 1):
                st.metric(f"Note {i}", note if note else "—")

# ── Channel list builder ───────────────────────────────────────────────────────

def _get_bargraph_channels(df):
    channels = []
    amp_cols = [c for c in df.columns if c.endswith('_amplitude')]
    for amp_col in amp_cols:
        base     = amp_col.replace('_amplitude', '')
        freq_col = base + '_frequency'
        parts    = base.split('_')
        if len(parts) < 3:
            continue
        ch_num     = parts[0]
        axis       = parts[1]
        mag        = '_'.join(parts[2:])
        axis_label = AXIS_LABEL.get(axis, axis)

        if 'Velocity' in mag or 'velocity' in mag:
            unit  = 'mm/s'
            color = BLOCK_COLORS.get(axis_label, BLOCK_COLORS['Other'])
        elif axis_label == 'Pressure':
            unit  = 'Pa'
            color = BLOCK_COLORS['Pressure']
        elif 'KBf' in mag:
            unit  = 'KBf'
            color = BLOCK_COLORS['KBf']
        else:
            unit  = ''
            color = BLOCK_COLORS['Other']

        channels.append({
            'amp_col':  amp_col,
            'freq_col': freq_col if freq_col in df.columns else None,
            'label':    f"{axis_label} ({ch_num})",
            'unit':     unit,
            'color':    color,
        })
    return channels

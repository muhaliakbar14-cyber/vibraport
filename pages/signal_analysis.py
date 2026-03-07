# pages/signal_analysis.py
"""
Signal Analysis page — stacked seismogram, frequency analysis, acceleration, displacement.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from core import calculate_frequency
from core.metrics import peak_displacement, acceleration_at_peak, acceleration_in_g
from config import (
    FREQUENCY_METHODS, DEFAULT_FREQUENCY_METHOD,
    LOW_AMPLITUDE_THRESHOLD,
)


# ── Colour palette ─────────────────────────────────────────────────────────────
BLOCK_COLORS = {
    'Vertical':     '#00897B',
    'Longitudinal': '#E53935',
    'Transversal':  '#5C6BC0',
    'Pressure':     '#FFB300',
    'KBf':          '#8E24AA',
    'Other':        '#607D8B',
}

B2_COLORS = {
    'Vertical':     '#26A69A',
    'Longitudinal': '#EF9A9A',
    'Transversal':  '#9FA8DA',
}


def render(df, time_axis, sampling_rate, make_chart_fn, metadata=None):
    st.title("📡 Signal Analysis")
    st.divider()

    # ── Velocity ─────────────────────────────────────────────────────────────
    st.markdown("## Velocity")
    with st.expander("🌊 Velocity", expanded=True):
        _render_stacked_chart(
            df, time_axis,
            channels=_get_display_channels(df),
            key_prefix='seis',
            show_sync_toggle=True,
        )

    st.divider()

    # ── Frequency Analysis ─────────────────────────────────────────────────────
    with st.expander("📡 Frequency Analysis", expanded=True):
        _render_frequency_analysis(df, time_axis, sampling_rate, metadata)

    st.divider()

    # ── Acceleration ───────────────────────────────────────────────────────────
    st.markdown("## Acceleration (Derivative)")
    with st.expander("⚡ Acceleration", expanded=False):
        accel_channels = _get_derived_channels(df, kind='accel')
        if accel_channels:
            _render_stacked_chart(
                df, time_axis,
                channels=accel_channels,
                key_prefix='accel',
                show_sync_toggle=True,
            )
        else:
            st.info("No acceleration data available.")

    st.divider()

    # ── Displacement ───────────────────────────────────────────────────────────
    st.markdown("## Displacement (Integral)")    
    with st.expander("📏 Displacement", expanded=False):
        disp_channels = _get_derived_channels(df, kind='disp')
        if disp_channels:
            _render_stacked_chart(
                df, time_axis,
                channels=disp_channels,
                key_prefix='disp',
                show_sync_toggle=True,
            )
        else:
            st.info("No displacement data available.")

    st.divider()

    # ── Acceleration at Peak Displacement ─────────────────────────────────────
    st.markdown("## A<sub>max</sub> for Slope Stability Analysis", unsafe_allow_html=True)
    with st.expander("🎯 Acceleration at Peak Displacement", expanded=False):
        _render_accel_at_peak(df, time_axis)


# ── Generic stacked chart ──────────────────────────────────────────────────────

def _render_stacked_chart(df, time_axis, channels, key_prefix, show_sync_toggle=False):
    """
    Reusable stacked chart renderer.
    Shared time axis, one row per channel, peak marker + label.

    show_sync_toggle: show a toggle to synchronise Y axis range across
                      channels of the same unit group.
    """
    if not channels:
        st.info("No data available.")
        return

    time_ms = time_axis * 1000

    # ── Y-axis sync toggle ─────────────────────────────────────────────────────
    sync_y = False
    if show_sync_toggle:
        sync_y = st.toggle("Sync Y-axis across channels", value=False,
                           key=f"{key_prefix}_sync_y")

    # Compute per-unit global max for synced Y
    unit_max = {}
    if sync_y:
        for ch in channels:
            u = ch['unit']
            mx = float(np.abs(df[ch['col']].values).max())
            unit_max[u] = max(unit_max.get(u, 0), mx)

    # ── Build figure ───────────────────────────────────────────────────────────
    fig = make_subplots(
        rows=len(channels), cols=1,
        shared_xaxes=True,
        subplot_titles=[ch['label'] for ch in channels],
        vertical_spacing=0.04,
    )

    for i, ch in enumerate(channels, start=1):
        col   = ch['col']
        color = ch['color']
        sig   = df[col].values
        unit  = ch['unit']

        fig.add_trace(
            go.Scatter(
                x=time_ms, y=sig,
                name=ch['label'],
                mode='lines',
                line=dict(color=color, width=1.2),
                showlegend=False,
            ),
            row=i, col=1
        )

        # Peak marker
        peak_idx = np.abs(sig).argmax()
        peak_t   = time_ms[peak_idx]
        peak_v   = sig[peak_idx]
        fig.add_trace(
            go.Scatter(
                x=[peak_t], y=[peak_v],
                mode='markers+text',
                marker=dict(color='red', size=8, symbol='square',
                            line=dict(color='black', width=1)),
                text=[f" {abs(peak_v):.3f} {unit}"],
                textposition='middle right',
                textfont=dict(size=12, color='red'),
                showlegend=False,
            ),
            row=i, col=1
        )

        # Sync Y axis
        if sync_y and unit in unit_max:
            ymax = unit_max[unit] * 1.15
            fig.update_yaxes(range=[-ymax, ymax], row=i, col=1)

    # Time ticks every 100 ms
    max_t     = time_ms[-1]
    tick_vals = list(range(0, int(max_t) + 100, 100))
    fig.update_xaxes(
        tickvals=tick_vals,
        ticktext=[str(t) for t in tick_vals],
        title_text="Time (ms)",
        row=len(channels), col=1,
    )
    fig.update_yaxes(tickfont=dict(size=10))
    fig.update_layout(
        height=max(200, 130 * len(channels)),
        hovermode="x unified",
        showlegend=False,
        margin=dict(t=40, b=60, l=60, r=40),
    )
    for ann in fig.layout.annotations:
        ann.update(font=dict(size=12, color='black'))

    st.plotly_chart(fig, use_container_width=True)


# ── Frequency Analysis ─────────────────────────────────────────────────────────

def _render_frequency_analysis(df, time_axis, sampling_rate, metadata=None):
    vel_cols = [c for c in df.columns
                if '(mm/s)' in c and 'A_' not in c and 'D_' not in c]

    if not vel_cols:
        st.info("No velocity data available.")
        return

    st.subheader("Frequency Results")

    # Use header values from device when available — more accurate than recomputing
    channel_info = (metadata or {}).get('Channel info', [])
    # Map velocity column names to channel_info index
    vel_ch_map = {}
    if channel_info:
        vel_idx = [i for i, ch in enumerate(channel_info)
                   if 'Velocity' in ch.get('magnitude', '') and not ch.get('is_virtual')]
        for j, col in enumerate(vel_cols):
            if j < len(vel_idx):
                vel_ch_map[col] = channel_info[vel_idx[j]]

    rows = []
    for col in vel_cols:
        ppv  = df[col].abs().max()
        warn = ' ⚠️' if ppv < LOW_AMPLITUDE_THRESHOLD else ''
        ch   = vel_ch_map.get(col)
        if ch:
            rows.append({
                'Channel':       col.replace(' (mm/s)', '') + warn,
                'Zero Crossing': f"{ch['freq_zero_crossing']} Hz",
                'FFT Peak':      f"{ch['freq_fft_peak']} Hz",
                'Energy 25%':    f"{ch['freq_energy_25']} Hz",
                'Energy 50%':    f"{ch['freq_energy_50']} Hz",
                'Energy 75%':    f"{ch['freq_energy_75']} Hz",
            })
        else:
            # Fallback: compute from signal (CSV files or missing header)
            sig = tuple(df[col].values)
            rows.append({
                'Channel':       col.replace(' (mm/s)', '') + warn,
                'Zero Crossing': f"{calculate_frequency(sig, sampling_rate, 'Zero Crossing')} Hz",
                'FFT Peak':      f"{calculate_frequency(sig, sampling_rate, 'FFT Peak')} Hz",
                'Energy 25%':    f"{calculate_frequency(sig, sampling_rate, 'Energy 25%')} Hz",
                'Energy 50%':    f"{calculate_frequency(sig, sampling_rate, 'Energy 50%')} Hz",
                'Energy 75%':    f"{calculate_frequency(sig, sampling_rate, 'Energy 75%')} Hz",
            })

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.subheader("FFT Spectrum (0–200 Hz)")
    fig_fft = go.Figure()
    n = len(df)
    for col in vel_cols:
        sig     = df[col].values
        fft_mag = np.abs(np.fft.rfft(sig)) / n
        freqs   = np.fft.rfftfreq(n, d=1 / sampling_rate)
        mask    = freqs <= 200
        fig_fft.add_trace(go.Scatter(
            x=freqs[mask], y=fft_mag[mask],
            name=col.replace(' (mm/s)', ''),
            mode='lines',
            line=dict(color=_col_to_color(col))
        ))
    fig_fft.update_layout(
        xaxis_title="Frequency (Hz)",
        yaxis_title="Amplitude",
        height=400,
        hovermode="x unified",
        legend=dict(orientation='h', y=-0.2),
    )
    st.plotly_chart(fig_fft, use_container_width=True)


# ── Acceleration at Peak Displacement ─────────────────────────────────────────

def _render_accel_at_peak(df, time_axis):
    blocks = [
        {
            'label': 'Block 1',
            'channels': [
                ('D_Vert (mm)',    'A_Vert (mm/s²)',    'Vertical',     '#00897B'),
                ('D_Long (mm)',    'A_Long (mm/s²)',    'Longitudinal', '#E53935'),
                ('D_Tran (mm)',    'A_Tran (mm/s²)',    'Transversal',  '#5C6BC0'),
            ]
        },
        {
            'label': 'Block 2',
            'channels': [
                ('D_Vert B2 (mm)', 'A_Vert B2 (mm/s²)', 'Vertical B2',     '#26A69A'),
                ('D_Long B2 (mm)', 'A_Long B2 (mm/s²)', 'Longitudinal B2', '#EF9A9A'),
                ('D_Tran B2 (mm)', 'A_Tran B2 (mm/s²)', 'Transversal B2',  '#9FA8DA'),
            ]
        },
    ]

    for block in blocks:
        available = [(d, a, l, c) for d, a, l, c in block['channels']
                     if d in df.columns and a in df.columns]
        if not available:
            continue

        st.markdown(f"**{block['label']}**")
        cols = st.columns(len(available))
        for i, (disp_col, accel_col, label, color) in enumerate(available):
            disp_sig  = df[disp_col].values
            accel_sig = df[accel_col].values
            peak_val, peak_idx = peak_displacement(disp_sig)
            accel_val = acceleration_at_peak(accel_sig, peak_idx)
            accel_g   = acceleration_in_g(accel_val)
            peak_time = time_axis[peak_idx] * 1000
            with cols[i]:
                st.markdown(f"**{label}**")
                st.metric("Peak Displacement", f"{abs(peak_val):.4f} mm")
                st.metric("Acceleration at Peak", f"{abs(accel_val):.2f} mm/s²")
                st.markdown(
                    f"<div style='margin-top:8px;'>"
                    f"<div style='font-size:12px;color:#888;margin-bottom:2px;'>Acceleration in g</div>"
                    f"<div style='display:flex;align-items:baseline;gap:4px;'>"
                    f"<div style='font-size:42px;font-weight:700;color:{color};line-height:1;'>"
                    f"{abs(accel_g):.4f}</div>"
                    f"<div style='font-size:20px;font-weight:600;color:{color};'>g</div>"
                    f"</div></div>",
                    unsafe_allow_html=True
                )
                st.caption(f"At t = {peak_time:.2f} ms")


# ── Channel list builders ──────────────────────────────────────────────────────

def _get_display_channels(df):
    """Ordered channel list for the seismogram."""
    channels = []
    ordered = [
        ('Vertical (mm/s)',        'Vertical',        'mm/s', BLOCK_COLORS['Vertical']),
        ('Longitudinal (mm/s)',    'Longitudinal',    'mm/s', BLOCK_COLORS['Longitudinal']),
        ('Transversal (mm/s)',     'Transversal',     'mm/s', BLOCK_COLORS['Transversal']),
        ('Vertical B2 (mm/s)',     'Vertical B2',     'mm/s', B2_COLORS['Vertical']),
        ('Longitudinal B2 (mm/s)', 'Longitudinal B2', 'mm/s', B2_COLORS['Longitudinal']),
        ('Transversal B2 (mm/s)',  'Transversal B2',  'mm/s', B2_COLORS['Transversal']),
    ]
    for col, label, unit, color in ordered:
        if col in df.columns:
            channels.append({'col': col, 'label': label, 'unit': unit, 'color': color})
    for col in df.columns:
        if '(Pa)' in col:
            channels.append({'col': col, 'label': 'Air Pressure', 'unit': 'Pa',
                             'color': BLOCK_COLORS['Pressure']})
    for col in df.columns:
        if 'KBf' in col:
            channels.append({'col': col, 'label': col, 'unit': 'KBf',
                             'color': BLOCK_COLORS['KBf']})
    return channels


def _get_derived_channels(df, kind):
    """
    Channel list for acceleration (kind='accel') or displacement (kind='disp').
    """
    channels = []
    if kind == 'accel':
        ordered = [
            ('A_Vert (mm/s²)',    'Vertical',        'mm/s²', BLOCK_COLORS['Vertical']),
            ('A_Long (mm/s²)',    'Longitudinal',    'mm/s²', BLOCK_COLORS['Longitudinal']),
            ('A_Tran (mm/s²)',    'Transversal',     'mm/s²', BLOCK_COLORS['Transversal']),
            ('A_Vert B2 (mm/s²)', 'Vertical B2',    'mm/s²', B2_COLORS['Vertical']),
            ('A_Long B2 (mm/s²)', 'Longitudinal B2','mm/s²', B2_COLORS['Longitudinal']),
            ('A_Tran B2 (mm/s²)', 'Transversal B2', 'mm/s²', B2_COLORS['Transversal']),
        ]
    else:
        ordered = [
            ('D_Vert (mm)',    'Vertical',        'mm', BLOCK_COLORS['Vertical']),
            ('D_Long (mm)',    'Longitudinal',    'mm', BLOCK_COLORS['Longitudinal']),
            ('D_Tran (mm)',    'Transversal',     'mm', BLOCK_COLORS['Transversal']),
            ('D_Vert B2 (mm)', 'Vertical B2',    'mm', B2_COLORS['Vertical']),
            ('D_Long B2 (mm)', 'Longitudinal B2','mm', B2_COLORS['Longitudinal']),
            ('D_Tran B2 (mm)', 'Transversal B2', 'mm', B2_COLORS['Transversal']),
        ]
    for col, label, unit, color in ordered:
        if col in df.columns:
            channels.append({'col': col, 'label': label, 'unit': unit, 'color': color})
    return channels


def _col_to_color(col):
    if 'Vertical' in col and 'B2' not in col:     return BLOCK_COLORS['Vertical']
    if 'Longitudinal' in col and 'B2' not in col: return BLOCK_COLORS['Longitudinal']
    if 'Transversal' in col and 'B2' not in col:  return BLOCK_COLORS['Transversal']
    if 'Vertical B2' in col:                      return B2_COLORS['Vertical']
    if 'Longitudinal B2' in col:                  return B2_COLORS['Longitudinal']
    if 'Transversal B2' in col:                   return B2_COLORS['Transversal']
    return BLOCK_COLORS['Other']

# pages/signal_analysis.py
"""
Signal Analysis page — acceleration, displacement, frequency analysis.
"""

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from core import calculate_frequency
from core.metrics import peak_displacement, acceleration_at_peak, acceleration_in_g
from config import (
    ACCEL_CHANNELS, DISP_CHANNELS, ACCEL_AT_PEAK_MAP,
    FREQUENCY_METHODS, DEFAULT_FREQUENCY_METHOD,
    VELOCITY_CHANNELS,
)


def render(df, time_axis, sampling_rate, make_chart_fn):
    st.title("📉 Signal Analysis")
    st.divider()

    # ── Frequency Analysis ─────────────────────────────────────────────────────
    with st.expander("📡 Frequency Analysis", expanded=True):
        st.subheader("Frequency Results")

        freq_channels = {
            ch: color for ch, color in VELOCITY_CHANNELS.items()
            if ch in df.columns
        }

        results_freq = {}
        for ch in freq_channels:
            sig = tuple(df[ch].values)
            results_freq[ch] = {
                'Zero Crossing (Hz)': calculate_frequency(sig, sampling_rate, "Zero Crossing"),
                'FFT Peak (Hz)':      calculate_frequency(sig, sampling_rate, "FFT Peak"),
                'Energy 25% (Hz)':    calculate_frequency(sig, sampling_rate, "Energy 25%"),
                'Energy 50% (Hz)':    calculate_frequency(sig, sampling_rate, "Energy 50%"),
                'Energy 75% (Hz)':    calculate_frequency(sig, sampling_rate, "Energy 75%"),
            }

        import pandas as pd
        freq_df = pd.DataFrame(results_freq).T
        st.dataframe(freq_df, use_container_width=True)

        # FFT Spectrum
        st.subheader("FFT Spectrum (0–200 Hz)")
        fig_fft = go.Figure()
        n = len(df)
        for ch, color in freq_channels.items():
            sig = df[ch].values
            fft_mag = np.abs(np.fft.rfft(sig)) / n
            freqs = np.fft.rfftfreq(n, d=1 / sampling_rate)
            mask = freqs <= 200
            fig_fft.add_trace(go.Scatter(
                x=freqs[mask], y=fft_mag[mask],
                name=ch, mode='lines',
                line=dict(color=color)
            ))
        fig_fft.update_layout(
            xaxis_title="Frequency (Hz)",
            yaxis_title="Amplitude",
            height=400,
            hovermode="x unified"
        )
        st.plotly_chart(fig_fft, use_container_width=True)

    st.divider()

    # ── Acceleration ───────────────────────────────────────────────────────────
    st.subheader("Acceleration (Derivative)")
    with st.expander("⚡ Acceleration", expanded=False):
        accel_cols = [c for c in ACCEL_CHANNELS.keys() if c in df.columns]
        if accel_cols:
            make_chart_fn(df, time_axis, accel_cols)
        else:
            st.info("No acceleration data available.")

    st.divider()

    # ── Displacement ───────────────────────────────────────────────────────────
    st.subheader("Displacement (Integral)")
    with st.expander("📏 Displacement", expanded=False):
        disp_cols = [c for c in DISP_CHANNELS.keys() if c in df.columns]
        if disp_cols:
            make_chart_fn(df, time_axis, disp_cols)
        else:
            st.info("No displacement data available.")

    st.divider()

    # ── Acceleration at Peak Displacement ─────────────────────────────────────
    st.subheader("Maximum A for Slope Stability")
    with st.expander("🎯 Acceleration at Peak Displacement", expanded=False):
        cols = st.columns(3)
        labels = ['Vertical', 'Longitudinal', 'Transversal']

        channel_colors = ['#00897B', '#E53935', '#5C6BC0']

        for i, (disp_col, accel_col) in enumerate(ACCEL_AT_PEAK_MAP.items()):
            if disp_col not in df.columns or accel_col not in df.columns:
                continue
            disp_sig = df[disp_col].values
            accel_sig = df[accel_col].values
            peak_val, peak_idx = peak_displacement(disp_sig)
            accel_val = acceleration_at_peak(accel_sig, peak_idx)
            accel_g = acceleration_in_g(accel_val)
            peak_time = time_axis[peak_idx]
            color = channel_colors[i]

            with cols[i]:
                st.markdown(f"**{labels[i]}**")
                st.metric("Peak Displacement", f"{abs(peak_val):.4f} mm")
                st.metric("Acceleration at Peak", f"{abs(accel_val):.2f} mm/s²")
                st.markdown(
                    f"<div style='margin-top:8px;'>"
                    f"<div style='font-size:12px;color:#888;margin-bottom:2px;'>Acceleration in g</div>"
                    f"<div style='display:flex;align-items:baseline;gap:4px;'>"
                    f"<div style='font-size:42px;font-weight:700;color:{color};line-height:1;'>"
                    f"{abs(accel_g):.4f}</div>"
                    f"<div style='font-size:20px;font-weight:600;color:{color};'>g</div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                st.caption(f"At t = {peak_time:.2f} ms")

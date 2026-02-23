# pages/overview.py
"""
Data Overview page — recording info, measurement summary, and waveforms.
"""

import streamlit as st
from core import calculate_frequency, detect_equipment_model
from core.metrics import peak_particle_velocity
from config import (
    VELOCITY_CHANNELS, SOUND_CHANNEL,
    FREQUENCY_METHODS, DEFAULT_FREQUENCY_METHOD,
    LOW_AMPLITUDE_THRESHOLD,
)


def render(df, time_axis, metadata, sampling_rate, make_chart_fn):
    st.title("📊 Data Overview")
    st.divider()

    # ── Recording Info ─────────────────────────────────────────────────────────
    st.markdown("## Recording Info")
    serial = metadata.get("Serial number", "")
    model = detect_equipment_model(serial)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Equipment Model", model)
        st.metric("Serial Number", serial or "N/A")
        st.caption(f"Calibrated: {metadata.get('Date of calibration', 'N/A')}")
    with col2:
        st.metric("Date & Time", metadata.get("Date & Time", "N/A"))
        st.metric("Duration", metadata.get("Time", "N/A"))
    with col3:
        st.metric("Sampling Rate", metadata.get("Sampling rate", "N/A"))
        st.metric("Pretrigger", metadata.get("Pretrigger", "N/A"))
    with col4:
        lon = metadata.get("Longitude", "Not set")
        lat = metadata.get("Latitude", "Not set")
        st.caption(f"GPS: {lat}, {lon}" if lon != "Not set" else "GPS: Not set")

    st.divider()

    # ── Measurement Summary ────────────────────────────────────────────────────
    with st.expander("📊 Measurement Summary", expanded=True):
        freq_method = st.selectbox(
            "Frequency calculation method",
            FREQUENCY_METHODS,
            index=FREQUENCY_METHODS.index(DEFAULT_FREQUENCY_METHOD)
        )

        # Low amplitude warning
        max_ppv = max(
            df[ch].abs().max()
            for ch in VELOCITY_CHANNELS.keys()
            if ch in df.columns
        )
        if max_ppv < LOW_AMPLITUDE_THRESHOLD:
            st.warning(
                f"⚠️ Low amplitude signal detected (PPV < {LOW_AMPLITUDE_THRESHOLD} mm/s). "
                "Frequency values may be less reliable due to noise influence."
            )

        s1, s2, s3, s4, s5 = st.columns(5)
        cols = [s1, s2, s3]
        labels = ['Vert', 'Long', 'Tran']

        for col, (ch, _), label in zip(cols, VELOCITY_CHANNELS.items(), labels):
            if ch not in df.columns:
                continue
            ppv = df[ch].abs().max()
            freq = calculate_frequency(tuple(df[ch].values), sampling_rate, freq_method)
            with col:
                st.metric(f"{label} Peak Particle Velocity", f"{ppv:.2f} mm/s")
                st.metric(f"{label} Frequency", f"{freq} Hz")

        # Peak Vector Sum
        if 'Vector sum 1 (mm/s)' in df.columns:
            s4.metric("Peak Vector Sum", f"{df['Vector sum 1 (mm/s)'].abs().max():.2f} mm/s")

        # Sound pressure
        if 'Channel 4 (Pa)' in df.columns:
            sound_freq = calculate_frequency(
                tuple(df['Channel 4 (Pa)'].values), sampling_rate, freq_method
            )
            s5.metric("Air Pressure", f"{df['Channel 4 (Pa)'].abs().max():.2f} Pa")
            s5.metric("Air Pressure Frequency", f"{sound_freq} Hz")

    st.divider()

    # ── Vibration Over Time ────────────────────────────────────────────────────
    with st.expander("📈 Vibration Over Time (Velocity)", expanded=True):
        display_cols = [c for c in VELOCITY_CHANNELS.keys() if c in df.columns]
        if 'Channel 4 (Pa)' in df.columns:
            display_cols.append('Channel 4 (Pa)')
        make_chart_fn(df, time_axis, display_cols)

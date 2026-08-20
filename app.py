import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO

from core.waveform import parse_sis_file, parse_file as _core_parse_file
from pages import report, ppv_analysis, monitoring, signal_analysis, sha, overview

st.set_page_config(page_title="Vibraport", layout="wide")

# ── Sidebar ────────────────────────────────────────────────────────────────────
# Initialize session state for file manager
if 'uploaded_files_dict' not in st.session_state:
    st.session_state.uploaded_files_dict = {}
if 'ppv_registry' not in st.session_state:
    st.session_state.ppv_registry = {}


@st.cache_data(show_spinner=False)
def _parse_uploaded_file(file_bytes: bytes, filename: str) -> tuple:
    """
    Parse a .sis or .csv file and return (metadata, df, time_axis, sampling_rate)
    with time_axis ALWAYS in milliseconds, regardless of source format.

    Cached on (file_bytes, filename) so re-parsing only happens when the
    active file actually changes, not on every widget interaction/rerun.

    NOTE: .sis parsing (core.waveform.parse_sis_file) returns time_axis in
    SECONDS by convention — pages/report.py compensates for this itself at
    each call site (time_axis * 1000). This wrapper normalizes it once, here,
    so every other page in app.py can assume milliseconds unconditionally.
    """
    if filename.lower().endswith('.sis'):
        metadata, df, time_axis, sampling_rate = parse_sis_file(file_bytes)
        time_axis = time_axis * 1000  # seconds -> milliseconds
        return metadata, df, time_axis, sampling_rate
    return _core_parse_file(file_bytes)


def _build_ppv_registry_entry(df) -> dict:
    def _maxabs(col):
        return float(round(df[col].abs().max(), 4))

    entry = {}
    if 'Vertical (mm/s)' in df.columns:
        entry['vert'] = _maxabs('Vertical (mm/s)')
    if 'Longitudinal (mm/s)' in df.columns:
        entry['long'] = _maxabs('Longitudinal (mm/s)')
    if 'Transversal (mm/s)' in df.columns:
        entry['tran'] = _maxabs('Transversal (mm/s)')
    if 'Vertical B2 (mm/s)' in df.columns:
        entry['vert_b2'] = _maxabs('Vertical B2 (mm/s)')
    if 'Longitudinal B2 (mm/s)' in df.columns:
        entry['long_b2'] = _maxabs('Longitudinal B2 (mm/s)')
    if 'Transversal B2 (mm/s)' in df.columns:
        entry['tran_b2'] = _maxabs('Transversal B2 (mm/s)')
    return entry

with st.sidebar:
    st.title("Vibraport")
    st.caption("Vibration Data Manager")
    st.divider()

    with st.expander("📁 Add Files", expanded=len(st.session_state.uploaded_files_dict) == 0):
        new_files = st.file_uploader(
            "Upload Vibracord files (.sis or .csv)",
            type=["sis", "csv"],
            accept_multiple_files=True,
        )
        if new_files:
            for f in new_files:
                if f.name not in st.session_state.uploaded_files_dict:
                    file_bytes = f.read()
                    st.session_state.uploaded_files_dict[f.name] = file_bytes
                    try:
                        _, fdf, _, _ = _parse_uploaded_file(file_bytes, f.name)
                        st.session_state.ppv_registry[f.name] = _build_ppv_registry_entry(fdf)
                    except Exception as e:
                        st.warning(f"Could not parse {f.name}: {e}")

    if st.session_state.uploaded_files_dict:
        selected_name = st.selectbox("Active file", list(st.session_state.uploaded_files_dict.keys()))

        from io import BytesIO
        selected_bytes = st.session_state.uploaded_files_dict[selected_name]
        uploaded_file = BytesIO(selected_bytes)
    else:
        uploaded_file = None

    st.divider()

    page = st.radio(
        "Navigate",
        [
            "📊 Data Overview",
            "📡 Signal Analysis",
            "💥 Signature Hole Analysis",
            "📈 Attenuation & Safe Zone",
            "📉 Bargraph Monitoring",
            "🖨️ Print Report",
        ],
    )

# calculate_frequency and make_chart (previously defined here) were only
# used by the inline Data Overview implementation below — removed along
# with it. core.fft_analysis.calculate_frequency is the shared version
# other pages (Signal Analysis, pages/overview.py) already import from
# `core`. Signal Analysis's stacked chart supersedes make_chart's role.


# ── No file uploaded ───────────────────────────────────────────────────────────
if not uploaded_file:
    st.title("Welcome to Vibraport")
    st.caption("Vibration Data Manager — powered by Vibracord .sis and CSV files")
    st.divider()

    st.markdown("""
    **Vibraport** is a vibration data analysis tool designed for **.sis** and CSV files exported 
    from **Vibracord** seismograph equipment. Built for engineers working with 
    blasting and vibration monitoring data.
    """)

    st.divider()

    st.subheader("📚 Features")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("### 📊 Data Overview")
        st.markdown("Recording info, per-channel/block measurement summary with transducer status, and SNI 7571:2023 compliance chart plotting this recording's PPV against building-class limit curves.")
        st.markdown("### 📡 Signal Analysis")
        st.markdown("Stacked seismogram view with dual-geophone (Block 2) support, device-reported frequency values, acceleration, displacement, and acceleration-at-peak-displacement for slope stability analysis.")
    with col2:
        st.markdown("### 💥 Signature Hole Analysis")
        st.markdown("Simulate full blast patterns using a single signature hole recording to find optimal timing delays, with optional USBM charge-weight/distance amplitude scaling.")
        st.markdown("### 📈 Attenuation & Safe Zone")
        st.markdown("Regress PPV against scaled distance across multiple blast events, then predict safe distance, max charge, or expected PPV — including SNI 7571 building-class compliance tables.")
    with col3:
        st.markdown("### 📉 Bargraph Monitoring")
        st.markdown("View long-term bargraph recordings (files ending in **M** before `.sis`) with configurable alert thresholds, exceedance markers, and frequency distribution.")
        st.markdown("### 🖨️ Print Report")
        st.markdown("Generate a formatted PDF-ready report from any uploaded recording.")

    st.divider()

    st.subheader("⚙️ Supported Equipment")
    st.markdown("""
    | Serial Prefix | Model |
    |---|---|
    | TE | Vibracord Tellus |
    | VG | Vibracord Gaia |
    | VB | Vibracord FX |
    | (number) | Vibracord DX |
    """)

    st.divider()
    st.info("👈 Upload a Vibracord .sis or CSV file from the sidebar to get started.")
    st.caption("Vibraport is an independent tool and is not affiliated with Vibracord or its manufacturers.")
    st.stop()

# ── Attenuation & Safe Zone doesn't need the active file's parsed waveform —
# it works from the registry of ALL uploaded files' peak values, so it's
# routed before parsing/gating on the currently active file.
if page == "📈 Attenuation & Safe Zone":
    ppv_analysis.render(st.session_state.uploaded_files_dict, st.session_state.ppv_registry)
    st.stop()

metadata, df, time_axis, sampling_rate = _parse_uploaded_file(selected_bytes, selected_name)
metadata['_filename'] = selected_name

# ── Bargraph ("M") files don't have velocity/accel/displacement waveform
# columns — only amplitude/frequency summaries per interval. Route them to
# the Bargraph Monitoring page regardless of which page is selected, rather
# than letting the waveform-only pages below crash on a missing column.
if not metadata.get('is_waveform', True) and page != "📉 Bargraph Monitoring":
    st.info(f"**{selected_name}** is a Bargraph recording, not a Waveform recording. Switch to **📉 Bargraph Monitoring** in the sidebar to view it.")
    st.stop()

if page == "📉 Bargraph Monitoring":
    # monitoring.py expects time_axis in raw seconds (bar_index * interval_seconds);
    # _parse_uploaded_file normalizes everything to milliseconds for the waveform
    # pages above, so convert back here.
    monitoring.render(df, time_axis / 1000, metadata, sampling_rate)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — DATA OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
# Previously an inline implementation lived here, independent of
# pages/overview.py (which existed but was never imported/called — the
# same dead-duplicate pattern found and fixed for SHA on 2026-08-20).
# pages/overview.py is the richer version — SIS/CSV-aware recording info,
# per-channel/block measurement table with transducer+test status, and
# the SNI 7571:2023 compliance chart, which the inline version never had.
if page == "📊 Data Overview":
    overview.render(df, time_axis, metadata, sampling_rate)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — SIGNAL ANALYSIS (stacked seismogram + Block 2 support)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📡 Signal Analysis":
    # signal_analysis.py expects time_axis in raw seconds; _parse_uploaded_file
    # normalizes to milliseconds for the other pages, so convert back here.
    signal_analysis.render(df, time_axis / 1000, sampling_rate, metadata=metadata)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — SIGNATURE HOLE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
# Previously an inline implementation lived here, independent of
# pages/sha.py (which existed but was never imported/called — a dead
# duplicate). Consolidated: pages/sha.py now contains the live logic
# (ported from this block) plus frequency-band analysis and USBM
# charge-weight/distance scaling, wrapped in the same st.form used here
# to avoid full-page reruns on every keystroke.
elif page == "💥 Signature Hole Analysis":
    sha.render(df, time_axis, sampling_rate)

elif page == "🖨️ Print Report":
    report.render(
        df,
        time_axis,
        metadata,
        sampling_rate,
        ppv_registry=st.session_state.ppv_registry,
        uploaded_files_dict=st.session_state.uploaded_files_dict,
    )

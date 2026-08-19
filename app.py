import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO

from core.waveform import parse_sis_file, parse_file as _core_parse_file
from pages import report, ppv_analysis, monitoring, signal_analysis

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


def _peak_vector_sum(df, metadata) -> float:
    for col in ('Vector sum 1 (mm/s)', 'Vector sum (mm/s)', 'Vector sum'):
        if col in df.columns:
            return float(df[col].abs().max())

    vector_sum = (metadata or {}).get('Vector sum') or {}
    for key in ('ch1_3', 'ch4_6'):
        val = vector_sum.get(key)
        if val is not None:
            return float(val)

    columns = [c for c in ('Vertical (mm/s)', 'Longitudinal (mm/s)', 'Transversal (mm/s)') if c in df.columns]
    if columns:
        return float(np.sqrt(sum(df[c].abs().max() ** 2 for c in columns)))

    return 0.0

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
            "📐 Math Analysis",
            "📡 Signal Analysis",
            "💥 Signature Hole Analysis",
            "📈 Attenuation & Safe Zone",
            "📉 Bargraph Monitoring",
            "🖨️ Print Report",
        ],
    )

def calculate_frequency(sig, sampling_rate, method):
    n = len(sig)
    if method == "Zero Crossing":
        zero_crossings = np.where(np.diff(np.sign(sig)))[0]
        return round((len(zero_crossings) / 2) / (n / sampling_rate), 2)
    else:
        fft_mag = np.abs(np.fft.rfft(sig))
        freqs = np.fft.rfftfreq(n, d=1/sampling_rate)
        energy = fft_mag ** 2
        cumulative_energy = np.cumsum(energy)
        total_energy = cumulative_energy[-1]
        if method == "FFT Peak":
            return round(freqs[np.argmax(fft_mag)], 2)
        elif method == "Energy 25%":
            return round(freqs[np.searchsorted(cumulative_energy, 0.25 * total_energy)], 2)
        elif method == "Energy 50%":
            return round(freqs[np.searchsorted(cumulative_energy, 0.50 * total_energy)], 2)
        elif method == "Energy 75%":
            return round(freqs[np.searchsorted(cumulative_energy, 0.75 * total_energy)], 2)

@st.fragment
def make_chart(df, time_axis, columns, title=""):
    """
    Reusable chart builder for any set of columns.

    Wrapped as a fragment: toggling a channel's Show/Hide checkbox only
    reruns this chart, not the whole page (which would otherwise re-run
    file parsing, all metric calculations, and every other chart above it).
    """
    channel_cols = [c for c in columns if c in df.columns]

    st.write("Show/Hide:")
    check_cols = st.columns(len(channel_cols))
    visible = []
    for i, col in enumerate(channel_cols):
        with check_cols[i]:
            visible.append(st.checkbox(col, value=True, key=f"cb_{col}"))

    active = [col for col, show in zip(channel_cols, visible) if show]

    if not active:
        st.info("Select at least one channel to display.")
        return

    fig = make_subplots(
        rows=len(active), cols=1,
        shared_xaxes=True,
        subplot_titles=active,
        vertical_spacing=0.06
    )

    color_map = {
        'Vertical (mm/s)':   '#00897B',
        'Longitudinal (mm/s)': '#E53935',
        'Transversal (mm/s)': '#5C6BC0',
        'A_Vert (mm/s²)':    '#00897B',
        'A_Long (mm/s²)':    '#E53935',
        'A_Tran (mm/s²)':    '#5C6BC0',
        'D_Vert (mm)':       '#00897B',
        'D_Long (mm)':       '#E53935',
        'D_Tran (mm)':       '#5C6BC0',
        'Channel 4 (Pa)':    '#FFB300',
    }

    for i, col in enumerate(active):
        color = color_map.get(col, '#888888')
        fig.add_trace(
            go.Scatter(x=time_axis, y=df[col], name=col, mode='lines',
                       line=dict(color=color)),
            row=i+1, col=1
        )
        peak_idx = df[col].abs().idxmax()
        peak_time = time_axis[peak_idx]
        peak_val = df[col][peak_idx]
        fig.add_trace(
            go.Scatter(
                x=[peak_time], y=[peak_val],
                mode='markers+text',
                marker=dict(color='red', size=10, symbol='square',
                            line=dict(color='black', width=1.5)),
                text=[f" {peak_val:.2f}"],
                textposition='middle right',
                textfont=dict(size=14, color='red'),
                name=f"{col} peak",
                showlegend=True
            ),
            row=i+1, col=1
        )

    max_time = time_axis[-1]
    tick_positions = [i * 100 for i in range(int(max_time / 100) + 2)]

    fig.update_xaxes(
        tickvals=tick_positions,
        ticktext=[f"{t:.0f}" for t in tick_positions],
        title_text="Time (ms)",
        tickfont=dict(size=13),
        title_font=dict(size=15),
        row=len(active), col=1
    )
    fig.update_yaxes(tickfont=dict(size=12), title_font=dict(size=13))
    fig.update_layout(
        height=400 * len(active),
        hovermode="x unified",
        showlegend=False,
        font=dict(size=14),
        margin=dict(t=120, b=60, l=60, r=40),
    )
    for annotation in fig.layout.annotations:
        annotation.update(font=dict(size=18, color="black",
                                    family="Arial Black, Arial, sans-serif"))

    st.plotly_chart(fig, use_container_width=True)


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
        st.markdown("View recording info, peak particle velocity, dominant frequency, and raw waveforms.")
        st.markdown("### 📐 Math Analysis")
        st.markdown("Derive acceleration and displacement, analyze frequency spectrum, and inspect peak values.")
    with col2:
        st.markdown("### 📡 Signal Analysis")
        st.markdown("Stacked seismogram view with dual-geophone (Block 2) support, device-reported frequency values, and acceleration-at-peak-displacement for slope stability analysis.")
        st.markdown("### 💥 Signature Hole Analysis")
        st.markdown("Simulate full blast patterns using a single signature hole recording to find optimal timing delays.")
    with col3:
        st.markdown("### 📈 Attenuation & Safe Zone")
        st.markdown("Regress PPV against scaled distance across multiple blast events, then predict safe distance, max charge, or expected PPV — including SNI 7571 building-class compliance tables.")
        st.markdown("### 📉 Bargraph Monitoring")
        st.markdown("View long-term bargraph recordings (files ending in **M** before `.sis`) with configurable alert thresholds, exceedance markers, and frequency distribution.")
        st.markdown("### 🖨️ Print Report")
        st.markdown("Generate a formatted PDF-ready report from any uploaded recording.")

    st.divider()
    st.caption("📐 Math Analysis and 📡 Signal Analysis currently overlap in purpose (frequency + acceleration + displacement). Signal Analysis is the newer version — it adds dual-geophone support and uses device-reported frequency values. Kept both for now; consolidating is a planned cleanup.")

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

velocity_cols = ['Vertical (mm/s)', 'Longitudinal (mm/s)', 'Transversal (mm/s)']
accel_cols    = ['A_Vert (mm/s²)', 'A_Long (mm/s²)', 'A_Tran (mm/s²)']
disp_cols     = ['D_Vert (mm)', 'D_Long (mm)', 'D_Tran (mm)']
accel_at_peak_map = {
    'D_Vert (mm)': 'A_Vert (mm/s²)',
    'D_Long (mm)': 'A_Long (mm/s²)',
    'D_Tran (mm)': 'A_Tran (mm/s²)',
}


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — DATA OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Data Overview":
    st.title("📊 Data Overview")
    st.divider()

    # Recording Info
    st.markdown("## Recording Info")
    serial = metadata.get("Serial number", "")
    if serial.startswith("TE"):
        model = "Vibracord Tellus"
    elif serial.startswith("VG"):
        model = "Vibracord Gaia"
    elif serial.startswith("VB"):
        model = "Vibracord FX"
    else:
        model = "Vibracord DX"
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Equipment Model", model)
        st.metric("Serial Number", metadata.get("Serial number", "N/A"))
        st.caption(f"Calibrated: {metadata.get('Date of calibration', 'N/A')}")
    with col2:
        st.metric("Date & Time", metadata.get("Date & Time", "N/A"))
        st.metric("Duration", metadata.get("Time", "N/A"))
    with col3:
        st.metric("Sampling Rate", metadata.get("Sampling rate", "N/A"))
        st.metric("Pretrigger", metadata.get("Pretrigger", "N/A"))
    with col4:
        loc = metadata.get("Longitude", "Not set")
        lat = metadata.get("Latitude", "Not set")
        st.caption(f"GPS: {lat}, {loc}" if loc != "Not set" else "GPS: Not set")

    st.divider()

    # Measurement Summary
    with st.expander("📊 Measurement Summary", expanded=True):
        freq_method = st.selectbox(
            "Frequency calculation method",
            ["Zero Crossing", "FFT Peak", "Energy 25%", "Energy 50%", "Energy 75%"],
            index=3
        )

        s1, s2, s3, s4, s5 = st.columns(5)

        for col, ch, label in zip(
            [s1, s2, s3],
            ['Vertical (mm/s)', 'Longitudinal (mm/s)', 'Transversal (mm/s)'],
            ['Vert', 'Long', 'Tran']
        ):
            ppv = df[ch].abs().max()
            freq = calculate_frequency(df[ch].values, sampling_rate, freq_method)
            with col:
                st.metric(f"{label} Peak Particle Velocity", f"{ppv:.2f} mm/s")
                st.metric(f"{label} Frequency", f"{freq} Hz")

        s4.metric("Peak Vector Sum", f"{_peak_vector_sum(df, metadata):.2f} mm/s")
        if 'Channel 4 (Pa)' in df.columns:
            s5.metric("Sound Pressure", f"{df['Channel 4 (Pa)'].abs().max():.2f} Pa")
        else:
            s5.metric("Sound Pressure", "—")

    st.divider()

    # Velocity graphs
    with st.expander("📈 Vibration Over Time (Velocity)", expanded=True):
        default_cols = [c for c in velocity_cols if c in df.columns] + ['Channel 4 (Pa)']
        make_chart(df, time_axis, default_cols)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📐 Math Analysis":
    st.title("📐 Math Analysis")
    st.divider()

    with st.expander("📡 Frequency Analysis", expanded=True):
        st.subheader("Frequency Results")

        freq_channels = {
            'Vertical (mm/s)': '#00897B',
            'Longitudinal (mm/s)': '#E53935',
            'Transversal (mm/s)': '#5C6BC0',
        }

        results_freq = {}

        for ch, color in freq_channels.items():
            sig = df[ch].values
            n = len(sig)

            # FFT
            fft_vals = np.fft.rfft(sig)
            fft_mag = np.abs(np.fft.rfft(sig)) / n
            freqs = np.fft.rfftfreq(n, d=1/sampling_rate)

            # FFT Peak
            fft_peak_freq = freqs[np.argmax(fft_mag)]

            # Zero Crossing
            zero_crossings = np.where(np.diff(np.sign(sig)))[0]
            zc_freq = (len(zero_crossings) / 2) / (n / sampling_rate)

            # Energy Spectrum percentiles
            energy = fft_mag ** 2
            cumulative_energy = np.cumsum(energy)
            total_energy = cumulative_energy[-1]
            freq_25 = freqs[np.searchsorted(cumulative_energy, 0.25 * total_energy)]
            freq_50 = freqs[np.searchsorted(cumulative_energy, 0.50 * total_energy)]
            freq_75 = freqs[np.searchsorted(cumulative_energy, 0.75 * total_energy)]

            results_freq[ch] = {
                'Zero Crossing (Hz)': round(zc_freq, 2),
                'FFT Peak (Hz)': round(fft_peak_freq, 2),
                'Energy 25% (Hz)': round(freq_25, 2),
                'Energy 50% (Hz)': round(freq_50, 2),
                'Energy 75% (Hz)': round(freq_75, 2),
            }

        # Display table
        freq_df = pd.DataFrame(results_freq).T
        st.dataframe(freq_df, use_container_width=True)

        st.divider()

        # FFT Spectrum chart
        st.subheader("FFT Spectrum")
        fig_fft = go.Figure()
        for ch, color in freq_channels.items():
            sig = df[ch].values
            n = len(sig)
            fft_mag = np.abs(np.fft.rfft(sig))
            freqs = np.fft.rfftfreq(n, d=1/sampling_rate)
            fig_fft.add_trace(go.Scatter(
                x=freqs, y=fft_mag,
                name=ch, mode='lines',
                line=dict(color=color)
            ))

        fig_fft.update_layout(
            xaxis_title="Frequency (Hz)",
            yaxis_title="Amplitude",
            height=400,
            hovermode="x unified",
            xaxis=dict(range=[0, 200])  # limit to 0-200 Hz, relevant range
        )
        st.plotly_chart(fig_fft, use_container_width=True)

    # Acceleration graphs
    with st.expander("⚡ Acceleration", expanded=False):
        st.subheader("Acceleration")
        make_chart(df, time_axis, accel_cols)

    # Displacement graphs
    with st.expander("📏 Displacement", expanded=False):
        st.subheader("Displacement")
        make_chart(df, time_axis, disp_cols)

    # Acceleration at peak displacement
    with st.expander("🎯 Acceleration at Peak Displacement", expanded=False):
        if st.button("Analyze Peak Displacement", key="btn_peak"):
            st.session_state['show_peak'] = True
        if st.session_state.get('show_peak'):
            c1, c2, c3 = st.columns(3)
            for i, (disp_col, accel_col) in enumerate(accel_at_peak_map.items()):
                peak_idx = df[disp_col].abs().idxmax()
                peak_time = time_axis[peak_idx]
                peak_disp = df[disp_col][peak_idx]
                accel_at_peak = df[accel_col][peak_idx]
                accel_at_peak_g = accel_at_peak / 9806.65
                axis_name = disp_col.split('_')[1].split(' ')[0]
                with [c1, c2, c3][i]:
                    st.metric(f"{axis_name}. Peak Displacement", f"{abs(peak_disp):.3f} mm")
                    st.metric(f"{axis_name}. Acceleration at Peak Displacement", f"{abs(accel_at_peak):.1f} mm/s²")
                    st.metric(f"which is", f"= {abs(accel_at_peak_g):.3f} g")
                    st.caption(f"Occurs at t = {peak_time:.1f} ms")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2.5 — SIGNAL ANALYSIS (stacked seismogram + Block 2 support)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📡 Signal Analysis":
    # signal_analysis.py expects time_axis in raw seconds; _parse_uploaded_file
    # normalizes to milliseconds for the other pages, so convert back here.
    signal_analysis.render(df, time_axis / 1000, sampling_rate, metadata=metadata)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — SIGNATURE HOLE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💥 Signature Hole Analysis":
    st.title("💥 Signature Hole Analysis")
    st.caption("Simulate blast timing combinations using the uploaded signature hole waveform.")
    st.divider()

    # ── STEP 1 ────────────────────────────────────────────────────────────────
    st.markdown("## Step 1 — Truncate the Waveform")
    trunc_method = st.radio(
        "Select truncation method",
        ["✏️ Type start & end time manually", "🖱️ Select visually on the graph"],
        horizontal=True
    )

    if trunc_method == "✏️ Type start & end time manually":
        tc1, tc2 = st.columns(2)
        t_start = tc1.number_input("Start Time (ms)", min_value=0.0, max_value=float(time_axis[-1]), value=0.0, step=0.5)
        t_end = tc2.number_input("End Time (ms)", min_value=0.0, max_value=float(time_axis[-1]), value=float(time_axis[-1]), step=0.5)
    else:
        st.caption("Use the slider below to select the waveform window.")
        time_step = 1000 / sampling_rate
        t_start, t_end = st.slider(
            "Select time window (ms)",
            min_value=float(time_axis[0]),
            max_value=float(time_axis[-1]),
            value=(float(time_axis[0]), float(time_axis[-1])),
            step=float(time_step),
        )

    start_idx = next(i for i, t in enumerate(time_axis) if t >= t_start)
    end_idx = next((i for i, t in enumerate(time_axis) if t >= t_end), len(time_axis) - 1)
    truncated_time = time_axis[start_idx:end_idx]

    trunc_channels = {
        'Vertical (mm/s)': '#00897B',
        'Longitudinal (mm/s)': '#E53935',
        'Transversal (mm/s)': '#5C6BC0',
    }

    fig_trunc = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        subplot_titles=list(trunc_channels.keys()),
        vertical_spacing=0.08
    )
    for i, (ch, color) in enumerate(trunc_channels.items()):
        fig_trunc.add_trace(
            go.Scatter(
                x=truncated_time,
                y=df[ch].values[start_idx:end_idx],
                mode='lines',
                line=dict(color=color),
                showlegend=False
            ),
            row=i+1, col=1
        )
    fig_trunc.update_layout(height=600, margin=dict(t=50, b=50), hovermode="x unified")
    for annotation in fig_trunc.layout.annotations:
        annotation.update(font=dict(size=15, color="black", family="Arial Black, Arial, sans-serif"))
    st.plotly_chart(fig_trunc, use_container_width=True)
    st.caption(f"Selected window: {t_start} ms to {t_end} ms — {len(truncated_time)} data points")

    st.divider()

    # ── STEP 2 + 3 ────────────────────────────────────────────────────────────
    # Wrapped in st.form: none of these 10 inputs trigger a rerun (or re-render
    # Step 1's truncation chart above) until "Run Simulation" is pressed. Only
    # the submit button reruns the script — this is the single biggest rerun
    # cost on this page since Step 1's chart was previously rebuilding on every
    # keystroke in any of these fields.
    st.markdown("## Step 2 — Blast Design Parameters")
    with st.form("sha_blast_params_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**Deck Configuration**")
            num_decks = st.number_input("Number of Decks per Hole", min_value=1, max_value=10, value=1)
            deck_delay = st.number_input("Inter-Deck Delay (ms)", min_value=0, max_value=500, value=0)

        with col2:
            st.markdown("**Row Configuration**")
            num_rows = st.number_input("Number of Rows", min_value=1, max_value=20, value=1)
            row_delay_start = st.number_input("Inter-Row Delay Start (ms)", min_value=0, max_value=500, value=20)
            row_delay_end = st.number_input("Inter-Row Delay End (ms)", min_value=0, max_value=500, value=150)
            row_delay_increment = st.number_input("Inter-Row Delay Increment (ms)", min_value=1, max_value=100, value=1)

        with col3:
            st.markdown("**Hole Configuration**")
            num_holes = st.number_input("Number of Holes per Row", min_value=1, max_value=50, value=5)
            hole_delay_start = st.number_input("Inter-Hole Delay Start (ms)", min_value=0, max_value=500, value=20)
            hole_delay_end = st.number_input("Inter-Hole Delay End (ms)", min_value=0, max_value=500, value=150)
            hole_delay_increment = st.number_input("Inter-Hole Delay Increment (ms)", min_value=1, max_value=100, value=1)

        hole_combos = len(range(hole_delay_start, hole_delay_end + 1, hole_delay_increment))
        row_combos = len(range(row_delay_start, row_delay_end + 1, row_delay_increment))
        total_combos = hole_combos * row_combos
        st.caption(f"Will simulate **{hole_combos}** inter-hole delays × **{row_combos}** inter-row delays = **{total_combos:,}** total combinations. (Updates after you press Run — form inputs don't trigger live reruns.)")

        st.divider()
        st.markdown("## Step 3 — Run the Simulation")
        simulate_btn = st.form_submit_button("▶ Run Simulation", type="primary")

    if simulate_btn:
        samples_per_ms = sampling_rate / 1000
        channels = {
            'Vert': df['Vertical (mm/s)'].values[start_idx:end_idx],
            'Long': df['Longitudinal (mm/s)'].values[start_idx:end_idx],
            'Tran': df['Transversal (mm/s)'].values[start_idx:end_idx],
        }
        hole_delays = range(hole_delay_start, hole_delay_end + 1, hole_delay_increment)
        row_delays = range(row_delay_start, row_delay_end + 1, row_delay_increment)
        results = []
        progress = st.progress(0, text="Running simulation...")
        count = 0

        for hd in hole_delays:
            for rd in row_delays:
                max_delay_samples = int((
                    (num_holes - 1) * hd +
                    (num_rows - 1) * rd +
                    (num_decks - 1) * deck_delay
                ) * samples_per_ms)
                sig_len = len(channels['Vert'])
                total_len = sig_len + max_delay_samples + 1
                ppv = {}
                for ch_name, sig in channels.items():
                    combined = np.zeros(total_len)
                    for row in range(num_rows):
                        for hole in range(num_holes):
                            for deck in range(num_decks):
                                delay_ms = (hole * hd) + (row * rd) + (deck * deck_delay)
                                delay_samples = int(delay_ms * samples_per_ms)
                                combined[delay_samples:delay_samples + sig_len] += sig
                    ppv[ch_name] = np.abs(combined).max()

                vector_sum = np.sqrt(ppv['Vert']**2 + ppv['Long']**2 + ppv['Tran']**2)
                results.append({
                    'Hole Delay (ms)': hd,
                    'Row Delay (ms)': rd,
                    'PPV Vert (mm/s)': round(ppv['Vert'], 2),
                    'PPV Long (mm/s)': round(ppv['Long'], 2),
                    'PPV Tran (mm/s)': round(ppv['Tran'], 2),
                    'Peak Vector Sum (mm/s)': round(vector_sum, 2),
                })
                count += 1
                progress.progress(count / total_combos, text=f"Running simulation... {count}/{total_combos}")

        progress.empty()
        results_df = pd.DataFrame(results)
        best_idx = results_df['Peak Vector Sum (mm/s)'].idxmin()

        st.success(f"✅ Simulation complete! Best combination: Hole Delay = {results_df.loc[best_idx, 'Hole Delay (ms)']} ms, Row Delay = {results_df.loc[best_idx, 'Row Delay (ms)']} ms — Peak Vector Sum = {results_df.loc[best_idx, 'Peak Vector Sum (mm/s)']} mm/s")

        def highlight_best(row):
            if row.name == best_idx:
                return ['background-color: #c8e6c9'] * len(row)
            return [''] * len(row)

        st.subheader("Simulation Results")
        st.dataframe(
            results_df.style.apply(highlight_best, axis=1),
            use_container_width=True
        )

elif page == "🖨️ Print Report":
    report.render(
        df,
        time_axis,
        metadata,
        sampling_rate,
        ppv_registry=st.session_state.ppv_registry,
        uploaded_files_dict=st.session_state.uploaded_files_dict,
    )


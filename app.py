# app.py
"""
Vibraport — entry point.
Handles sidebar, file management, and page routing.
"""

import streamlit as st
from io import BytesIO
from core.waveform import parse_file, parse_sis_file
from pages import overview, signal_analysis, sha, ppv_analysis, monitoring
from config import VELOCITY_CHANNELS


st.set_page_config(page_title="Vibraport", layout="wide")


def _parse_uploaded_file(file_bytes: bytes, filename: str) -> tuple:
    """
    Route to the correct parser based on file extension.
    Returns (metadata, df, time_axis, sampling_rate).
    """
    if filename.lower().endswith('.sis'):
        return parse_sis_file(file_bytes)
    else:
        return parse_file(file_bytes)


def _build_ppv_registry_entry(df, metadata: dict) -> dict:
    """
    Extract PPV values for the PPV Analysis page registry.
    Handles both single-block and dual-block recordings.
    """
    def _maxabs(col):
        return float(round(df[col].abs().max(), 4))

    entry = {}
    # Block 1 (always present)
    if 'Vertical (mm/s)'     in df.columns: entry['vert'] = _maxabs('Vertical (mm/s)')
    if 'Longitudinal (mm/s)' in df.columns: entry['long'] = _maxabs('Longitudinal (mm/s)')
    if 'Transversal (mm/s)'  in df.columns: entry['tran'] = _maxabs('Transversal (mm/s)')
    # Block 2 (dual-block .sis files only)
    if 'Vertical B2 (mm/s)'     in df.columns: entry['vert_b2'] = _maxabs('Vertical B2 (mm/s)')
    if 'Longitudinal B2 (mm/s)' in df.columns: entry['long_b2'] = _maxabs('Longitudinal B2 (mm/s)')
    if 'Transversal B2 (mm/s)'  in df.columns: entry['tran_b2'] = _maxabs('Transversal B2 (mm/s)')
    return entry
st.markdown("""
    <style>
        [data-testid="stSidebarNav"] { display: none; }
        button[data-testid="stNumberInputStepDown"],
        button[data-testid="stNumberInputStepUp"],
        button[data-testid="stNumberInputClear"] {
            display: none !important;
        }
    </style>
""", unsafe_allow_html=True)


# ── Chart builder ──────────────────────────────────────────────────────────────
def make_chart(df, time_axis, columns):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

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

    color_map = {
        'Vertical (mm/s)':     '#00897B',
        'Longitudinal (mm/s)': '#E53935',
        'Transversal (mm/s)':  '#5C6BC0',
        'A_Vert (mm/s²)':      '#00897B',
        'A_Long (mm/s²)':      '#E53935',
        'A_Tran (mm/s²)':      '#5C6BC0',
        'D_Vert (mm)':         '#00897B',
        'D_Long (mm)':         '#E53935',
        'D_Tran (mm)':         '#5C6BC0',
        'Channel 4 (Pa)':      '#FFB300',
    }

    fig = make_subplots(
        rows=len(active), cols=1,
        shared_xaxes=True,
        subplot_titles=active,
        vertical_spacing=0.06
    )

    for i, col in enumerate(active):
        color = color_map.get(col, '#888888')
        fig.add_trace(
            go.Scatter(x=time_axis, y=df[col], name=col,
                       mode='lines', line=dict(color=color)),
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
                showlegend=False,
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


# ── Session state ──────────────────────────────────────────────────────────────
if 'uploaded_files_dict' not in st.session_state:
    st.session_state.uploaded_files_dict = {}
if 'ppv_registry' not in st.session_state:
    st.session_state.ppv_registry = {}


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Vibraport")
    st.caption("Vibration Data Manager")
    st.divider()

    with st.expander("📁 Add Files",
                     expanded=len(st.session_state.uploaded_files_dict) == 0):
        new_files = st.file_uploader(
            "Upload Vibracord files (.sis or .csv)",
            type=["sis", "csv"],
            accept_multiple_files=True
        )
        if new_files:
            for f in new_files:
                if f.name not in st.session_state.uploaded_files_dict:
                    file_bytes = f.read()
                    st.session_state.uploaded_files_dict[f.name] = file_bytes
                    try:
                        _, fdf, _, _ = _parse_uploaded_file(file_bytes, f.name)
                        st.session_state.ppv_registry[f.name] = _build_ppv_registry_entry(fdf, {})
                    except Exception as e:
                        st.warning(f"Could not parse {f.name}: {e}")

    if st.session_state.uploaded_files_dict:
        selected_name = st.selectbox(
            "Active file",
            list(st.session_state.uploaded_files_dict.keys())
        )
        selected_bytes = st.session_state.uploaded_files_dict[selected_name]
    else:
        selected_bytes = None

    st.divider()
    # Detect record type from byte 0x09 — no full parse needed
    is_bargraph = False
    if selected_bytes and selected_name.endswith('.sis') and len(selected_bytes) > 0x2D:
        equip = selected_bytes[0x2C]
        rec   = selected_bytes[0x09]
        is_bargraph = (rec != 0) if equip == 3 else (rec != 1)

    if is_bargraph:
        page = st.radio("Navigate", [
            "📊 Bargraph Monitoring",
        ])
    else:
        page = st.radio("Navigate", [
            "📊 Data Overview",
            "📡 Signal Analysis",
            "💥 Signature Hole Analysis",
            "📈 Attenuation & Safe Zone",
        ])


# ── Welcome screen ─────────────────────────────────────────────────────────────
if not selected_bytes:
    st.title("Welcome to Vibraport")
    st.caption("Vibration Data Manager — powered by Vibracord .sis files")
    st.divider()
    st.markdown("""
    **Vibraport** is a vibration data analysis tool designed for **.sis files**
    from **Vibracord** seismograph equipment. Built for engineers working with
    blasting and vibration monitoring data.
    """)
    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown("### 📊 Data Overview")
        st.markdown("View recording info, PPV, dominant frequency, and raw waveforms.")
    with col2:
        st.markdown("### 📡 Signal Analysis")
        st.markdown("Derive acceleration and displacement, analyze frequency spectrum.")
    with col3:
        st.markdown("### 💥 Signature Hole Analysis")
        st.markdown("Simulate full blast patterns to find optimal timing delays.")
    with col4:
        st.markdown("### 📈 Attenuation & Safe Zone")
        st.markdown("Regression analysis and safe zone prediction based on SNI 7571.")
    with col5:
        st.markdown("### 📊 Bargraph Monitoring")
        st.markdown("A page for bargraph mode monitoring with speacilized overview.")
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
    st.info("👈 Upload a Vibracord .sis file from the sidebar to get started.")
    st.caption("Vibraport is an independent tool and is not affiliated with Vibracord or its manufacturers.")
    st.stop()


# ── Parse active file ──────────────────────────────────────────────────────────
metadata, df, time_axis, sampling_rate = _parse_uploaded_file(selected_bytes, selected_name)
metadata['_filename'] = selected_name


# ── Page routing ───────────────────────────────────────────────────────────────
if page == "📊 Data Overview":
    overview.render(df, time_axis, metadata, sampling_rate)

elif page == "📡 Signal Analysis":
    signal_analysis.render(df, time_axis, sampling_rate, make_chart, metadata)

elif page == "💥 Signature Hole Analysis":
    sha.render(df, time_axis, sampling_rate)

elif page == "📈 Attenuation & Safe Zone":
    ppv_analysis.render(
        st.session_state.uploaded_files_dict,
        st.session_state.ppv_registry,
    )

elif page == "📊 Bargraph Monitoring":
    monitoring.render(df, time_axis, metadata, sampling_rate)

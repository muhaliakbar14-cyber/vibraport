# pages/overview.py
"""
Data Overview page — recording info, measurement summary table, and waveform chart.
"""

import streamlit as st
import pandas as pd
from core import calculate_frequency, detect_equipment_model
from core.sni_chart import build_sni_chart
from config import (
    FREQUENCY_METHODS, DEFAULT_FREQUENCY_METHOD,
    LOW_AMPLITUDE_THRESHOLD,
)

def render(df, time_axis, metadata, sampling_rate, make_chart_fn=None):
    st.title("📊 Data Overview")
    st.divider()

    is_sis = metadata.get('is_sis', False)

    if is_sis:
        _render_sis_recording_info(metadata)
    else:
        _render_csv_recording_info(metadata)

    st.divider()

    # ── Measurement Summary Table ──────────────────────────────────────────────
    st.markdown("## Measurement Summary")
    filename = metadata.get('_filename', metadata.get('Serial number', 'Recording'))
    with st.expander(f"📊 {filename}", expanded=True):
        freq_method = st.selectbox(
            "Frequency calculation method",
            FREQUENCY_METHODS,
            index=FREQUENCY_METHODS.index(DEFAULT_FREQUENCY_METHOD)
        )

        table_rows = _build_summary_rows(df, time_axis, sampling_rate, freq_method, metadata)

        if table_rows:
            summary_df = pd.DataFrame(table_rows)

            st.dataframe(
                summary_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'Channel':    st.column_config.TextColumn('Channel'),
                    'Block':      st.column_config.TextColumn('Block'),
                    'PPV':        st.column_config.TextColumn('PPV'),
                    'Frequency':  st.column_config.TextColumn('Frequency'),
                    'Transducer': st.column_config.TextColumn('Transducer'),
                    'Test':       st.column_config.TextColumn('Test'),
                }
            )

            # ── Vector Sum summary line below table ────────────────────────────
            vector_sum = metadata.get('Vector sum', {})
            pvs_parts = []
            pvs_b1 = vector_sum.get('ch1_3')
            pvs_b2 = vector_sum.get('ch4_6')
            if pvs_b1 and pvs_b1 > 0:
                pvs_parts.append(f"Block 1 = **{pvs_b1:.2f} mm/s**")
            if pvs_b2 and pvs_b2 > 0:
                pvs_parts.append(f"Block 2 = **{pvs_b2:.2f} mm/s**")
            if pvs_parts:
                st.caption("Peak Vector Sum:  " + "    |    ".join(pvs_parts))

    # ── SNI 7571:2023 Compliance Chart — waveform only ───────────────────────
    if metadata.get('is_waveform', True):
        st.divider()
        st.markdown("## SNI 7571:2023 Compliance")
        with st.expander("📈 Compliance Chart", expanded=True):
            _render_sni_chart(df, time_axis, sampling_rate, metadata)




# ── Recording Info renderers ───────────────────────────────────────────────────

def _render_sis_recording_info(metadata):
    st.markdown("## Recording Info")
    serial = metadata.get('Serial number', '')
    model  = detect_equipment_model(serial)

    # ── Primary fields — always visible ───────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Equipment", model)
        st.metric("Serial Number", serial or "N/A")
    with c2:
        st.metric("Date", metadata.get('Date', 'N/A'))
        st.metric("Record Type", metadata.get('Record type', 'N/A'))
    with c3:
        st.metric("Time", metadata.get('Time', 'N/A'))
        st.metric("Record Length", metadata.get('Record length', 'N/A'))
    with c4:
        st.metric("Sampling Rate", metadata.get('Sampling rate', 'N/A'))
        st.metric("Pretrigger", metadata.get('Pretrigger', 'N/A'))


    # ── Secondary fields — collapsed by default ────────────────────────────────
    with st.expander("More Details", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Calibration Date", metadata.get('Calibration date', 'N/A'))
        with c2:
            st.metric("Clock Source", metadata.get('Clock source', 'N/A'))
            gps_source = metadata.get('GPS source', 'Not set')
            lat = metadata.get('Latitude')
            lon = metadata.get('Longitude')
            st.metric("GPS Source", gps_source)
            if gps_source != 'Not set' and lat is not None:
                st.metric("Coordinates", f"{lat:.6f}, {lon:.6f}")
        with c3:
            notes = [metadata.get(f'Note {i}', '') for i in range(1, 4)]
            for i, note in enumerate(notes, 1):
                st.metric(f"Note {i}", note if note else "—")


def _render_csv_recording_info(metadata):
    st.markdown("## Recording Info")
    serial = metadata.get("Serial number", "")
    model  = detect_equipment_model(serial)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Equipment Model", model)
        st.metric("Serial Number", serial or "N/A")
        st.caption(f"Calibrated: {metadata.get('Date of calibration', 'N/A')}")
    with c2:
        st.metric("Date & Time", metadata.get("Date & Time", "N/A"))
        st.metric("Duration", metadata.get("Time", "N/A"))
    with c3:
        st.metric("Sampling Rate", metadata.get("Sampling rate", "N/A"))
        st.metric("Pretrigger", metadata.get("Pretrigger", "N/A"))
    with c4:
        lon = metadata.get("Longitude")
        lat = metadata.get("Latitude")
        st.caption(f"GPS: {lat}, {lon}" if lon and lat else "GPS: Not set")


# ── Summary table builder ──────────────────────────────────────────────────────

def _build_summary_rows(df, time_axis, sampling_rate, freq_method, metadata):
    """
    Build rows for the measurement summary table.
    Each row = one channel (velocity axis, pressure, or KBf).
    Columns: Channel, Block, PPV, Frequency, Peak Vector Sum, Transducer, Test
    """
    rows = []
    is_sis = metadata.get('is_sis', False)
    channel_info = metadata.get('Channel info', [])
    geophone_test = metadata.get('Geophone test', [])  # 7 physical channels
    vector_sum = metadata.get('Vector sum', {})

    # Build a lookup from channel index to channel_info
    ch_lookup = {ch['index']: ch for ch in channel_info} if channel_info else {}

    # ── Velocity channels — Block 1 ───────────────────────────────────────────
    b1_map = {
        'Vertical (mm/s)':     ('Vertical',     1),
        'Longitudinal (mm/s)': ('Longitudinal', 1),
        'Transversal (mm/s)':  ('Transversal',  1),
    }
    for col, (axis_label, block) in b1_map.items():
        if col not in df.columns:
            continue
        ppv  = df[col].abs().max()
        freq = calculate_frequency(tuple(df[col].values), sampling_rate, freq_method)
        ch_idx = _find_channel_index(ch_lookup, axis_label, block=1)
        transducer, test = _get_transducer_info(ch_idx, ch_lookup, geophone_test)
        warn = ' ⚠️' if ppv < LOW_AMPLITUDE_THRESHOLD else ''
        rows.append({
            'Channel':    axis_label,
            'Block':      '1',
            'PPV':        f"{ppv:.2f} mm/s{warn}",
            'Frequency':  f"{freq} Hz",
            'Transducer': transducer,
            'Test':       test,
        })

    # ── Velocity channels — Block 2 ───────────────────────────────────────────
    b2_map = {
        'Vertical B2 (mm/s)':     ('Vertical',     2),
        'Longitudinal B2 (mm/s)': ('Longitudinal', 2),
        'Transversal B2 (mm/s)':  ('Transversal',  2),
    }
    for col, (axis_label, block) in b2_map.items():
        if col not in df.columns:
            continue
        ppv  = df[col].abs().max()
        freq = calculate_frequency(tuple(df[col].values), sampling_rate, freq_method)
        ch_idx = _find_channel_index(ch_lookup, axis_label, block=2)
        transducer, test = _get_transducer_info(ch_idx, ch_lookup, geophone_test)
        warn = ' ⚠️' if ppv < LOW_AMPLITUDE_THRESHOLD else ''
        rows.append({
            'Channel':    axis_label,
            'Block':      '2',
            'PPV':        f"{ppv:.2f} mm/s{warn}",
            'Frequency':  f"{freq} Hz",
            'Transducer': transducer,
            'Test':       test,
        })

    # ── Pressure channel ──────────────────────────────────────────────────────
    pa_col = next((c for c in df.columns if '(Pa)' in c), None)
    if pa_col:
        ppv  = df[pa_col].abs().max()
        freq = calculate_frequency(tuple(df[pa_col].values), sampling_rate, freq_method)
        rows.append({
            'Channel':    'Air Pressure',
            'Block':      '—',
            'PPV':        f"{ppv:.2f} Pa",
            'Frequency':  f"{freq} Hz",
            'Transducer': 'Microphone',
            'Test':       '—',
        })

    # ── KBf / virtual channels ────────────────────────────────────────────────
    kbf_cols = [c for c in df.columns if 'KBf' in c]
    for col in kbf_cols:
        ppv = df[col].abs().max()
        rows.append({
            'Channel':    col.split(' ')[1] + ' KBf',
            'Block':      '—',
            'PPV':        f"{ppv:.4f} KBf",
            'Frequency':  '—',
            'Transducer': 'KBf (virtual)',
            'Test':       '—',
        })

    return rows


def _find_channel_index(ch_lookup, axis_label, block):
    """Find channel index matching axis label and block number."""
    AXIS_MATCH = {
        'Vertical':     ('Vertical', 'X'),
        'Longitudinal': ('Longitudinal', 'Y'),
        'Transversal':  ('Transverse', 'Z'),
    }
    valid_axes = AXIS_MATCH.get(axis_label, (axis_label,))
    for idx, ch in ch_lookup.items():
        if ch['axis'] in valid_axes and ch['belongs_to_block'] == block:
            return idx
    return None


def _get_transducer_info(ch_idx, ch_lookup, geophone_test):
    """Return (transducer type string, test result string) for a channel."""
    if ch_idx is None or ch_idx not in ch_lookup:
        return '—', '—'
    ch = ch_lookup[ch_idx]
    transducer = ch.get('type', '—')
    # geophone_test covers physical channels 1-7
    if ch_idx <= 7 and geophone_test:
        test_result = geophone_test[ch_idx - 1]
        icon = '✅' if test_result == 'OK' else ('⚠️' if test_result == 'Not performed' else '❌')
        test = f"{icon} {test_result}"
    else:
        test = '—'
    return transducer, test


# ── SNI 7571:2023 chart renderer ───────────────────────────────────────────────

def _render_sni_chart(df, time_axis, sampling_rate, metadata):
    """
    Plot PPV points for all active velocity channels onto the SNI 7571:2023
    limit curve graph. User selects which infrastructure class applies.
    """
    from core.sni_chart import SNI_LIMITS

    # ── Class selector ─────────────────────────────────────────────────────────
    class_options = {
        'Kelas 1 — Bangunan sangat sensitif (heritage, bersejarah)': 1,
        'Kelas 2 — Bangunan sensitif (rumah tinggal lama)':          2,
        'Kelas 3 — Bangunan biasa (rumah tinggal, ruko)':            3,
        'Kelas 4 — Bangunan kokoh (beton bertulang, industri)':      4,
        'Kelas 5 — Infrastruktur khusus (bendungan, tambang)':       5,
    }
    selected_label = st.selectbox(
        "Infrastructure Class",
        options=list(class_options.keys()),
        index=2,  # default Kelas 3
    )
    selected_class = class_options[selected_label]

    # ── Build PPV points from current recording ────────────────────────────────
    freq_method = DEFAULT_FREQUENCY_METHOD
    ppv_points = []

    channel_map = [
        ('Vertical (mm/s)',        'Vertical',        1),
        ('Longitudinal (mm/s)',    'Longitudinal',    1),
        ('Transversal (mm/s)',     'Transversal',     1),
        ('Vertical B2 (mm/s)',     'Vertical B2',     2),
        ('Longitudinal B2 (mm/s)', 'Longitudinal B2', 2),
        ('Transversal B2 (mm/s)',  'Transversal B2',  2),
    ]

    for col, ch_name, block in channel_map:
        if col not in df.columns:
            continue
        ppv  = float(df[col].abs().max())
        freq = float(calculate_frequency(tuple(df[col].values), sampling_rate, freq_method))
        ppv_points.append({
            'channel': ch_name,
            'ppv':     ppv,
            'freq':    freq,
            'block':   block,
        })

    if not ppv_points:
        st.info("No velocity data available.")
        return

    # ── Compliance summary ─────────────────────────────────────────────────────
    limits = SNI_LIMITS[selected_class]
    violations = []
    for pt in ppv_points:
        seg = 0 if pt['freq'] < 5 else (1 if pt['freq'] < 20 else 2)
        if pt['ppv'] > limits[seg]:
            violations.append(pt)

    if violations:
        names = ', '.join(f"Blk{v['block']} {v['channel']}" if v['block'] == 2
                          else v['channel'] for v in violations)
        st.error(f"⚠️ Exceeds Kelas {selected_class} limit: **{names}**")
    else:
        st.success(f"✅ All channels comply with Kelas {selected_class}")

    # ── Chart ──────────────────────────────────────────────────────────────────
    fig = build_sni_chart(ppv_points)

    # Highlight selected class curve
    for trace in fig.data:
        if hasattr(trace, 'name') and trace.name == f'Cl. {selected_class}':
            trace.line.width = 3.5

    st.plotly_chart(fig, use_container_width=True)

    # Legend note matching Vibracord convention
    st.caption("Tran: +   Vert: ×   Long: ○   (hollow = Block 2)")

# pages/ppv_analysis.py
"""
PPV vs Scaled Distance Analysis page — regression and safe zone prediction.
"""

from html import escape

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from regression.scaled_distance import standard_scaled_distance
from regression.fitting import (
    fit_power_law,
    regression_curve,
    confidence_curve,
)
from config import VELOCITY_CHANNELS


_CHANNEL_COLORS = {
    'Vertical': '#00897B',
    'Longitudinal': '#E53935',
    'Transversal': '#5C6BC0',
}


def _equation(K, n):
    return f"PPV = {K} × SD^{n}"


def _build_regression_result(data_rows, selected_names):
    """Build an immutable snapshot of one explicit regression calculation."""
    if not selected_names:
        raise ValueError("Please select at least one channel.")

    data = pd.DataFrame(data_rows)
    required_columns = [
        'Charge (kg)',
        'Distance (m)',
        'Vertical (mm/s)',
        'Longitudinal (mm/s)',
        'Transversal (mm/s)',
    ]
    data = data[
        (data['Charge (kg)'] > 0) & (data['Distance (m)'] > 0)
    ].dropna(subset=required_columns)

    if len(data) < 4:
        raise ValueError("Please enter at least 4 valid data points.")

    charges = data['Charge (kg)'].values
    distances = data['Distance (m)'].values
    channels = {
        'Vertical': data['Vertical (mm/s)'].values,
        'Longitudinal': data['Longitudinal (mm/s)'].values,
        'Transversal': data['Transversal (mm/s)'].values,
    }

    # Pool the actual PPV points from every selected channel into the fit.
    # This preserves the existing behavior where each selected channel
    # contributes independently instead of collapsing each shot to its max.
    scaled_distance_parts = []
    ppv_parts = []
    for name in selected_names:
        values = channels[name]
        channel_valid = values > 0
        scaled_distance_parts.append(
            standard_scaled_distance(
                distances[channel_valid],
                charges[channel_valid],
            )
        )
        ppv_parts.append(values[channel_valid])

    scaled_distance = np.concatenate(scaled_distance_parts)
    ppv = np.concatenate(ppv_parts)
    if len(scaled_distance) < 4:
        raise ValueError(
            "Please enter at least 4 positive PPV values across the selected channels."
        )

    # Plot markers against the original row order for the selected channels.
    valid_rows = np.zeros(len(charges), dtype=bool)
    for name in selected_names:
        valid_rows |= channels[name] > 0
    valid_charges = charges[valid_rows]
    valid_distances = distances[valid_rows]
    display_scaled_distance = standard_scaled_distance(
        valid_distances,
        valid_charges,
    )

    fit = fit_power_law(scaled_distance, ppv)
    x_range = np.linspace(scaled_distance.min(), scaled_distance.max(), 200)
    y_regression = regression_curve(fit['K'], fit['n'], x_range)
    y_confidence = confidence_curve(fit['K_conf'], fit['n'], x_range)

    figure = go.Figure()
    blocks = (
        data['Block'].values[valid_rows]
        if 'Block' in data.columns
        else np.ones(valid_rows.sum())
    )
    block_symbol = {1: 'circle-open', 2: 'square-open'}
    block_label = {1: '', 2: ' (Blk2)'}

    for channel_name in selected_names:
        values = channels[channel_name][valid_rows]
        for block in sorted(set(blocks.astype(int))):
            block_mask = blocks.astype(int) == block
            if not block_mask.any():
                continue
            figure.add_trace(go.Scatter(
                x=display_scaled_distance[block_mask],
                y=values[block_mask],
                mode='markers',
                name=f"{channel_name}{block_label.get(block, '')}",
                marker=dict(
                    color=_CHANNEL_COLORS[channel_name],
                    size=10,
                    symbol=block_symbol.get(block, 'circle-open'),
                    line=dict(width=2),
                ),
            ))

    figure.add_trace(go.Scatter(
        x=x_range,
        y=y_regression,
        mode='lines',
        name='Regression line',
        line=dict(color='#E53935', width=2.5),
    ))
    figure.add_trace(go.Scatter(
        x=x_range,
        y=y_confidence,
        mode='lines',
        name='95% Confidence line',
        line=dict(color='#FFB300', width=2.5, dash='dash'),
    ))
    figure.update_layout(
        xaxis_title="Scaled Distance — D / √Q (m/kg^0.5)",
        yaxis_title="PPV (mm/s)",
        xaxis_type="log",
        yaxis_type="log",
        height=550,
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=-0.3),
    )

    return {
        'figure': figure,
        'fit': fit,
        'regression_equation': _equation(fit['K'], fit['n']),
        'confidence_equation': _equation(fit['K_conf'], fit['n']),
        'selected_channels': tuple(selected_names),
    }


def _render_regression_result(result):
    """Render the last explicitly calculated result snapshot."""
    st.caption(
        "Showing the last calculated regression. Table and channel edits are "
        "applied only after clicking Calculate Regression again."
    )
    st.plotly_chart(result['figure'], use_container_width=True)
    st.subheader("Regression Results")
    st.markdown(f"**Regression:** {result['regression_equation']}")
    confidence_equation = escape(result['confidence_equation'])
    st.markdown(
        '<div class="metis-confidence-result">'
        '<div class="metis-confidence-result__label">Confidence (95%)</div>'
        f'<div class="metis-confidence-result__equation">{confidence_equation}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.metric("Correlation Coefficient (r)", result['fit']['r'])


def render(uploaded_files_dict, ppv_registry):
    st.title("📈 Attenuation & Safe Zone")
    st.caption("Linear regression of Peak Particle Velocity against scaled distance.Uses the standard scaled distance formula: **PPV = K × (D / √Q)^n**")
    st.divider()

    # ── Data input table ───────────────────────────────────────────────────────
    st.subheader("Blast Event Data")

    EMPTY_ROW = {
        'No.': 1,
        'Source': '',
        'Block': 1,
        'Charge (kg)': 0.0,
        'Distance (m)': 0.0,
        'Vertical (mm/s)': 0.0,
        'Longitudinal (mm/s)': 0.0,
        'Transversal (mm/s)': 0.0,
    }

    # ── Initialise table from uploaded files ──────────────────────────────────
    if 'ppv_table' not in st.session_state:
        st.session_state.ppv_table = pd.DataFrame([EMPTY_ROW])

    # Ensure No. column exists for tables loaded before this feature was added
    if 'No.' not in st.session_state.ppv_table.columns:
        st.session_state.ppv_table.insert(0, 'No.', range(1, len(st.session_state.ppv_table) + 1))

    # Track which files have ever been imported — independent of current table rows.
    # This prevents deleted rows from being re-added on rerun.
    if 'ppv_imported' not in st.session_state:
        st.session_state.ppv_imported = set()

    # Merge any newly uploaded files into the table
    existing_sources = set(st.session_state.ppv_table['Source'].tolist())
    new_rows = []
    for fname in uploaded_files_dict.keys():
        if fname not in existing_sources:
            registry = ppv_registry.get(fname, {'vert': 0.0, 'long': 0.0, 'tran': 0.0})
            # Block 1
            new_rows.append({
                'No.': len(st.session_state.ppv_table) + len(new_rows) + 1,
                'Source': fname,
                'Block': 1,
                'Charge (kg)': 0.0,
                'Distance (m)': 0.0,
                'Vertical (mm/s)': float(registry.get('vert', 0.0)),
                'Longitudinal (mm/s)': float(registry.get('long', 0.0)),
                'Transversal (mm/s)': float(registry.get('tran', 0.0)),
            })
            # Block 2 — only if dual-block file
            if registry.get('vert_b2') is not None:
                new_rows.append({
                    'No.': len(st.session_state.ppv_table) + len(new_rows) + 1,
                    'Source': fname,
                    'Block': 2,
                    'Charge (kg)': 0.0,
                    'Distance (m)': 0.0,
                    'Vertical (mm/s)': float(registry.get('vert_b2', 0.0)),
                    'Longitudinal (mm/s)': float(registry.get('long_b2', 0.0)),
                    'Transversal (mm/s)': float(registry.get('tran_b2', 0.0)),
                })
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        current = st.session_state.ppv_table
        if len(current) == 1 and current.iloc[0]['Source'] == '' and current.iloc[0]['Charge (kg)'] == 0.0:
            st.session_state.ppv_table = new_df
        else:
            st.session_state.ppv_table = pd.concat([current, new_df], ignore_index=True)
        # Mark all newly imported files so they are never re-added
        for row in new_rows:
            st.session_state.ppv_imported.add(row['Source'])

    # ── Save / Load / Info — one clean row ────────────────────────────────────
    _save_load_col, _info_col = st.columns([1, 3])

    with _save_load_col:
        # Placeholder filled in AFTER the data_editor call below, so the
        # download always contains the latest edits even though this button
        # is drawn above the table. See the comment near `edited_df` for why
        # we don't source this from st.session_state.ppv_table directly.
        _save_button_slot = st.empty()
        loaded_file = st.file_uploader(
            "📂 Load Table", type="csv",
            key="ppv_load_csv", label_visibility="visible"
        )
        if loaded_file:
            try:
                loaded_df = pd.read_csv(loaded_file)
                for col in EMPTY_ROW.keys():
                    if col not in loaded_df.columns:
                        if col == 'No.':
                            loaded_df[col] = range(1, len(loaded_df) + 1)
                        elif col == 'Source':
                            loaded_df[col] = ''
                        elif col == 'Block':
                            loaded_df[col] = 1
                        else:
                            loaded_df[col] = 0.0
                st.session_state.ppv_table = loaded_df[list(EMPTY_ROW.keys())]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to load file: {e}")

    with _info_col:
        st.info("Use **Tab** to confirm and move between cells · **Arrow keys** to navigate · **Click the bottom row** to add a new entry")

    # ── Editable table ─────────────────────────────────────────────────────────
    # IMPORTANT — why there's no on_change/sync-back here:
    # st.data_editor merges its own internal per-`key` edit state with the
    # `data` you pass it on every rerun. That merge only works cleanly if
    # `data` stays byte-identical across reruns. The previous version wrote
    # every keystroke straight back into st.session_state.ppv_table (the same
    # object fed back in as `data`), so on the very next rerun the widget saw
    # a *different* `data` than before and threw away its focus/selection
    # state — hence "click the cell again for every input". (This matches a
    # long-standing Streamlit behavior: https://github.com/streamlit/streamlit/issues/7749)
    #
    # Fix: keep st.session_state.ppv_table frozen across simple cell edits and
    # read the live, fully-merged result from `edited_df` (the return value)
    # for everything downstream in this same run — Save, regression, etc.
    # We only overwrite st.session_state.ppv_table when a row was actually
    # added/deleted (a structural change the widget already has to redraw
    # for), so normal typing never causes a remount.
    edited_df = st.data_editor(
        st.session_state.ppv_table,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            'No.':                  st.column_config.NumberColumn("No.", width="small", disabled=True),
            'Source':               st.column_config.TextColumn("Source", width="medium"),
            'Block':                st.column_config.NumberColumn("Blk", width="small"),
            'Charge (kg)':          st.column_config.NumberColumn("Charge (kg)",   min_value=0.0, format="%.1f"),
            'Distance (m)':         st.column_config.NumberColumn("Distance (m)",  min_value=0.0, format="%.1f"),
            'Vertical (mm/s)':      st.column_config.NumberColumn("Vert (mm/s)",   min_value=0.0, format="%.2f"),
            'Longitudinal (mm/s)':  st.column_config.NumberColumn("Long (mm/s)",   min_value=0.0, format="%.2f"),
            'Transversal (mm/s)':   st.column_config.NumberColumn("Tran (mm/s)",   min_value=0.0, format="%.2f"),
        },
        key="ppv_data_editor",
    )

    # Renumber for display/downstream use only — never fed back as `data`.
    live_df = edited_df.copy()
    live_df['No.'] = range(1, len(live_df) + 1)

    # Persist only on structural changes (row added/removed), not per keystroke.
    if len(live_df) != len(st.session_state.ppv_table):
        st.session_state.ppv_table = live_df

    with _save_button_slot:
        st.download_button(
            label="💾 Save Table",
            data=live_df.to_csv(index=False).encode('utf-8'),
            file_name="blast_event_data.csv",
            mime="text/csv",
            use_container_width=True,
        )

    data_rows = live_df.to_dict('records')

    st.divider()

    # ── Channel selection ──────────────────────────────────────────────────────
    st.markdown("**Include channels in regression:**")
    cb1, cb2, cb3 = st.columns(3)
    use_vert = cb1.checkbox("Vertical", value=True)
    use_long = cb2.checkbox("Longitudinal", value=True)
    use_tran = cb3.checkbox("Transversal", value=True)

    # ── Calculate Regression ───────────────────────────────────────────────────
    selected_names = [
        name
        for name, use in [
            ('Vertical', use_vert),
            ('Longitudinal', use_long),
            ('Transversal', use_tran),
        ]
        if use
    ]
    if st.button("📐 Calculate Regression", type="primary"):
        try:
            regression_result = _build_regression_result(data_rows, selected_names)
        except ValueError as exc:
            st.error(str(exc))
        else:
            # Both the chart and numeric result are a snapshot of this click.
            # Subsequent widget/table reruns keep rendering this same snapshot.
            st.session_state['ppv_regression_result'] = regression_result
            st.session_state['ppv_fit'] = regression_result['fit']

    regression_result = st.session_state.get('ppv_regression_result')
    if regression_result is not None:
        _render_regression_result(regression_result)

    # ── Safe Zone Calculator ───────────────────────────────────────────────────
    if 'ppv_fit' in st.session_state:
        fit = st.session_state['ppv_fit']

        st.divider()
        st.subheader("🛡️ Safe Zone Calculator")
        st.info(
            "⚠️ Predictions are based on the **95% confidence line**, "
            "which is more conservative than the regression line. "
            "This is the recommended approach for safety assessments.",
            icon=None
        )

        K = fit['K_conf']
        n = fit['n']

        col_d, col_q, col_ppv = st.columns(3)

        with col_d:
            st.markdown("**📏 Min Distance**")
            q_d = st.number_input("Charge (kg)", min_value=0.1, value=100.0, step=1.0, key="sz_q_d")
            ppv_d = st.number_input("PPV Limit (mm/s)", min_value=0.01, value=5.0, step=0.1, key="sz_ppv_d")
            d_min = (q_d ** 0.5) * (ppv_d / K) ** (1 / n)
            st.metric("Minimum Safe Distance", f"{d_min:.1f} m")

        with col_q:
            st.markdown("**💣 Max Charge**")
            d_q = st.number_input("Distance (m)", min_value=0.1, value=100.0, step=1.0, key="sz_d_q")
            ppv_q = st.number_input("PPV Limit (mm/s)", min_value=0.01, value=5.0, step=0.1, key="sz_ppv_q")
            q_max = (d_q ** 2) / ((ppv_q / K) ** (2 / n))
            st.metric("Maximum Allowable Charge", f"{q_max:.1f} kg")

        with col_ppv:
            st.markdown("**📡 Predicted PPV**")
            q_p = st.number_input("Charge (kg)", min_value=0.1, value=100.0, step=1.0, key="sz_q_p")
            d_p = st.number_input("Distance (m)", min_value=0.1, value=100.0, step=1.0, key="sz_d_p")
            ppv_pred = K * ((d_p / (q_p ** 0.5)) ** n)
            st.metric("Predicted PPV", f"{ppv_pred:.3f} mm/s")

    # ── SNI 7571 Compliance Tables ─────────────────────────────────────────────
    if 'ppv_fit' in st.session_state:
        fit = st.session_state['ppv_fit']

        K = fit['K_conf']
        n = fit['n']

        st.divider()
        st.subheader("📋 SNI 7571 Compliance Tables")
        st.caption("Based on Blasting Vibration Limit Standard for Buildings in Surface Mining Activities (Indonesian National Standard)")

        # SNI 7571 PPV limits per class per frequency range
        SNI_LIMITS = {
            "0 – 5 Hz":   {"Class 1": 2,  "Class 2": 3,  "Class 3": 5,  "Class 4": 7,  "Class 5": 12},
            "5 – 20 Hz":  {"Class 1": 3,  "Class 2": 5,  "Class 3": 7,  "Class 4": 12, "Class 5": 24},
            "20 – 100 Hz":{"Class 1": 5,  "Class 2": 7,  "Class 3": 12, "Class 4": 20, "Class 5": 40},
        }

        CLASS_DESCRIPTIONS = {
            "Class 1": "Highly sensitive / heritage buildings",
            "Class 2": "Sensitive / simple residential buildings",
            "Class 3": "Standard residential buildings",
            "Class 4": "Reinforced residential / commercial buildings",
            "Class 5": "Heavy industrial / critical infrastructure",
        }

        _freq_col, _freqinfo_col = st.columns([1, 2])
        with _freq_col:
            freq_range = st.selectbox(
                "Frequency Range",
                list(SNI_LIMITS.keys()),
                help="Select based on the dominant frequency of your signal (from Signal Analysis page)"
            )
        with _freqinfo_col:
            st.info("⚠️ Verify dominant frequency from your **Signal Analysis** page before selecting a range.", icon=None)
        ppv_limits = SNI_LIMITS[freq_range]
        classes = list(ppv_limits.keys())
        ppv_values = list(ppv_limits.values())

        # Helper functions
        def calc_min_distance(charge, ppv_lim):
            return (charge ** 0.5) * (ppv_lim / K) ** (1 / n)

        def calc_max_charge(distance, ppv_lim):
            return (distance ** 2) / ((ppv_lim / K) ** (2 / n))

        # ── Table 1: Safe Distance Prediction ─────────────────────────────────
        st.markdown("### 📏 Safe Distance Prediction Table")
        st.caption("Enter charge values (kg) — table shows minimum safe distance (m) for each building class.")

        if 'sni_charges' not in st.session_state:
            st.session_state.sni_charges = [100.0]

        # Add/remove row buttons
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("➕ Add Charge Row", key="add_charge"):
            st.session_state.sni_charges.append(100.0)
            st.rerun()
        if b2.button("➖ Remove Last", key="rem_charge") and len(st.session_state.sni_charges) > 1:
            st.session_state.sni_charges.pop()
            st.rerun()

        # Header row
        header_cols = st.columns([1.2] + [1] * 5)
        header_cols[0].markdown("**Charge (kg)**")
        for i, cls in enumerate(classes):
            header_cols[i + 1].markdown(f"**{cls}**<br><small>{ppv_values[i]} mm/s</small>", unsafe_allow_html=True)

        # Data rows
        for row_i, charge_val in enumerate(st.session_state.sni_charges):
            row_cols = st.columns([1.2] + [1] * 5)
            new_val = row_cols[0].number_input(
                "", min_value=0.1, value=float(charge_val), step=1.0,
                key=f"sni_c_{row_i}", label_visibility="collapsed"
            )
            st.session_state.sni_charges[row_i] = new_val

            for i, ppv_lim in enumerate(ppv_values):
                d = calc_min_distance(new_val, ppv_lim)
                row_cols[i + 1].markdown(
                    f"<div style='background:#FFD700;padding:4px 8px;border-radius:4px;"
                    f"text-align:center;font-weight:bold'>{d:.1f} m</div>",
                    unsafe_allow_html=True
                )

        st.divider()

        # ── Table 2: Safe Charge Prediction ───────────────────────────────────
        st.markdown("### 💣 Safe Charge Prediction Table")
        st.caption("Enter distance values (m) — table shows maximum allowable charge (kg) for each building class.")

        if 'sni_distances' not in st.session_state:
            st.session_state.sni_distances = [100.0]

        b3, b4, _ = st.columns([1, 1, 4])
        if b3.button("➕ Add Distance Row", key="add_dist"):
            st.session_state.sni_distances.append(100.0)
            st.rerun()
        if b4.button("➖ Remove Last", key="rem_dist") and len(st.session_state.sni_distances) > 1:
            st.session_state.sni_distances.pop()
            st.rerun()

        # Header row
        header_cols2 = st.columns([1.2] + [1] * 5)
        header_cols2[0].markdown("**Distance (m)**")
        for i, cls in enumerate(classes):
            header_cols2[i + 1].markdown(f"**{cls}**<br><small>{ppv_values[i]} mm/s</small>", unsafe_allow_html=True)

        # Data rows
        for row_i, dist_val in enumerate(st.session_state.sni_distances):
            row_cols2 = st.columns([1.2] + [1] * 5)
            new_dist = row_cols2[0].number_input(
                "", min_value=0.1, value=float(dist_val), step=1.0,
                key=f"sni_d_{row_i}", label_visibility="collapsed"
            )
            st.session_state.sni_distances[row_i] = new_dist

            for i, ppv_lim in enumerate(ppv_values):
                q = calc_max_charge(new_dist, ppv_lim)
                row_cols2[i + 1].markdown(
                    f"<div style='background:#90CAF9;padding:4px 8px;border-radius:4px;"
                    f"text-align:center;font-weight:bold;color:black'>{q:.1f} kg</div>",
                    unsafe_allow_html=True
                )

        # Class legend
        st.divider()
        st.markdown("**Building Class Reference (SNI 7571:2023)**")
        leg_cols = st.columns(5)
        for i, (cls, desc) in enumerate(CLASS_DESCRIPTIONS.items()):
            leg_cols[i].caption(f"**{cls}**\n{desc}")

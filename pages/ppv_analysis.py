# pages/ppv_analysis.py
"""
PPV vs Scaled Distance Analysis page — regression and safe zone prediction.
"""

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


def render(uploaded_files_dict, ppv_registry):
    st.title("📈 Attenuation & Safe Zone")
    st.caption("Linear regression of Peak Particle Velocity against scaled distance.Uses the standard scaled distance formula: **PPV = K × (D / √Q)^n**")
    st.divider()

    # ── Data input table ───────────────────────────────────────────────────────
    st.subheader("Blast Event Data")
    _info_col, _save_col, _load_col = st.columns([3, 1, 1])
 
    EMPTY_ROW = {
        'No.': 1,
        'Source': '',
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

    # Merge any newly uploaded files into the table
    existing_sources = set(st.session_state.ppv_table['Source'].tolist())
    new_rows = []
    for fname in uploaded_files_dict.keys():
        if fname not in existing_sources:
            registry = ppv_registry.get(fname, {'vert': 0.0, 'long': 0.0, 'tran': 0.0})
            new_rows.append({
                'No.': len(st.session_state.ppv_table) + len(new_rows) + 1,
                'Source': fname,
                'Charge (kg)': 0.0,
                'Distance (m)': 0.0,
                'Vertical (mm/s)': float(registry['vert']),
                'Longitudinal (mm/s)': float(registry['long']),
                'Transversal (mm/s)': float(registry['tran']),
            })
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        current = st.session_state.ppv_table
        if len(current) == 1 and current.iloc[0]['Source'] == '' and current.iloc[0]['Charge (kg)'] == 0.0:
            st.session_state.ppv_table = new_df
        else:
            st.session_state.ppv_table = pd.concat([current, new_df], ignore_index=True)

    # ── Save / Load / Info — one clean row ────────────────────────────────────
    _save_col, _load_col, _info_col = st.columns([1, 1, 4])

    with _save_col:
        csv_bytes = st.session_state.ppv_table.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Save Table",
            data=csv_bytes,
            file_name="blast_event_data.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with _load_col:
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
                        else:
                            loaded_df[col] = 0.0
                st.session_state.ppv_table = loaded_df[list(EMPTY_ROW.keys())]
                st.rerun()
            except Exception as e:
                st.error(f"Failed to load file: {e}")

    with _info_col:
        st.info("Use **Tab** to confirm and move between cells · **Arrow keys** to navigate · **Click the bottom row** to add a new entry")

    # ── Editable table ─────────────────────────────────────────────────────────
    # Use on_change callback to persist edits to session state only when the
    # user commits a change — avoids the double-input revert bug while still
    # keeping session state up to date for Save and regression.
    def _sync_table():
        if 'ppv_data_editor' in st.session_state:
            state = st.session_state['ppv_data_editor']
            df = st.session_state.ppv_table.copy()
            # Apply edits
            for idx, changes in state.get('edited_rows', {}).items():
                for col, val in changes.items():
                    df.at[idx, col] = val
            # Apply additions
            for row in state.get('added_rows', []):
                new_row = {c: row.get(c, 0.0 if c != 'Source' else '') for c in df.columns}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            # Apply deletions
            deleted = state.get('deleted_rows', [])
            if deleted:
                df = df.drop(index=deleted).reset_index(drop=True)
            # Renumber No. column
            df['No.'] = range(1, len(df) + 1)
            st.session_state.ppv_table = df

    edited_df = st.data_editor(
        st.session_state.ppv_table,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            'No.':                  st.column_config.NumberColumn("No.", width="small", disabled=True),
            'Source':               st.column_config.TextColumn("Source", width="medium"),
            'Charge (kg)':          st.column_config.NumberColumn("Charge (kg)",   min_value=0.0, format="%.1f"),
            'Distance (m)':         st.column_config.NumberColumn("Distance (m)",  min_value=0.0, format="%.1f"),
            'Vertical (mm/s)':      st.column_config.NumberColumn("Vert (mm/s)",   min_value=0.0, format="%.2f"),
            'Longitudinal (mm/s)':  st.column_config.NumberColumn("Long (mm/s)",   min_value=0.0, format="%.2f"),
            'Transversal (mm/s)':   st.column_config.NumberColumn("Tran (mm/s)",   min_value=0.0, format="%.2f"),
        },
        key="ppv_data_editor",
        on_change=_sync_table,
    )
    data_rows = edited_df.to_dict('records')

    st.divider()

    # ── Channel selection ──────────────────────────────────────────────────────
    st.markdown("**Include channels in regression:**")
    cb1, cb2, cb3 = st.columns(3)
    use_vert = cb1.checkbox("Vertical", value=True)
    use_long = cb2.checkbox("Longitudinal", value=True)
    use_tran = cb3.checkbox("Transversal", value=True)

    # ── Calculate Regression ───────────────────────────────────────────────────
    if st.button("📐 Calculate Regression", type="primary"):
        data = pd.DataFrame(data_rows)
        data = data[(data['Charge (kg)'] > 0) & (data['Distance (m)'] > 0)].dropna(subset=['Charge (kg)', 'Distance (m)', 'Vertical (mm/s)', 'Longitudinal (mm/s)', 'Transversal (mm/s)'])

        if len(data) < 4:
            st.error("Please enter at least 4 valid data points.")
            return

        charges = data['Charge (kg)'].values
        distances = data['Distance (m)'].values
        channel_colors = {
            'Vertical': '#00897B',
            'Longitudinal': '#E53935',
            'Transversal': '#5C6BC0',
        }
        channels = {
            'Vertical': data['Vertical (mm/s)'].values,
            'Longitudinal': data['Longitudinal (mm/s)'].values,
            'Transversal': data['Transversal (mm/s)'].values,
        }

        # Build max PPV from selected channels
        selected = []
        if use_vert: selected.append(channels['Vertical'])
        if use_long: selected.append(channels['Longitudinal'])
        if use_tran: selected.append(channels['Transversal'])

        if not selected:
            st.error("Please select at least one channel.")
            return

        max_ppv = np.maximum.reduce(selected)
        valid = max_ppv > 0
        Q = charges[valid]
        D = distances[valid]
        V = max_ppv[valid]

        # Compute scaled distance — standard formula: SD = D / √Q
        SD = standard_scaled_distance(D, Q)
        xaxis_title = "Scaled Distance — D / √Q (m/kg^0.5)"
        eq_template = lambda K, n: f"PPV = {K} × SD^{n}"
        x_pts = {ch: standard_scaled_distance(D, Q) for ch in channels}

        fit = fit_power_law(SD, V)
        x_range = np.linspace(SD.min(), SD.max(), 200)
        y_reg = regression_curve(fit['K'], fit['n'], x_range)
        y_conf = confidence_curve(fit['K_conf'], fit['n'], x_range)

        fig = go.Figure()

        # Data points
        for ch_name, ppv_vals in channels.items():
            if ch_name == 'Vertical' and not use_vert: continue
            if ch_name == 'Longitudinal' and not use_long: continue
            if ch_name == 'Transversal' and not use_tran: continue
            color = channel_colors[ch_name]
            v = ppv_vals[valid]
            fig.add_trace(go.Scatter(
                x=x_pts[ch_name], y=v,
                mode='markers', name=ch_name,
                marker=dict(color=color, size=10, symbol='circle-open',
                            line=dict(width=2)),
            ))

        # Regression and confidence lines
        fig.add_trace(go.Scatter(
            x=x_range, y=y_reg, mode='lines',
            name='Regression line',
            line=dict(color='#E53935', width=2.5),
        ))
        fig.add_trace(go.Scatter(
            x=x_range, y=y_conf, mode='lines',
            name='95% Confidence line',
            line=dict(color='#FFB300', width=2.5, dash='dash'),
        ))

        fig.update_layout(
            xaxis_title=xaxis_title,
            yaxis_title="PPV (mm/s)",
            xaxis_type="log",
            yaxis_type="log",
            height=550,
            hovermode="closest",
            legend=dict(orientation="h", yanchor="bottom", y=-0.3)
        )
        st.plotly_chart(fig, use_container_width=True)

        # Results
        st.subheader("Regression Results")
        st.markdown(f"**Regression:** {eq_template(fit['K'], fit['n'])}")
        st.markdown(f"**Confidence (95%):** {eq_template(fit['K_conf'], fit['n'])}")
        st.metric("Correlation Coefficient (r)", fit['r'])

        # Store regression results in session state for the calculator
        st.session_state['ppv_fit'] = fit

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
        st.caption("Based on SNI 7571:2023 — Baku Tingkat Getaran Peledakan pada Kegiatan Tambang Terbuka terhadap Bangunan")

        # SNI 7571 PPV limits per class per frequency range
        SNI_LIMITS = {
            "0 – 5 Hz":   {"Class 1": 2,  "Class 2": 3,  "Class 3": 5,  "Class 4": 7,  "Class 5": 12},
            "5 – 20 Hz":  {"Class 1": 3,  "Class 2": 5,  "Class 3": 7,  "Class 4": 12, "Class 5": 24},
            "20 – 100 Hz":{"Class 1": 5,  "Class 2": 7,  "Class 3": 12, "Class 4": 20, "Class 5": 40},
        }

        CLASS_DESCRIPTIONS = {
            "Class 1": "Very sensitive / historic buildings",
            "Class 2": "Sensitive buildings / light residential",
            "Class 3": "General residential buildings",
            "Class 4": "Commercial buildings / light industrial",
            "Class 5": "Heavy industrial buildings",
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

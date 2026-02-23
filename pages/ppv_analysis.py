# pages/ppv_analysis.py
"""
PPV vs Scaled Distance Analysis page — regression and safe zone prediction.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from regression.scaled_distance import (
    standard_scaled_distance,
    optimized_scaled_distance,
    find_best_exponent,
)
from regression.fitting import (
    fit_power_law,
    regression_curve,
    confidence_curve,
)
from config import VELOCITY_CHANNELS


def render(uploaded_files_dict, ppv_registry):
    st.title("📈 PPV vs Scaled Distance Analysis")
    st.caption("Linear regression of Peak Particle Velocity against scaled distance.")
    st.divider()

    # ── Formula selection ──────────────────────────────────────────────────────
    st.subheader("Regression Formula")
    formula = st.radio(
        "Select formula type",
        ["Standard Scaled Distance  —  PPV = K × (D/√Q)^n",
         "Two-Variable  —  PPV = K × Q^α × D^β"],
        horizontal=True
    )
    use_two_var = "Two-Variable" in formula
    st.divider()

    # ── Data input table ───────────────────────────────────────────────────────
    st.subheader("Blast Event Data")
    st.caption("PPV values are auto-filled from uploaded files. You can edit any value manually.")

    if 'ppv_charges' not in st.session_state:
        st.session_state.ppv_charges = {}
    if 'ppv_distances' not in st.session_state:
        st.session_state.ppv_distances = {}
    if 'ppv_manual_rows' not in st.session_state:
        st.session_state.ppv_manual_rows = []
    if 'ppv_vert_override' not in st.session_state:
        st.session_state.ppv_vert_override = {}
    if 'ppv_long_override' not in st.session_state:
        st.session_state.ppv_long_override = {}
    if 'ppv_tran_override' not in st.session_state:
        st.session_state.ppv_tran_override = {}

    if not uploaded_files_dict:
        st.info("Upload CSV files from the sidebar to auto-fill PPV values.")

    # Headers
    h0, h1, h2, h3, h4, h5 = st.columns([2.5, 1.5, 1.5, 1.5, 1.5, 1.5])
    h0.markdown("**Source**")
    h1.markdown("**Charge (kg)**")
    h2.markdown("**Distance (m)**")
    h3.markdown("**Vert (mm/s)**")
    h4.markdown("**Long (mm/s)**")
    h5.markdown("**Tran (mm/s)**")

    data_rows = []

    # Auto-filled rows from uploaded files
    for fname in uploaded_files_dict.keys():
        registry = ppv_registry.get(fname, {'vert': 0.0, 'long': 0.0, 'tran': 0.0})
        auto_vert = registry['vert']
        auto_long = registry['long']
        auto_tran = registry['tran']

        c0, c1, c2, c3, c4, c5 = st.columns([2.5, 1.5, 1.5, 1.5, 1.5, 1.5])
        c0.caption(fname)
        charge = c1.number_input("", min_value=0.0, value=None,
            placeholder="kg", key=f"ppv_charge_{fname}",
            label_visibility="collapsed")
        distance = c2.number_input("", min_value=0.0, value=None,
            placeholder="m", key=f"ppv_dist_{fname}",
            label_visibility="collapsed")
        vert = c3.number_input("", min_value=0.0,
            value=float(auto_vert), key=f"ppv_vert_{fname}",
            label_visibility="collapsed")
        long_ = c4.number_input("", min_value=0.0,
            value=float(auto_long), key=f"ppv_long_{fname}",
            label_visibility="collapsed")
        tran = c5.number_input("", min_value=0.0,
            value=float(auto_tran), key=f"ppv_tran_{fname}",
            label_visibility="collapsed")

        data_rows.append({
            'Charge (kg)': charge,
            'Distance (m)': distance,
            'Vertical (mm/s)': vert,
            'Longitudinal (mm/s)': long_,
            'Transversal (mm/s)': tran,
        })

    # Manual rows
    for i, row in enumerate(st.session_state.ppv_manual_rows):
        c0, c1, c2, c3, c4, c5 = st.columns([2.5, 1.5, 1.5, 1.5, 1.5, 1.5])
        c0.caption(f"Manual {i+1}")
        st.session_state.ppv_manual_rows[i]['Charge (kg)'] = c1.number_input(
            "", min_value=0.0, value=None, placeholder="kg",
            key=f"man_charge_{i}", label_visibility="collapsed")
        st.session_state.ppv_manual_rows[i]['Distance (m)'] = c2.number_input(
            "", min_value=0.0, value=None, placeholder="m",
            key=f"man_dist_{i}", label_visibility="collapsed")
        st.session_state.ppv_manual_rows[i]['Vertical (mm/s)'] = c3.number_input(
            "", min_value=0.0, value=None, placeholder="mm/s",
            key=f"man_vert_{i}", label_visibility="collapsed")
        st.session_state.ppv_manual_rows[i]['Longitudinal (mm/s)'] = c4.number_input(
            "", min_value=0.0, value=None, placeholder="mm/s",
            key=f"man_long_{i}", label_visibility="collapsed")
        st.session_state.ppv_manual_rows[i]['Transversal (mm/s)'] = c5.number_input(
            "", min_value=0.0, value=None, placeholder="mm/s",
            key=f"man_tran_{i}", label_visibility="collapsed")
        data_rows.append(st.session_state.ppv_manual_rows[i])

    # Add/remove manual rows
    st.divider()
    btn1, btn2 = st.columns(2)
    if btn1.button("➕ Add Manual Row"):
        st.session_state.ppv_manual_rows.append({
            'Charge (kg)': 0.0, 'Distance (m)': 0.0,
            'Vertical (mm/s)': 0.0, 'Longitudinal (mm/s)': 0.0,
            'Transversal (mm/s)': 0.0
        })
        st.rerun()
    if btn2.button("➖ Remove Last Manual Row") and st.session_state.ppv_manual_rows:
        st.session_state.ppv_manual_rows.pop()
        st.rerun()

    st.divider()

    # ── Channel selection ──────────────────────────────────────────────────────
    st.markdown("**Include channels in regression:**")
    cb1, cb2, cb3 = st.columns(3)
    use_vert = cb1.checkbox("Vertical", value=True)
    use_long = cb2.checkbox("Longitudinal", value=True)
    use_tran = cb3.checkbox("Transversal", value=True)

    # ── Calculate Regression ───────────────────────────────────────────────────
    if st.button("📐 Calculate Regression", type="primary"):
        data = pd.DataFrame(data_rows).dropna()
        data = data[(data['Charge (kg)'] > 0) & (data['Distance (m)'] > 0)]

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

        # Compute scaled distance
        if use_two_var:
            best_exp = find_best_exponent(D, Q, V)
            SD = optimized_scaled_distance(D, Q, best_exp)
            xaxis_title = f"D · Q^{best_exp:.3f}"
            eq_template = lambda K, n: f"PPV = {K} × Q^{best_exp:.3f} × D^{n}"
            x_pts = {
                ch: optimized_scaled_distance(D, Q, best_exp)
                for ch in channels
            }
        else:
            SD = standard_scaled_distance(D, Q)
            xaxis_title = "D · Q^-0.500"
            eq_template = lambda K, n: f"PPV = {K} × SD^{n}"
            x_pts = {
                ch: standard_scaled_distance(D, Q)
                for ch in channels
            }

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

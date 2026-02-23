# pages/sha.py
"""
Signature Hole Analysis page — blast timing optimization.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import SimulationConfig, VELOCITY_CHANNELS
from optimizer.delay_scan import build_delay_grid, scan, results_to_dataframe


def render(df, time_axis, sampling_rate):
    st.title("💥 Signature Hole Analysis")
    st.divider()

    # ── STEP 1 — Truncate Waveform ─────────────────────────────────────────────
    st.markdown("## Step 1 — Truncate Waveform")
    st.caption("Isolate the signature hole pulse by selecting the active window.")

    max_time = time_axis[-1]

    input_mode = st.radio(
        "Input mode",
        ["Manual", "Visual Slider"],
        horizontal=True
    )

    if input_mode == "Manual":
        c1, c2 = st.columns(2)
        t_start = c1.number_input("Start time (ms)", min_value=0.0,
                                   max_value=max_time, value=0.0)
        t_end = c2.number_input("End time (ms)", min_value=0.0,
                                 max_value=max_time, value=max_time)
    else:
        t_start, t_end = st.slider(
            "Select window (ms)",
            min_value=0.0, max_value=max_time,
            value=(0.0, max_time), step=1.0
        )

    start_idx = int(t_start * sampling_rate / 1000)
    end_idx = int(t_end * sampling_rate / 1000)
    truncated_time = time_axis[start_idx:end_idx]

    # Preview truncated waveform
    vel_cols = [c for c in VELOCITY_CHANNELS.keys() if c in df.columns]
    colors = list(VELOCITY_CHANNELS.values())

    fig_trunc = make_subplots(
        rows=len(vel_cols), cols=1,
        shared_xaxes=True,
        subplot_titles=vel_cols,
        vertical_spacing=0.06
    )
    for i, (col, color) in enumerate(zip(vel_cols, colors)):
        fig_trunc.add_trace(
            go.Scatter(
                x=truncated_time,
                y=df[col].values[start_idx:end_idx],
                mode='lines', name=col,
                line=dict(color=color)
            ),
            row=i + 1, col=1
        )
    fig_trunc.update_layout(
        height=300 * len(vel_cols),
        hovermode="x unified",
        showlegend=False,
        margin=dict(t=60, b=40)
    )
    st.plotly_chart(fig_trunc, use_container_width=True)
    st.caption(
        f"Selected window: {t_start} ms to {t_end} ms — "
        f"{len(truncated_time)} data points"
    )

    st.divider()

    # ── STEP 2 — Blast Design Parameters ──────────────────────────────────────
    st.markdown("## Step 2 — Blast Design Parameters")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Deck Configuration**")
        num_decks = st.number_input("Number of Decks per Hole",
                                     min_value=1, max_value=10, value=1)
        deck_delay = st.number_input("Inter-Deck Delay (ms)",
                                      min_value=0, max_value=500, value=0)
    with col2:
        st.markdown("**Row Configuration**")
        num_rows = st.number_input("Number of Rows",
                                    min_value=1, max_value=20, value=1)
        row_delay_start = st.number_input("Inter-Row Delay Start (ms)",
                                           min_value=0, max_value=500, value=20)
        row_delay_end = st.number_input("Inter-Row Delay End (ms)",
                                         min_value=0, max_value=500, value=150)
        row_delay_increment = st.number_input("Inter-Row Delay Increment (ms)",
                                               min_value=1, max_value=100, value=1)
    with col3:
        st.markdown("**Hole Configuration**")
        num_holes = st.number_input("Number of Holes per Row",
                                     min_value=1, max_value=50, value=5)
        hole_delay_start = st.number_input("Inter-Hole Delay Start (ms)",
                                            min_value=0, max_value=500, value=20)
        hole_delay_end = st.number_input("Inter-Hole Delay End (ms)",
                                          min_value=0, max_value=500, value=150)
        hole_delay_increment = st.number_input("Inter-Hole Delay Increment (ms)",
                                                min_value=1, max_value=100, value=1)

    hole_delays, row_delays, total_combos = build_delay_grid(
        hole_delay_start, hole_delay_end, hole_delay_increment,
        row_delay_start, row_delay_end, row_delay_increment,
    )
    st.info(
        f"This will simulate **{len(hole_delays)}** inter-hole delays × "
        f"**{len(row_delays)}** inter-row delays = **{total_combos:,}** total combinations."
    )

    st.divider()

    # ── STEP 3 — Run Simulation ────────────────────────────────────────────────
    st.markdown("## Step 3 — Run the Simulation")

    if st.button("▶ Run Simulation", type="primary"):
        waveform = {
            'Vert': df['Vertical (mm/s)'].values[start_idx:end_idx],
            'Long': df['Longitudinal (mm/s)'].values[start_idx:end_idx],
            'Tran': df['Transversal (mm/s)'].values[start_idx:end_idx],
        }

        config = SimulationConfig(
            sample_rate=sampling_rate,
            waveform=waveform,
            hole_delays_ms=hole_delays,
            row_delays_ms=row_delays,
            n_holes=num_holes,
            n_rows=num_rows,
            n_decks=num_decks,
            deck_delay_ms=float(deck_delay),
        )

        progress = st.progress(0, text="Running simulation...")

        def progress_callback(count, total):
            progress.progress(count / total,
                              text=f"Running simulation... {count}/{total}")

        results_df, best, best_idx = scan(config, progress_callback)
        progress.empty()

        st.session_state['sha_results_df'] = results_df
        st.session_state['sha_best'] = best
        st.session_state['sha_best_idx'] = best_idx

    if 'sha_results_df' in st.session_state:
        results_df = st.session_state['sha_results_df']
        best = st.session_state['sha_best']
        best_idx = st.session_state['sha_best_idx']

        st.success(
            f"✅ Simulation complete! "
            f"Best combination: Hole Delay = {best['hole_delay_ms']} ms, "
            f"Row Delay = {best['row_delay_ms']} ms — "
            f"Peak Vector Sum = {best['pvs']} mm/s"
        )

        # ── Ranked Recommendations ─────────────────────────────────────────
        st.subheader("🏆 Top Recommendations")
        st.caption("Ranked by combined score of Peak Vector Sum and dominant frequency. Lower PVS and higher frequency = safer.")

        n_top = st.slider("Number of recommendations to show", 3, 20, 5)

        pvs_vals = results_df['Peak Vector Sum (mm/s)'].values
        freq_vert = results_df['Freq Vert (Hz)'].values
        freq_long = results_df['Freq Long (Hz)'].values
        freq_tran = results_df['Freq Tran (Hz)'].values
        min_freq = np.minimum(np.minimum(freq_vert, freq_long), freq_tran)

        pvs_norm = (pvs_vals - pvs_vals.min()) / (pvs_vals.max() - pvs_vals.min() + 1e-9)
        freq_norm = (min_freq - min_freq.min()) / (min_freq.max() - min_freq.min() + 1e-9)

        score = 0.6 * pvs_norm - 0.4 * freq_norm
        results_df = results_df.copy()
        results_df['Score'] = score

        top_df = results_df.nsmallest(n_top, 'Score').drop(columns=['Score'])

        def highlight_top(row):
            if row.name == top_df.index[0]:
                return ['background-color: #c8e6c9'] * len(row)
            return ['background-color: #f1f8e9'] * len(row)

        st.dataframe(
            top_df.style.apply(highlight_top, axis=1).format({
                'PPV Vert (mm/s)': '{:.2f}',
                'PPV Long (mm/s)': '{:.2f}',
                'PPV Tran (mm/s)': '{:.2f}',
                'Peak Vector Sum (mm/s)': '{:.2f}',
                'Freq Vert (Hz)': '{:.2f}',
                'Freq Long (Hz)': '{:.2f}',
                'Freq Tran (Hz)': '{:.2f}',
            }),
            use_container_width=True
        )
        st.caption("🟢 Best overall | 🟩 Other strong candidates")

        st.subheader("Simulation Results")

        def highlight_best(row):
            if row.name == best_idx:
                return ['background-color: #c8e6c9'] * len(row)
            return [''] * len(row)

        st.dataframe(
            results_df.drop(columns=['Score'], errors='ignore').style.apply(
                highlight_best, axis=1).format({
                'PPV Vert (mm/s)': '{:.2f}',
                'PPV Long (mm/s)': '{:.2f}',
                'PPV Tran (mm/s)': '{:.2f}',
                'Peak Vector Sum (mm/s)': '{:.2f}',
                'Freq Vert (Hz)': '{:.2f}',
                'Freq Long (Hz)': '{:.2f}',
                'Freq Tran (Hz)': '{:.2f}',
            }),
            use_container_width=True
        )

        csv = results_df.drop(columns=['Score'], errors='ignore').to_csv(index=False).encode('utf-8')
        st.download_button(
            label="⬇️ Download Results as CSV",
            data=csv,
            file_name="sha_results.csv",
            mime="text/csv"
        )

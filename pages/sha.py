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

    max_time_ms = float(time_axis[-1] * 1000)

    input_mode = st.radio(
        "Input mode",
        ["Manual", "Visual Slider"],
        horizontal=True
    )

    if input_mode == "Manual":
        c1, c2 = st.columns(2)
        t_start = c1.number_input("Start time (ms)", min_value=0.0,
                                   max_value=max_time_ms, value=0.0)
        t_end = c2.number_input("End time (ms)", min_value=0.0,
                                 max_value=max_time_ms, value=max_time_ms)
    else:
        t_start, t_end = st.slider(
            "Select window (ms)",
            min_value=0.0, max_value=max_time_ms,
            value=(0.0, max_time_ms), step=1.0
        )

    start_idx = int(t_start * sampling_rate / 1000)
    end_idx = int(t_end * sampling_rate / 1000)
    truncated_time = time_axis[start_idx:end_idx] * 1000  # ms for display

    # Preview truncated waveform — show only the selected block
    has_block2_preview = 'Vertical B2 (mm/s)' in df.columns
    if has_block2_preview:
        block_choice_preview = st.radio(
            "Preview block",
            ["Block 1", "Block 2"],
            horizontal=True,
            key='preview_block',
        )
        sfx_preview = ' B2' if block_choice_preview == "Block 2" else ''
    else:
        sfx_preview = ''

    vel_cols = [f'Vertical{sfx_preview} (mm/s)', f'Longitudinal{sfx_preview} (mm/s)',
                f'Transversal{sfx_preview} (mm/s)']
    vel_cols = [c for c in vel_cols if c in df.columns]
    colors = ['#00897B', '#E53935', '#5C6BC0']

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

    # ── STEP 2.5 — Charge Weight & Distance Scaling (optional) ───────────────
    st.markdown("## Step 2.5 — Charge Weight & Distance Scaling (optional)")
    st.caption(
        "By default every hole reuses the signature waveform unchanged. "
        "Enable this to rescale each hole's amplitude for a different "
        "charge weight and/or distance than the signature shot, using the "
        "USBM scaled-distance law."
    )

    scaling_enabled = st.checkbox(
        "Enable charge weight & distance scaling (USBM)",
        value=False,
        key="sha_scaling_enabled",
    )

    with st.expander("ℹ️ About USBM Scaling", expanded=scaling_enabled):
        st.markdown(
            r"""
The signature hole recording captures the wave from **one** charge weight
at **one** distance. If a simulated hole uses a different charge weight,
or the whole pattern sits at a different distance from the monitor than
the signature shot, its amplitude can be rescaled using the USBM
square-root scaled-distance law (Duvall & Petkof):

$$PPV = K \left(\dfrac{D}{\sqrt{W}}\right)^{-B}$$

Rearranged into a per-hole **amplitude scale factor** applied to the
recorded signature waveform ($K$ cancels out — we're scaling a measured
wave, not predicting PPV from a blank page):

$$\text{scale} = \left(\dfrac{W_{hole} / W_{sig}}{\text{distance\_ratio}^{2}}\right)^{0.5B}$$

- **$W_{hole}$** — charge weight of the hole being simulated (kg)
- **$W_{sig}$** — charge weight of the recorded signature hole (kg)
- **distance_ratio** — $D_{hole} / D_{sig}$. Applied once for the whole
  pattern, not per hole — see note below.
- **$B$** (Field Constant) — your site's attenuation exponent from a
  prior PPV-vs-scaled-distance regression (e.g. the **Attenuation & Safe
  Zone** page). This is **not** calculated from the signature wave itself
  — you need to already have it from historical monitoring data at your
  site.

**What this does and doesn't fix:** this only rescales amplitude — it
assumes the scaled hole produces the *same-shaped* waveform (same
frequency content, same duration), just bigger or smaller. That holds
reasonably well for moderate charge-weight differences at a similar
distance. It gets less reliable the further the scaled charge weight is
from the signature charge, since ground attenuates high frequencies
faster than low frequencies over distance — a genuinely farther hole
should physically arrive lower-frequency and more spread out, not just
"the same wave, smaller." Distance here only scales overall amplitude,
not the frequency shift. It also doesn't account for different rock/
geology along different holes' propagation paths. Treat scaled results
as an engineering approximation, not an exact prediction — and be more
cautious the larger the scale factor is.
            """
        )

    signature_weight_kg = 1.0
    distance_ratio = 1.0
    field_constant = 1.6
    hole_weights_kg = None

    if scaling_enabled:
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            signature_weight_kg = st.number_input(
                "Signature Hole Charge Weight (kg)",
                min_value=0.01, value=1.0, step=0.1,
                key="sha_sig_weight",
                help="Charge weight of the hole this recording came from.",
            )
        with sc2:
            distance_ratio = st.number_input(
                "Distance Ratio (pattern / signature)",
                min_value=0.01, value=1.0, step=0.05,
                key="sha_distance_ratio",
                help="D_hole ÷ D_signature. 1.0 = pattern is at the same "
                     "distance from the monitor as the signature shot.",
            )
        with sc3:
            field_constant = st.number_input(
                "Field Constant (B)",
                min_value=0.0, value=1.6, step=0.1,
                key="sha_field_constant",
                help="Site-specific attenuation exponent from your own "
                     "PPV-vs-scaled-distance regression. Not derived here.",
            )

        weight_mode = st.radio(
            "Hole charge weight",
            ["Same weight for every hole", "Different weight per hole"],
            horizontal=True,
            key="sha_weight_mode",
        )

        if weight_mode == "Different weight per hole":
            st.caption(
                f"Enter charge weight (kg) for each of the {num_holes} hole "
                "positions. Same weights are reused for every row."
            )
            default_weights_df = pd.DataFrame({
                "Hole": list(range(1, int(num_holes) + 1)),
                "Charge Weight (kg)": [signature_weight_kg] * int(num_holes),
            })
            edited_weights_df = st.data_editor(
                default_weights_df,
                hide_index=True,
                use_container_width=True,
                key="sha_hole_weights_editor",
                column_config={
                    "Hole": st.column_config.NumberColumn(disabled=True),
                    "Charge Weight (kg)": st.column_config.NumberColumn(
                        min_value=0.01, step=0.1
                    ),
                },
            )
            hole_weights_kg = edited_weights_df["Charge Weight (kg)"].tolist()

        # Warn if the resulting scale factors span a wide range — this is
        # exactly where the same-waveform-shape assumption above gets shaky.
        from core.scaling import usbm_scale_factor
        weights_to_check = hole_weights_kg if hole_weights_kg else [signature_weight_kg]
        computed_scales = [
            usbm_scale_factor(w, signature_weight_kg, distance_ratio, field_constant)
            for w in weights_to_check
        ]
        min_scale, max_scale = min(computed_scales), max(computed_scales)
        if max_scale > 3.0 or (min_scale > 0 and min_scale < (1 / 3)):
            st.warning(
                f"⚠️ Computed scale factors range from {min_scale:.2f}× to "
                f"{max_scale:.2f}× the signature waveform. Large scale "
                "factors are where the same-waveform-shape assumption is "
                "weakest — treat results at these holes with extra caution."
            )
        else:
            st.caption(f"Computed scale factor range: {min_scale:.2f}× – {max_scale:.2f}×")

    st.divider()

    # ── STEP 3 — Run Simulation ────────────────────────────────────────────────
    st.markdown("## Step 3 — Run the Simulation")

    # ── Block selector (only shown for dual-block files) ──────────────────────
    has_block2 = 'Vertical B2 (mm/s)' in df.columns
    if has_block2:
        block_choice = st.radio(
            "Geophone block to use as signature hole",
            ["Block 1", "Block 2"],
            horizontal=True,
        )
        sfx = ' B2' if block_choice == "Block 2" else ''
    else:
        sfx = ''

    if st.button("▶ Run Simulation", type="primary"):
        waveform = {
            'Vert': df[f'Vertical{sfx} (mm/s)'].values[start_idx:end_idx],
            'Long': df[f'Longitudinal{sfx} (mm/s)'].values[start_idx:end_idx],
            'Tran': df[f'Transversal{sfx} (mm/s)'].values[start_idx:end_idx],
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
            scaling_enabled=scaling_enabled,
            signature_weight_kg=float(signature_weight_kg),
            distance_ratio=float(distance_ratio),
            field_constant=float(field_constant),
            hole_weights_kg=hole_weights_kg,
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

    # ── Frequency Band Analysis ────────────────────────────────────────
        st.subheader("📊 Best Results by Frequency Band")
        st.caption("Minimum Peak Vector Sum within each dominant frequency range. Band assigned using PPV-weighted average frequency — each channel's frequency is weighted by its PPV, so the dominant axis drives the result.")

        freq_bands = [
            ("0 – 4 Hz",    0,   4),
            ("4 – 16 Hz",   4,  16),
            ("16 – 64 Hz",  16, 64),
            ("64 – 250 Hz", 64, 250),
        ]

        results_df = results_df.copy()

        band_rows = []
        for label, f_low, f_high in freq_bands:
            mask = (results_df['Freq Vector Sum (Hz)'] >= f_low) & (results_df['Freq Vector Sum (Hz)'] < f_high)
            band_df = results_df[mask]
            if band_df.empty:
                band_rows.append({
                    'Frequency Band': label,
                    'Hole Delay (ms)': '—',
                    'Row Delay (ms)': '—',
                    'PPV Vert (mm/s)': '—',
                    'PPV Long (mm/s)': '—',
                    'PPV Tran (mm/s)': '—',
                    'Peak Vector Sum (mm/s)': '—',
                    'Freq Vector Sum (Hz)': '—',
                    'Count in Band': 0,
                })
            else:
                best_row = band_df.loc[band_df['Peak Vector Sum (mm/s)'].idxmin()]
                band_rows.append({
                    'Frequency Band': label,
                    'Hole Delay (ms)': int(best_row['Hole Delay (ms)']),
                    'Row Delay (ms)': int(best_row['Row Delay (ms)']),
                    'PPV Vert (mm/s)': f"{best_row['PPV Vert (mm/s)']:.2f}",
                    'PPV Long (mm/s)': f"{best_row['PPV Long (mm/s)']:.2f}",
                    'PPV Tran (mm/s)': f"{best_row['PPV Tran (mm/s)']:.2f}",
                    'Peak Vector Sum (mm/s)': f"{best_row['Peak Vector Sum (mm/s)']:.2f}",
                    'Freq Vector Sum (Hz)': f"{best_row['Freq Vector Sum (Hz)']:.2f}",
                    'Count in Band': len(band_df),
                })

        band_summary_df = pd.DataFrame(band_rows)
        st.dataframe(band_summary_df, use_container_width=True, hide_index=True)

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
                'Freq Vector Sum (Hz)': '{:.2f}',
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

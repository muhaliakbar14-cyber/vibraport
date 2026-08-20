# pages/sha.py
"""
Signature Hole Analysis page — blast timing optimization.

NOTE ON HISTORY: this page previously existed but was never wired up —
app.py had its own independent inline copy of SHA (with an st.form
rerun-reduction fix, but no frequency-band analysis and no charge-weight/
distance scaling). Step 1 below is ported directly from that live inline
implementation (kept as-is, since it's the version already field-tested
against real .sis files — see memory-bank/decisions.md for the
ms-unit-mismatch bug that was fixed there).

STEP ORDER NOTE: Step 2 (scaling) renders BEFORE Step 3 (blast design
parameters), even though scaling is visually/conceptually a sub-step of
blast design. This is required by Streamlit's form mechanics, not a
stylistic choice — see the comment above Step 2's render code for why.
"""

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from config import SimulationConfig
from core.scaling import usbm_scale_factor
from optimizer.delay_scan import build_delay_grid, scan


def render(df, time_axis, sampling_rate):
    st.title("💥 Signature Hole Analysis")
    st.caption("Simulate blast timing combinations using the uploaded signature hole waveform.")
    st.divider()

    # ── STEP 1 — Truncate Waveform ─────────────────────────────────────────────
    # time_axis is expected in MILLISECONDS here (the app-wide convention —
    # see app.py's _parse_uploaded_file), matching the previously-live logic
    # this was ported from.
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

    # Preview block selector — only shown for dual-geophone (Block 2) files.
    has_block2 = 'Vertical B2 (mm/s)' in df.columns
    if has_block2:
        preview_block = st.radio(
            "Preview block",
            ["Block 1", "Block 2"],
            horizontal=True,
            key='sha_preview_block',
        )
        sfx_preview = ' B2' if preview_block == "Block 2" else ''
    else:
        sfx_preview = ''

    trunc_channels = {
        f'Vertical{sfx_preview} (mm/s)': '#00897B',
        f'Longitudinal{sfx_preview} (mm/s)': '#E53935',
        f'Transversal{sfx_preview} (mm/s)': '#5C6BC0',
    }
    trunc_channels = {ch: color for ch, color in trunc_channels.items() if ch in df.columns}

    fig_trunc = make_subplots(
        rows=len(trunc_channels), cols=1,
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
            row=i + 1, col=1
        )
    fig_trunc.update_layout(height=600, margin=dict(t=50, b=50), hovermode="x unified")
    for annotation in fig_trunc.layout.annotations:
        annotation.update(font=dict(size=15, color="black", family="Arial Black, Arial, sans-serif"))
    st.plotly_chart(fig_trunc, use_container_width=True)
    st.caption(f"Selected window: {t_start} ms to {t_end} ms — {len(truncated_time)} data points")

    st.divider()

    # ── STEP 2 — Charge Weight & Distance Scaling (optional) ────────────────────
    # Deliberately OUTSIDE any st.form: form-wrapped widgets don't push their
    # value to Python until the form is submitted, so a checkbox inside a form
    # can't drive an immediate conditional reveal — the reveal would only
    # happen a run later, after "Run Simulation" is pressed. Everything in
    # this section is live/reactive on purpose so ticking the checkbox (or
    # switching the weight-mode radio) reveals its fields right away. That
    # does mean these specific widgets re-run the whole script (including
    # redrawing Step 1's chart above) on every change — accepted trade-off,
    # confirmed with the user, scoped to just this section. Step 3's 10 blast
    # design fields below stay form-wrapped, which is where the rerun cost
    # actually mattered.
    #
    # Rendered BEFORE Blast Design Parameters (not after, despite the numbering
    # implied by "Step 2.5" in earlier drafts) because num_holes — needed if
    # this were positioned after Blast Design Parameters — lives inside that
    # form and wouldn't be current here until submit anyway. The per-hole
    # weight table below is deliberately decoupled from num_holes entirely
    # (dynamic add/remove rows) so this ordering constraint doesn't recreate
    # the same staleness problem in a different spot.
    st.markdown("## Step 2 — Charge Weight & Distance Scaling (optional)")
    st.caption(
        "By default every hole reuses the signature waveform unchanged. "
        "Enable this to rescale each hole's amplitude for a different "
        "charge weight and/or distance than the signature shot, using "
        "the USBM scaled-distance law."
    )

    scaling_enabled = st.checkbox(
        "Enable charge weight & distance scaling (USBM)",
        value=False,
        key="sha_scaling_enabled",
    )

    with st.expander("ℹ️ About USBM Scaling", expanded=False):
        st.markdown(
            r"""
The signature hole recording captures the wave from **one** charge weight
at **one** distance. If a simulated hole uses a different charge weight,
or the pattern sits at a different distance from the monitor than the
signature shot, its amplitude can be rescaled using the USBM square-root
scaled-distance law (Duvall & Petkof):

$$PPV = K \left(\dfrac{D}{\sqrt{W}}\right)^{-B}$$

**Why there's no $K$ input here:** $K$ is a site constant, and it cancels
out when you take the ratio of two PPVs *at the same site* — which is
exactly what a scale factor is (predicted hole PPV ÷ recorded signature
PPV). Working through the ratio:

$$\frac{PPV_{hole}}{PPV_{sig}} = \left(\frac{D_{sig}}{D_{hole}}\right)^{B} \left(\frac{W_{hole}}{W_{sig}}\right)^{B/2}$$

$K$ never appears — it only matters if you're predicting an *absolute*
PPV from a blank page (that's what the regression on the **Attenuation &
Safe Zone** page produces both $K$ and $B$ for). Here we're rescaling an
*already-measured* waveform, which already has $K$'s effect baked in, so
only the ratios of weight and distance matter.

Rearranged into the per-hole **amplitude scale factor** actually applied
to the recorded signature waveform below:

$$\text{scale} = \left(\dfrac{W_{hole} / W_{sig}}{(D_{hole}/D_{sig})^{2}}\right)^{0.5B}$$

- **$W_{sig}$**, **$D_{sig}$** — charge weight and distance of the
  recorded signature hole.
- **$W_{hole}$**, **$D_{hole}$** — charge weight and distance of the hole
  you're simulating. If every hole in the pattern uses the same charge
  and the monitor is roughly the same distance from the whole pattern,
  one "blast pattern" value covers all holes; otherwise enter per-hole
  weights below.
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
    blast_pattern_weight_kg = 1.0
    signature_distance_m = 1.0
    blast_pattern_distance_m = 1.0
    field_constant = 1.6
    hole_weights_kg = None
    weight_mode = "Same weight for every hole"

    if scaling_enabled:
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            signature_weight_kg = st.number_input(
                "Signature Hole Charge Weight (kg)",
                min_value=0.01, value=1.0, step=0.1,
                key="sha_sig_weight",
                help="Charge weight of the hole this recording came from.",
            )
            signature_distance_m = st.number_input(
                "Signature Hole Distance (m)",
                min_value=0.01, value=1.0, step=1.0,
                key="sha_sig_distance",
                help="Distance from the signature hole to the monitor.",
            )
        with r1c2:
            field_constant = st.number_input(
                "Field Constant (B)",
                min_value=0.0, value=1.6, step=0.1,
                key="sha_field_constant",
                help="Site-specific attenuation exponent from your own "
                     "PPV-vs-scaled-distance regression. Not derived here.",
            )
            blast_pattern_distance_m = st.number_input(
                "Blast Pattern Distance (m)",
                min_value=0.01, value=1.0, step=1.0,
                key="sha_pattern_distance",
                help="Distance from the pattern you're simulating to the "
                     "monitor. Applied to every hole in the pattern — see "
                     "'About USBM Scaling' above.",
            )

        weight_mode = st.radio(
            "Hole charge weight",
            ["Same weight for every hole", "Different weight per hole"],
            horizontal=True,
            key="sha_weight_mode",
        )

        if weight_mode == "Same weight for every hole":
            blast_pattern_weight_kg = st.number_input(
                "Blast Pattern Charge Weight (kg)",
                min_value=0.01, value=1.0, step=0.1,
                key="sha_pattern_weight",
                help="Charge weight per hole in the pattern you're "
                     "simulating. Not required to match the signature "
                     "hole's charge weight above.",
            )
        else:
            st.caption(
                "One row per hole, in order (row 1 = first hole to fire "
                "within its delay group, and so on). Use the **+** row "
                "at the bottom of the table to add holes, or select a row "
                "and press delete to remove one — this must match "
                "'Number of Holes per Row' in Blast Design Parameters "
                "below when you run the simulation."
            )
            default_weights_df = pd.DataFrame({
                "Charge Weight (kg)": [signature_weight_kg] * 5,
            })
            edited_weights_df = st.data_editor(
                default_weights_df,
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                key="sha_hole_weights_editor",
                column_config={
                    "Charge Weight (kg)": st.column_config.NumberColumn(
                        min_value=0.01, step=0.1
                    ),
                },
            )
            hole_weights_kg = edited_weights_df["Charge Weight (kg)"].dropna().tolist()
            st.caption(f"{len(hole_weights_kg)} hole weight(s) entered.")

        # Warn if the resulting scale factors span a wide range — this is
        # exactly where the same-waveform-shape assumption above gets shaky.
        # Fully live, so this updates as you type, not just after Run.
        distance_ratio_preview = blast_pattern_distance_m / signature_distance_m
        weights_to_check = hole_weights_kg if hole_weights_kg else [blast_pattern_weight_kg]
        computed_scales = [
            usbm_scale_factor(w, signature_weight_kg, distance_ratio_preview, field_constant)
            for w in weights_to_check
        ]
        if computed_scales:
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

    # ── STEP 3 + 4 ────────────────────────────────────────────────────────────
    # Wrapped in st.form: none of these 10 inputs trigger a rerun (or re-render
    # Step 1's truncation chart above) until "Run Simulation" is pressed —
    # this is the rerun-reduction fix from the previously-live version, and
    # the actual expensive case it targets (the other 10 fields have no
    # bearing on the scaling section above, so keeping them debounced doesn't
    # cost anything there).
    st.markdown("## Step 3 — Blast Design Parameters")
    with st.form("sha_blast_params_form"):
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
        st.caption(
            f"Will simulate **{len(hole_delays)}** inter-hole delays × "
            f"**{len(row_delays)}** inter-row delays = **{total_combos:,}** "
            "total combinations. (Updates after you press Run — form inputs "
            "don't trigger live reruns.)"
        )

        st.divider()

        # ── STEP 4 — Run Simulation ──────────────────────────────────────────
        st.markdown("## Step 4 — Run the Simulation")

        has_block2_sim = 'Vertical B2 (mm/s)' in df.columns
        if has_block2_sim:
            block_choice = st.radio(
                "Geophone block to use as signature hole",
                ["Block 1", "Block 2"],
                horizontal=True,
            )
            sfx = ' B2' if block_choice == "Block 2" else ''
        else:
            sfx = ''

        simulate_btn = st.form_submit_button("▶ Run Simulation", type="primary")

    if simulate_btn and scaling_enabled and weight_mode == "Different weight per hole" \
            and hole_weights_kg is not None and len(hole_weights_kg) != num_holes:
        st.error(
            f"⚠️ The per-hole charge weight table has {len(hole_weights_kg)} "
            f"row(s), but 'Number of Holes per Row' above is set to "
            f"{num_holes}. Add or remove rows in Step 2's table so they "
            "match, then press Run Simulation again."
        )
    elif simulate_btn:
        waveform = {
            'Vert': df[f'Vertical{sfx} (mm/s)'].values[start_idx:end_idx],
            'Long': df[f'Longitudinal{sfx} (mm/s)'].values[start_idx:end_idx],
            'Tran': df[f'Transversal{sfx} (mm/s)'].values[start_idx:end_idx],
        }

        distance_ratio = (
            blast_pattern_distance_m / signature_distance_m
            if scaling_enabled else 1.0
        )
        weight_for_uniform = (
            [blast_pattern_weight_kg] * num_holes
            if scaling_enabled and weight_mode == "Same weight for every hole"
            else hole_weights_kg
        )

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
            hole_weights_kg=weight_for_uniform,
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

        # ── Frequency Band Analysis ──────────────────────────────────────────
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

# pages/report.py
"""
PDF Report Generation page — exports a professional measurement report
covering Recording Info, Measurement Summary, Signal Analysis, and
(if available) Attenuation & SNI 7571 compliance results.

reportlab is imported lazily inside _build_pdf() so this module can be
imported even when the package is not yet installed.  The ImportError
only surfaces when the user actually clicks Generate PDF.
"""

from __future__ import annotations

import io
import math
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core import calculate_frequency, detect_equipment_model
from core.waveform import parse_sis_file, parse_file
from core.sni_chart import build_sni_chart
from core.sni_chart import SNI_LIMITS
from config import DEFAULT_FREQUENCY_METHOD, LOW_AMPLITUDE_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════════
# Streamlit page entry point
# ══════════════════════════════════════════════════════════════════════════════

def render(df, time_axis, metadata, sampling_rate,
           ppv_registry=None, uploaded_files_dict=None):
    st.title("Vibraport PDF Report")
    st.caption("Generate a professional measurement report for the active recording.")
    st.divider()

    st.subheader("Report Options")
    col1, col2 = st.columns(2)
    with col1:
        project_name = st.text_input("Project / Site Name", value="")
        operator = st.text_input("Prepared by", value="")
    with col2:
        client_name = st.text_input("Client / Company", value="")
        report_notes = st.text_area("Additional Notes (optional)", height=68, value="")

    file_names = []
    if uploaded_files_dict:
        file_names = list(uploaded_files_dict.keys())
    active_name = metadata.get("_filename") if metadata else None
    if active_name and active_name not in file_names:
        file_names.insert(0, active_name)

    if file_names:
        selected_files = st.multiselect(
            "Files to include in report",
            options=file_names,
            default=[active_name] if active_name else [file_names[0]],
        )
    else:
        selected_files = [active_name] if active_name else []

    st.markdown("**Include sections:**")
    c1, c2, c3 = st.columns(3)
    inc_records = c1.checkbox("Records summary (multi-file)", value=len(selected_files) > 1)
    inc_ad = c2.checkbox("Acceleration + Displacement", value=False)
    inc_fft = c3.checkbox("FFT Analysis", value=False)

    class_options = {
        'Class 1 - Highly sensitive / heritage buildings':         1,
        'Class 2 - Sensitive / simple residential buildings':      2,
        'Class 3 - Standard residential buildings':                3,
        'Class 4 - Reinforced residential / commercial buildings': 4,
        'Class 5 - Heavy industrial / critical infrastructure':    5,
    }
    sni_class_label = st.selectbox(
        "SNI 7571 Infrastructure Class", list(class_options.keys()), index=2
    )
    sni_class = class_options[sni_class_label]

    st.divider()

    if st.button("Generate PDF Report", type="primary"):
        options = dict(
            project_name=project_name,
            operator=operator,
            client_name=client_name,
            report_notes=report_notes,
            inc_records=inc_records,
            inc_ad=inc_ad,
            inc_fft=inc_fft,
            sni_class=sni_class,
        )
        try:
            with st.spinner("Building PDF..."):
                files = _build_report_files(
                    selected_files,
                    active=(df, time_axis, metadata, sampling_rate),
                    uploaded_files_dict=uploaded_files_dict or {},
                )
                pdf_bytes = _build_vibraport_pdf(files, options)
        except ImportError as e:
            st.error(
                f"Missing dependency: {e}. "
                "Run `pip install reportlab kaleido` in your environment, then restart Streamlit."
            )
            return

        filename = (active_name or 'recording').replace('.', '_')
        st.success("Report ready!")
        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes,
            file_name=f"vibraport_report_{filename}.pdf",
            mime="application/pdf",
        )


# ══════════════════════════════════════════════════════════════════════════════
# PDF builder  — ALL reportlab imports are inside this function
# ══════════════════════════════════════════════════════════════════════════════

def _build_pdf(df, time_axis, metadata, sampling_rate, options: dict) -> bytes:
    # Lazy imports — only executed when user clicks Generate
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, Image as RLImage, Flowable,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    PAGE_W, PAGE_H = A4
    MARGIN = 18 * mm
    usable = PAGE_W - 2 * MARGIN

    def cw(*fracs):
        return [usable * f for f in fracs]

    # Colours
    C_HEAD  = rl_colors.HexColor('#1A237E')
    C_SUBH  = rl_colors.HexColor('#3949AB')
    C_LIGHT = rl_colors.HexColor('#E8EAF6')
    C_WARN  = rl_colors.HexColor('#FFF3E0')
    C_OK    = rl_colors.HexColor('#E8F5E9')
    C_FAIL  = rl_colors.HexColor('#FFEBEE')

    # Styles
    base = getSampleStyleSheet()
    def P(name, **kw):
        return ParagraphStyle(name, parent=base['Normal'], **kw)

    S = {
        'title':       P('vtitle',    fontSize=20, fontName='Helvetica-Bold', textColor=C_HEAD, spaceAfter=4),
        'section':     P('vsect',     fontSize=13, fontName='Helvetica-Bold', textColor=C_SUBH, spaceBefore=6, spaceAfter=3),
        'subsection':  P('vsubsect',  fontSize=10, fontName='Helvetica-Bold', textColor=C_HEAD, spaceBefore=4, spaceAfter=2),
        'body':        P('vbody',     fontSize=9,  leading=13),
        'small':       P('vsmall',    fontSize=8,  leading=11),
        'small_grey':  P('vsmgrey',   fontSize=7.5, textColor=rl_colors.grey, leading=10),
        'th':          P('vth',       fontSize=8.5, fontName='Helvetica-Bold', textColor=rl_colors.white, alignment=TA_CENTER),
        'td':          P('vtd',       fontSize=8.5, leading=11),
        'td_c':        P('vtd_c',     fontSize=8.5, leading=11, alignment=TA_CENTER),
        'caption':     P('vcaption',  fontSize=8,  textColor=rl_colors.HexColor('#555555'), alignment=TA_CENTER, spaceAfter=4),
        'ok':          P('vok',       fontSize=10, fontName='Helvetica-Bold', textColor=rl_colors.HexColor('#1B5E20')),
        'fail':        P('vfail',     fontSize=10, fontName='Helvetica-Bold', textColor=rl_colors.HexColor('#B71C1C')),
    }

    def base_ts(head_color=None):
        cmds = [
            ('GRID',          (0, 0), (-1, -1), 0.3, rl_colors.HexColor('#BBBBBB')),
            ('TOPPADDING',    (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING',   (0, 0), (-1, -1), 5),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 5),
        ]
        if head_color:
            cmds.insert(0, ('BACKGROUND', (0, 0), (-1, 0), head_color))
        return cmds

    # Page header/footer drawn on every page
    def page_frame(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_HEAD)
        canvas.rect(MARGIN, PAGE_H - MARGIN - 8 * mm,
                    PAGE_W - 2 * MARGIN, 8 * mm, fill=1, stroke=0)
        canvas.setFillColor(rl_colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(MARGIN + 3 * mm, PAGE_H - MARGIN - 5.5 * mm, "VIBRAPORT")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(PAGE_W - MARGIN - 3 * mm,
                               PAGE_H - MARGIN - 5.5 * mm,
                               "Vibration Measurement Report")
        canvas.setFillColor(rl_colors.HexColor('#555555'))
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(PAGE_W / 2, MARGIN / 2, f"Page {doc.page}")
        canvas.restoreState()

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Vibration Measurement Report", S['title']))
    story.append(HRFlowable(width="100%", thickness=2, color=C_HEAD))
    story.append(Spacer(1, 3 * mm))

    serial = metadata.get('Serial number', '-')
    model  = detect_equipment_model(serial)
    for row_data in [
        ["Project / Site", options.get('project_name') or '-', "Equipment",  model],
        ["Client",         options.get('client_name')  or '-', "Serial No.", serial],
        ["Prepared by",    options.get('operator')     or '-', "Date",       metadata.get('Date', '-')],
        ["File",           metadata.get('_filename', '-'),      "Time",       metadata.get('Time', '-')],
    ]:
        pass  # built below
    cover_data = [
        [Paragraph(f"<b>{r[0]}</b>", S['td']), Paragraph(str(r[1]), S['td']),
         Paragraph(f"<b>{r[2]}</b>", S['td']), Paragraph(str(r[3]), S['td'])]
        for r in [
            ["Project / Site", options.get('project_name') or '-', "Equipment",  model],
            ["Client",         options.get('client_name')  or '-', "Serial No.", serial],
            ["Prepared by",    options.get('operator')     or '-', "Date",       metadata.get('Date', '-')],
            ["File",           metadata.get('_filename', '-'),      "Time",       metadata.get('Time', '-')],
        ]
    ]
    tbl_cover = Table(cover_data, colWidths=cw(0.18, 0.32, 0.18, 0.32))
    tbl_cover.setStyle(TableStyle(base_ts() + [
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [rl_colors.white, C_LIGHT]),
    ]))
    story.append(tbl_cover)
    story.append(Spacer(1, 6 * mm))

    # ── Section 1: Recording Overview ─────────────────────────────────────────
    if options['inc_overview']:
        story.append(Paragraph("1. Recording Overview", S['section']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_SUBH))
        story.append(Spacer(1, 2 * mm))

        info_items = [
            ("Record Type",   metadata.get('Record type', '-')),
            ("Sampling Rate", metadata.get('Sampling rate', '-')),
            ("Record Length", metadata.get('Record length', '-')),
            ("Pretrigger",    metadata.get('Pretrigger', '-')),
            ("Calibration",   metadata.get('Calibration date', '-')),
            ("Clock Source",  metadata.get('Clock source', '-')),
        ]
        gps = metadata.get('GPS source', 'Not set')
        lat = metadata.get('Latitude')
        lon = metadata.get('Longitude')
        info_items.append(("GPS", f"{lat:.6f}, {lon:.6f}" if gps != 'Not set' and lat else "Not set"))
        for i in range(1, 4):
            n = metadata.get(f'Note {i}', '')
            if n:
                info_items.append((f"Note {i}", n))

        info_rows = []
        for j in range(0, len(info_items), 2):
            left  = info_items[j]
            right = info_items[j + 1] if j + 1 < len(info_items) else ('', '')
            info_rows.append([
                Paragraph(f"<b>{left[0]}</b>",  S['td']),
                Paragraph(str(left[1]),           S['td']),
                Paragraph(f"<b>{right[0]}</b>",  S['td']),
                Paragraph(str(right[1]),           S['td']),
            ])
        tbl_info = Table(info_rows, colWidths=cw(0.18, 0.32, 0.18, 0.32))
        tbl_info.setStyle(TableStyle(base_ts() + [
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [rl_colors.white, C_LIGHT]),
        ]))
        story.append(tbl_info)

        # Measurement Summary
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Measurement Summary", S['subsection']))
        sum_rows = _build_summary_rows(df, time_axis, sampling_rate, metadata)
        sum_headers = ["Channel", "Block", "PPV", "Frequency", "Transducer", "Geophone Test"]
        sum_data = [[Paragraph(h, S['th']) for h in sum_headers]]
        sum_ts   = TableStyle(base_ts(C_HEAD) + [
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_LIGHT]),
        ])
        for i, row in enumerate(sum_rows, start=1):
            ppv_clean = row['PPV'].replace(' ⚠️', '')
            sum_data.append([
                Paragraph(row['Channel'],    S['td']),
                Paragraph(row['Block'],      S['td_c']),
                Paragraph(ppv_clean,         S['td_c']),
                Paragraph(row['Frequency'],  S['td_c']),
                Paragraph(row['Transducer'], S['td']),
                Paragraph(row['Test'],       S['td']),
            ])
            if '\u26a0' in row.get('PPV', ''):
                sum_ts.add('BACKGROUND', (0, i), (-1, i), C_WARN)
        tbl_sum = Table(sum_data, colWidths=cw(0.20, 0.08, 0.16, 0.16, 0.22, 0.18))
        tbl_sum.setStyle(sum_ts)
        story.append(tbl_sum)

        vector_sum = metadata.get('Vector sum', {})
        pvs_parts = []
        if (vector_sum.get("ch1_3") or 0) > 0:
            pvs_parts.append(f"Block 1 = <b>{vector_sum['ch1_3']:.2f} mm/s</b>")
        if (vector_sum.get("ch4_6") or 0) > 0:
            pvs_parts.append(f"Block 2 = <b>{vector_sum['ch4_6']:.2f} mm/s</b>")
        if pvs_parts:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph("Peak Vector Sum:  " + "    |    ".join(pvs_parts), S['small']))

        # Waveform chart
        vel_cfg = [
            ('Vertical (mm/s)',        '#00897B', 'Vertical'),
            ('Longitudinal (mm/s)',    '#E53935', 'Longitudinal'),
            ('Transversal (mm/s)',     '#5C6BC0', 'Transversal'),
            ('Vertical B2 (mm/s)',     '#26A69A', 'Vertical B2'),
            ('Longitudinal B2 (mm/s)', '#EF9A9A', 'Longitudinal B2'),
            ('Transversal B2 (mm/s)',  '#9FA8DA', 'Transversal B2'),
        ]
        active_vel = [(col, c, lbl) for col, c, lbl in vel_cfg if col in df.columns]
        if active_vel:
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("Velocity Waveform", S['subsection']))
            time_ms = time_axis * 1000
            nv = len(active_vel)
            fig_wf = make_subplots(rows=nv, cols=1, shared_xaxes=True,
                                   subplot_titles=[lbl for _, _, lbl in active_vel],
                                   vertical_spacing=0.06)
            for i, (col, color, lbl) in enumerate(active_vel, start=1):
                sig = df[col].values
                fig_wf.add_trace(go.Scatter(x=time_ms, y=sig, mode='lines',
                                            line=dict(color=color, width=1),
                                            showlegend=False), row=i, col=1)
                pk = int(np.abs(sig).argmax())
                fig_wf.add_trace(go.Scatter(
                    x=[time_ms[pk]], y=[sig[pk]], mode='markers+text',
                    marker=dict(color='red', size=7, symbol='square'),
                    text=[f" {abs(sig[pk]):.2f}"], textposition='middle right',
                    textfont=dict(size=9, color='red'), showlegend=False,
                ), row=i, col=1)
            tick_v = list(range(0, int(time_ms[-1]) + 100, 100))
            fig_wf.update_xaxes(tickvals=tick_v, title_text="Time (ms)", row=nv, col=1)
            fig_wf.update_layout(height=180 * nv, showlegend=False,
                                  margin=dict(t=30, b=40, l=55, r=20), font=dict(size=10))
            for ann in fig_wf.layout.annotations:
                ann.update(font=dict(size=10))
            img_wf_bytes = fig_wf.to_image(format='png', width=720, height=180 * nv, scale=2)
            story.append(RLImage(io.BytesIO(img_wf_bytes),
                                 width=usable, height=usable * (180 * nv / 720)))
            story.append(Paragraph("Figure 1 - Velocity waveform with peak markers.", S['caption']))

    # ── Section 2: Signal Analysis ─────────────────────────────────────────────
    if options['inc_signal']:
        story.append(PageBreak())
        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph("2. Signal Analysis", S['section']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_SUBH))
        story.append(Spacer(1, 2 * mm))

        vel_cols = [c for c in df.columns if '(mm/s)' in c and 'A_' not in c and 'D_' not in c]
        if vel_cols:
            story.append(Paragraph("Frequency Analysis", S['subsection']))
            channel_info = (metadata or {}).get('Channel info', [])
            vel_ch_map = {}
            if channel_info:
                vel_idx = [i for i, ch in enumerate(channel_info)
                           if 'Velocity' in ch.get('magnitude', '') and not ch.get('is_virtual')]
                for j, col in enumerate(vel_cols):
                    if j < len(vel_idx):
                        vel_ch_map[col] = channel_info[vel_idx[j]]

            freq_headers = ["Channel", "Zero Crossing", "FFT Peak",
                            "Energy 25%", "Energy 50%", "Energy 75%"]
            freq_data = [[Paragraph(h, S['th']) for h in freq_headers]]
            for col in vel_cols:
                ppv  = df[col].abs().max()
                warn = ' *' if ppv < LOW_AMPLITUDE_THRESHOLD else ''
                lbl  = col.replace(' (mm/s)', '') + warn
                ch   = vel_ch_map.get(col)
                if ch:
                    freq_data.append([
                        Paragraph(lbl,                              S['td']),
                        Paragraph(f"{ch['freq_zero_crossing']} Hz", S['td_c']),
                        Paragraph(f"{ch['freq_fft_peak']} Hz",      S['td_c']),
                        Paragraph(f"{ch['freq_energy_25']} Hz",     S['td_c']),
                        Paragraph(f"{ch['freq_energy_50']} Hz",     S['td_c']),
                        Paragraph(f"{ch['freq_energy_75']} Hz",     S['td_c']),
                    ])
                else:
                    sig = tuple(df[col].values)
                    freq_data.append([
                        Paragraph(lbl, S['td']),
                        Paragraph(f"{calculate_frequency(sig, sampling_rate, 'Zero Crossing')} Hz", S['td_c']),
                        Paragraph(f"{calculate_frequency(sig, sampling_rate, 'FFT Peak')} Hz",      S['td_c']),
                        Paragraph(f"{calculate_frequency(sig, sampling_rate, 'Energy 25%')} Hz",    S['td_c']),
                        Paragraph(f"{calculate_frequency(sig, sampling_rate, 'Energy 50%')} Hz",    S['td_c']),
                        Paragraph(f"{calculate_frequency(sig, sampling_rate, 'Energy 75%')} Hz",    S['td_c']),
                    ])
            tbl_freq = Table(freq_data, colWidths=cw(0.25, 0.15, 0.15, 0.15, 0.15, 0.15))
            tbl_freq.setStyle(TableStyle(base_ts(C_HEAD) + [
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_LIGHT]),
            ]))
            story.append(tbl_freq)
            story.append(Spacer(1, 1 * mm))
            story.append(Paragraph("* Low amplitude - frequency estimate may be unreliable.", S['small_grey']))

            # FFT chart
            story.append(Spacer(1, 4 * mm))
            story.append(Paragraph("FFT Spectrum (0-200 Hz)", S['subsection']))
            COLOR_MAP = {
                'Vertical (mm/s)': '#00897B', 'Longitudinal (mm/s)': '#E53935',
                'Transversal (mm/s)': '#5C6BC0',
            }
            n_samp  = len(df)
            fig_fft = go.Figure()
            for col in vel_cols:
                sig     = df[col].values
                fft_mag = np.abs(np.fft.rfft(sig)) / n_samp
                freqs   = np.fft.rfftfreq(n_samp, d=1 / sampling_rate)
                mask    = freqs <= 200
                fig_fft.add_trace(go.Scatter(
                    x=freqs[mask], y=fft_mag[mask],
                    name=col.replace(' (mm/s)', ''),
                    mode='lines', line=dict(color=COLOR_MAP.get(col, '#888888'), width=1.2),
                ))
            fig_fft.update_layout(
                xaxis_title="Frequency (Hz)", yaxis_title="Amplitude (mm/s)",
                height=300, margin=dict(t=20, b=50, l=55, r=20),
                legend=dict(orientation='h', y=-0.3), font=dict(size=10),
            )
            img_fft_bytes = fig_fft.to_image(format='png', width=720, height=300, scale=2)
            story.append(RLImage(io.BytesIO(img_fft_bytes),
                                 width=usable, height=usable * (300 / 720)))
            story.append(Paragraph("Figure 2 - FFT amplitude spectrum (0-200 Hz).", S['caption']))

    # ── Section 3: SNI 7571:2023 ───────────────────────────────────────────────
    if options['inc_sni']:
        story.append(PageBreak())
        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph("3. SNI 7571:2023 Compliance Assessment", S['section']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_SUBH))
        story.append(Spacer(1, 2 * mm))

        sni_class = options['sni_class']
        class_labels = {
            1: "Class 1 - Highly sensitive / heritage buildings",
            2: "Class 2 - Sensitive / simple residential buildings",
            3: "Class 3 - Standard residential buildings",
            4: "Class 4 - Reinforced residential / commercial buildings",
            5: "Class 5 - Heavy industrial / critical infrastructure",
        }
        story.append(Paragraph(
            f"Infrastructure class: <b>{class_labels[sni_class]}</b>", S['body']
        ))
        story.append(Spacer(1, 2 * mm))

        limits = SNI_LIMITS[sni_class]
        ch_map = [
            ('Vertical (mm/s)',        'Vertical',        1),
            ('Longitudinal (mm/s)',    'Longitudinal',    1),
            ('Transversal (mm/s)',     'Transversal',     1),
            ('Vertical B2 (mm/s)',     'Vertical B2',     2),
            ('Longitudinal B2 (mm/s)', 'Longitudinal B2', 2),
            ('Transversal B2 (mm/s)',  'Transversal B2',  2),
        ]
        sni_headers = ["Channel", "Block", "PPV (mm/s)", "Freq (Hz)", "Limit (mm/s)", "Result"]
        sni_data  = [[Paragraph(h, S['th']) for h in sni_headers]]
        sni_ts    = TableStyle(base_ts(C_HEAD))
        row_bgs   = {}

        for col, ch_name, block in ch_map:
            if col not in df.columns:
                continue
            ppv    = float(df[col].abs().max())
            freq   = float(calculate_frequency(tuple(df[col].values), sampling_rate, DEFAULT_FREQUENCY_METHOD))
            seg    = 0 if freq < 5 else (1 if freq < 20 else 2)
            lim    = limits[seg]
            passed = ppv <= lim
            ri     = len(sni_data)
            row_bgs[ri] = C_OK if passed else C_FAIL
            sni_data.append([
                Paragraph(ch_name,           S['td']),
                Paragraph(str(block),         S['td_c']),
                Paragraph(f"{ppv:.2f}",       S['td_c']),
                Paragraph(f"{freq:.1f}",      S['td_c']),
                Paragraph(f"{lim:.0f}",       S['td_c']),
                Paragraph(f"<b>{'PASS' if passed else 'FAIL'}</b>", S['td_c']),
            ])
        for ri, bg in row_bgs.items():
            sni_ts.add('BACKGROUND', (0, ri), (-1, ri), bg)
        tbl_sni = Table(sni_data, colWidths=cw(0.20, 0.08, 0.17, 0.17, 0.17, 0.21))
        tbl_sni.setStyle(sni_ts)
        story.append(tbl_sni)

        story.append(Spacer(1, 3 * mm))
        all_pass = all(bg == C_OK for bg in row_bgs.values()) if row_bgs else True
        story.append(Paragraph(
            ("All channels COMPLY with " if all_pass else "One or more channels EXCEED the limit for ")
            + class_labels[sni_class] + ".",
            S['ok'] if all_pass else S['fail']
        ))

        # Limit reference
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("SNI 7571:2023 PPV Limit Reference (mm/s)", S['subsection']))
        all_limits = {1:[2,3,5], 2:[3,5,7], 3:[5,7,12], 4:[7,12,20], 5:[12,24,40]}
        ref_data = [[Paragraph(h, S['th'])
                     for h in ["Frequency Band", "Cl.1", "Cl.2", "Cl.3", "Cl.4", "Cl.5"]]]
        for fi, band in enumerate(["0-5 Hz", "5-20 Hz", "20-100 Hz"]):
            row = [Paragraph(band, S['td'])]
            for c in range(1, 6):
                val = all_limits[c][fi]
                row.append(Paragraph(f"<b>{val}</b>" if c == sni_class else str(val), S['td_c']))
            ref_data.append(row)
        tbl_ref = Table(ref_data, colWidths=cw(0.28, 0.144, 0.144, 0.144, 0.144, 0.144))
        tbl_ref.setStyle(TableStyle(base_ts(C_HEAD) + [
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_LIGHT]),
            ('BACKGROUND', (sni_class, 0), (sni_class, -1), rl_colors.HexColor('#7986CB')),
        ]))
        story.append(tbl_ref)

    # ── Section 4: Attenuation ─────────────────────────────────────────────────
    if options['inc_ppv'] and options.get('ppv_fit'):
        fit = options['ppv_fit']
        K, n_exp, K_conf, r = fit['K'], fit['n'], fit['K_conf'], fit['r']

        story.append(PageBreak())
        story.append(Spacer(1, 10 * mm))
        story.append(Paragraph("4. Attenuation and Safe Zone", S['section']))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_SUBH))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("Regression Model: PPV = K x (D / sqrt(Q)) ^ n", S['subsection']))
        story.append(Spacer(1, 2 * mm))

        param_data = [
            [Paragraph(h, S['th']) for h in ["Parameter", "Regression Line", "95% Confidence Line"]],
            [Paragraph("K (intercept)",   S['td']), Paragraph(str(K),     S['td_c']), Paragraph(str(K_conf), S['td_c'])],
            [Paragraph("n (exponent)",    S['td']), Paragraph(str(n_exp), S['td_c']), Paragraph(str(n_exp), S['td_c'])],
            [Paragraph("Formula",         S['td']),
             Paragraph(f"PPV = {K} x SD^{n_exp}",      S['td_c']),
             Paragraph(f"PPV = {K_conf} x SD^{n_exp}", S['td_c'])],
            [Paragraph("Correlation (r)", S['td']), Paragraph(str(r), S['td_c']), Paragraph("-", S['td_c'])],
        ]
        tbl_param = Table(param_data, colWidths=cw(0.30, 0.35, 0.35))
        tbl_param.setStyle(TableStyle(base_ts(C_HEAD) + [
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_LIGHT]),
        ]))
        story.append(tbl_param)
        story.append(Spacer(1, 1 * mm))
        story.append(Paragraph(
            "The 95% confidence line is recommended for safety assessments.",
            S['small_grey']
        ))

        ppv_table = options.get('ppv_table')
        if ppv_table is not None and len(ppv_table) > 0:
            data = ppv_table.copy()
            data = data[(data['Charge (kg)'] > 0) & (data['Distance (m)'] > 0)]
            if not data.empty:
                story.append(Spacer(1, 4 * mm))
                story.append(Paragraph("Blast Event Data", S['subsection']))
                blast_headers = ["No.", "Source", "Blk", "Charge (kg)",
                                 "Dist. (m)", "SD", "Vert", "Long", "Tran"]
                blast_data = [[Paragraph(h, S['th']) for h in blast_headers]]
                for _, row in data.iterrows():
                    q  = row['Charge (kg)']
                    d  = row['Distance (m)']
                    sd = d / math.sqrt(q)
                    blast_data.append([
                        Paragraph(str(int(row.get('No.', 0))),         S['td_c']),
                        Paragraph(str(row['Source'])[:24],              S['td']),
                        Paragraph(str(int(row.get('Block', 1))),        S['td_c']),
                        Paragraph(f"{q:.1f}",                           S['td_c']),
                        Paragraph(f"{d:.1f}",                           S['td_c']),
                        Paragraph(f"{sd:.1f}",                          S['td_c']),
                        Paragraph(f"{row['Vertical (mm/s)']:.2f}",     S['td_c']),
                        Paragraph(f"{row['Longitudinal (mm/s)']:.2f}", S['td_c']),
                        Paragraph(f"{row['Transversal (mm/s)']:.2f}",  S['td_c']),
                    ])
                tbl_blast = Table(blast_data, colWidths=cw(0.05, 0.22, 0.05, 0.10, 0.09, 0.09, 0.133, 0.133, 0.134))
                tbl_blast.setStyle(TableStyle(base_ts(C_HEAD) + [
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, C_LIGHT]),
                    ('FONTSIZE',      (0, 0), (-1, -1), 7.5),
                    ('TOPPADDING',    (0, 0), (-1, -1), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ]))
                story.append(tbl_blast)

    # ── Footer ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=rl_colors.grey))
    story.append(Spacer(1, 2 * mm))
    if options.get('report_notes'):
        story.append(Paragraph(f"<b>Notes:</b> {options['report_notes']}", S['small']))
        story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Generated by <b>Vibraport</b> - independent vibration analysis tool. "
        "Not affiliated with Vibracord or its manufacturers.",
        S['small_grey']
    ))

    # ── Build PDF ──────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title="Vibraport Measurement Report",
        author=options.get('operator', 'Vibraport'),
    )
    doc.build(story, onFirstPage=page_frame, onLaterPages=page_frame)
    buf.seek(0)
    return buf.read()


def _parse_any_file(file_bytes: bytes, filename: str):
    if filename and filename.lower().endswith(".sis"):
        return parse_sis_file(file_bytes)
    return parse_file(file_bytes)


def _build_report_files(selected_files, active, uploaded_files_dict):
    files = []
    if active and selected_files:
        df, time_axis, metadata, sampling_rate = active
        meta_name = metadata.get("_filename") if metadata else None
        if meta_name in selected_files:
            files.append({
                "name": meta_name,
                "df": df,
                "time_axis": time_axis,
                "metadata": metadata,
                "sampling_rate": sampling_rate,
            })
    for name in selected_files:
        if files and any(f["name"] == name for f in files):
            continue
        b = uploaded_files_dict.get(name)
        if not b:
            continue
        metadata, df, time_axis, sampling_rate = _parse_any_file(b, name)
        metadata["_filename"] = name
        files.append({
            "name": name,
            "df": df,
            "time_axis": time_axis,
            "metadata": metadata,
            "sampling_rate": sampling_rate,
        })
    return files


def _record_values_from_df(df, time_axis, sampling_rate, metadata):
    rows = []
    time_ms = time_axis * 1000
    channel_info = (metadata or {}).get("Channel info", [])

    def _freq_for(axis, block, magnitude="Velocity"):
        for ch in channel_info or []:
            if ch.get("magnitude") != magnitude:
                continue
            if ch.get("belongs_to_block", 1) != block:
                continue
            ax = ch.get("axis")
            if axis in (ax, "Transversal") and ax in ("Transverse", "Transversal"):
                return ch.get("freq_energy_50") or ch.get("freq_fft_peak") or ch.get("freq_zero_crossing")
            if ax == axis or (axis == "Vertical" and ax == "X") or (axis == "Longitudinal" and ax == "Y") or (axis == "Transversal" and ax == "Z"):
                return ch.get("freq_energy_50") or ch.get("freq_fft_peak") or ch.get("freq_zero_crossing")
        return None

    col_map = [
        ("Vertical (mm/s)", "Vertical", 1),
        ("Longitudinal (mm/s)", "Longitudinal", 1),
        ("Transversal (mm/s)", "Transversal", 1),
        ("Vertical B2 (mm/s)", "Vertical", 2),
        ("Longitudinal B2 (mm/s)", "Longitudinal", 2),
        ("Transversal B2 (mm/s)", "Transversal", 2),
    ]
    for col, axis, block in col_map:
        if col not in df.columns:
            continue
        sig = df[col].values
        idx = int(abs(sig).argmax())
        rows.append({
            "channel": f"{axis}{' B2' if block == 2 else ''}",
            "max": float(abs(sig[idx])),
            "time_ms": float(time_ms[idx]),
            "freq": _freq_for(axis, block),
        })

    pa_col = next((c for c in df.columns if "(Pa)" in c), None)
    if pa_col:
        sig = df[pa_col].values
        idx = int(abs(sig).argmax())
        rows.append({
            "channel": "Air Pressure",
            "max": float(abs(sig[idx])),
            "time_ms": float(time_ms[idx]),
            "freq": _freq_for("Pressure", 1, magnitude="Pressure"),
        })

    return rows


def _ppv_points_from_metadata(metadata, df, sampling_rate):
    points = []
    channel_info = (metadata or {}).get("Channel info", [])
    if channel_info:
        for ch in channel_info:
            if ch.get("magnitude") != "Velocity":
                continue
            axis = ch.get("axis")
            block = ch.get("belongs_to_block", 1)
            axis_norm = "Transversal" if axis in ("Transverse", "Transversal", "Z") else axis
            if axis_norm in ("X", "Vertical"):
                ch_name = "Vertical"
            elif axis_norm in ("Y", "Longitudinal"):
                ch_name = "Longitudinal"
            elif axis_norm in ("Z", "Transversal"):
                ch_name = "Transversal"
            else:
                continue
            if block == 2:
                ch_name = f"{ch_name} B2"
            ppv = ch.get("max_amplitude")
            freq = ch.get("freq_energy_50") or ch.get("freq_fft_peak") or ch.get("freq_zero_crossing")
            if ppv is None or freq is None:
                continue
            points.append({"channel": ch_name, "ppv": float(ppv), "freq": float(freq), "block": block})
    if points:
        return points

    # fallback from df
    from core import calculate_frequency
    col_map = [
        ("Vertical (mm/s)", "Vertical", 1),
        ("Longitudinal (mm/s)", "Longitudinal", 1),
        ("Transversal (mm/s)", "Transversal", 1),
        ("Vertical B2 (mm/s)", "Vertical B2", 2),
        ("Longitudinal B2 (mm/s)", "Longitudinal B2", 2),
        ("Transversal B2 (mm/s)", "Transversal B2", 2),
    ]
    for col, ch_name, block in col_map:
        if col not in df.columns:
            continue
        sig = df[col].values
        ppv = float(abs(sig).max())
        freq = float(calculate_frequency(tuple(sig), sampling_rate, DEFAULT_FREQUENCY_METHOD))
        points.append({"channel": ch_name, "ppv": ppv, "freq": freq, "block": block})
    return points


def _build_vibraport_pdf(files, options: dict) -> bytes:
    import os
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import Table, TableStyle, Paragraph, Image as RLImage
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    PAGE_W, PAGE_H = A4
    MARGIN = 14 * mm
    HEADER_H = 12 * mm
    FOOTER_H = 10 * mm
    usable_w = PAGE_W - 2 * MARGIN
    body_top = PAGE_H - MARGIN - HEADER_H - 4
    body_bottom = MARGIN + FOOTER_H + 4

    base = getSampleStyleSheet()
    def P(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    body_font = "Helvetica"
    title_font = "Helvetica-Bold"
    try:
        font_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "fonts"))
        pdfmetrics.registerFont(TTFont("Montserrat Regular", os.path.join(font_dir, "Montserrat-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("GEOMETR415 BLK BT BLACK", os.path.join(font_dir, "GEOMETR415-BLK-BT.ttf")))
        body_font = "Montserrat Regular"
        title_font = "GEOMETR415 BLK BT BLACK"
    except Exception:
        pass

    S = {
        "title": P("rt_title", fontSize=14, fontName=title_font, alignment=TA_CENTER),
        "section": P("rt_sect", fontSize=11, fontName=title_font),
        "small": P("rt_small", fontSize=8, fontName=body_font),
        "td": P("rt_td", fontSize=8, fontName=body_font),
        "td_c": P("rt_td_c", fontSize=8, fontName=body_font, alignment=TA_CENTER),
        "th": P("rt_th", fontSize=8, fontName=title_font, alignment=TA_CENTER),
        "td_sm": P("rt_td_sm", fontSize=7, fontName=body_font),
        "td_c_sm": P("rt_td_c_sm", fontSize=7, fontName=body_font, alignment=TA_CENTER),
        "th_sm": P("rt_th_sm", fontSize=7, fontName=title_font, alignment=TA_CENTER),
    }

    def base_ts(head_color=None):
        cmds = [
            ("GRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#BBBBBB")),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        if head_color:
            cmds.insert(0, ("BACKGROUND", (0, 0), (-1, 0), head_color))
        return cmds

    def draw_header_footer(c, file_name: str, page_title: str, page_num: int):
        header_y = PAGE_H - MARGIN + 2
        footer_y = MARGIN - 6
        company = options.get("project_name") or ""
        c.setFont(title_font, 9)
        c.drawString(MARGIN, header_y, company)
        c.setFont(title_font, 8)
        if file_name:
            c.drawRightString(PAGE_W - MARGIN, header_y, file_name)
        if page_title:
            c.drawRightString(PAGE_W - MARGIN, header_y - 10, page_title)
        c.setStrokeColor(rl_colors.black)
        c.setLineWidth(0.6)
        c.line(MARGIN, PAGE_H - MARGIN - 10, PAGE_W - MARGIN, PAGE_H - MARGIN - 10)
        c.setFont(title_font, 8)
        c.drawString(MARGIN, footer_y, "VIBRAPORT by ABDIYASA")
        c.drawRightString(PAGE_W - MARGIN, footer_y, f"Page {page_num}")
        c.line(MARGIN, MARGIN + 6, PAGE_W - MARGIN, MARGIN + 6)

    def draw_table(c, table: Table, x, y_top):
        w, h = table.wrap(0, 0)
        table.drawOn(c, x, y_top - h)
        return h

    def draw_title(c, text, y_top):
        c.setFont(title_font, 14)
        c.drawCentredString(PAGE_W / 2, y_top, text)
        return y_top - 14 - 6

    page_num = 1
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # Records summary page (multi-file)
    if options.get("inc_records") and len(files) > 1:
        draw_header_footer(c, "Multiple files", "Records summary", page_num)
        y = draw_title(c, "Records summary", body_top)
        headers = ["No", "File / Serial / Date Time", "Note", "Time Location", "Record values"]
        data = [[Paragraph(h, S["th"]) for h in headers]]
        for i, f in enumerate(files, start=1):
            meta = f["metadata"]
            rec_vals = _record_values_from_df(f["df"], f["time_axis"], f["sampling_rate"], meta)
            rec_txt = "<br/>".join(
                [f"C{idx+1}: {r['max']:.2f} ({r['freq']} Hz)" if r.get("freq") is not None else f"C{idx+1}: {r['max']:.2f}"
                 for idx, r in enumerate(rec_vals)]
            )
            vs = meta.get("Vector sum", {})
            if vs and (vs.get("ch1_3") or 0) > 0:
                rec_txt += f"<br/>PVS1: {vs.get('ch1_3'):.2f} mm/s"
            row = [
                Paragraph(str(i), S["td_c"]),
                Paragraph(f"{meta.get('_filename','-')}<br/>{meta.get('Serial number','-')}<br/>{meta.get('Date','-')} {meta.get('Time','-')}", S["td"]),
                Paragraph(meta.get("Note 1", "-") or "-", S["td"]),
                Paragraph(meta.get("Record length", "-"), S["td_c"]),
                Paragraph(rec_txt or "-", S["td"]),
            ]
            data.append(row)
        tbl = Table(data, colWidths=[usable_w * f for f in (0.06, 0.28, 0.18, 0.12, 0.36)])
        tbl.setStyle(TableStyle(base_ts(rl_colors.HexColor("#E0E0E0")) + [
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F7F7F7")]),
        ]))
        draw_table(c, tbl, MARGIN, y)
        c.showPage()
        page_num += 1

    # Per-file pages
    for idx, f in enumerate(files, start=1):
        meta = f["metadata"]
        df = f["df"]
        time_axis = f["time_axis"]
        sps = f["sampling_rate"]

        # Data summary page
        draw_header_footer(c, meta.get("_filename", ""), "Data summary", page_num)
        y = draw_title(c, "Data summary", body_top)

        left = [
            ("Equipment", meta.get("Equipment", "-")),
            ("Serial number", meta.get("Serial number", "-")),
            ("Date of calibration", meta.get("Calibration date", "-")),
            ("Note 1", meta.get("Note 1", "-") or "-"),
            ("Note 2", meta.get("Note 2", "-") or "-"),
            ("Note 3", meta.get("Note 3", "-") or "-"),
        ]
        right = [
            ("Record", meta.get("_filename", "-")),
            ("Date & Time", f"{meta.get('Date','-')} {meta.get('Time','-')}"),
            ("Pretrigger", meta.get("Pretrigger", "-")),
            ("Longitude", meta.get("Longitude", "-") or "-"),
            ("Latitude", meta.get("Latitude", "-") or "-"),
            ("Time Source", meta.get("Clock source", "-")),
        ]
        info_rows = []
        for i in range(len(left)):
            info_rows.append([
                Paragraph(f"<b>{left[i][0]}</b>", S["td"]),
                Paragraph(str(left[i][1]), S["td"]),
                Paragraph(f"<b>{right[i][0]}</b>", S["td"]),
                Paragraph(str(right[i][1]), S["td"]),
            ])
        info_tbl = Table(info_rows, colWidths=[usable_w * f for f in (0.22, 0.28, 0.22, 0.28)])
        info_tbl.setStyle(TableStyle(base_ts() + [
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F5F5F5")]),
        ]))
        y -= draw_table(c, info_tbl, MARGIN, y) + 14

        c.setFont(title_font, 12)
        c.drawCentredString(PAGE_W / 2, y - 2, "Velocity (mm/s)")
        y -= 12

        bottom_block_h = 72 * mm
        wave_bottom = body_bottom + bottom_block_h + 8
        wave_top = y - 4
        wave_h = max(40 * mm, wave_top - wave_bottom)

        vel_cfg = [
            ("Vertical (mm/s)", "#00897B", "Vertical"),
            ("Longitudinal (mm/s)", "#E53935", "Longitudinal"),
            ("Transversal (mm/s)", "#5C6BC0", "Transversal"),
            ("Vertical B2 (mm/s)", "#26A69A", "Vertical B2"),
            ("Longitudinal B2 (mm/s)", "#EF9A9A", "Longitudinal B2"),
            ("Transversal B2 (mm/s)", "#9FA8DA", "Transversal B2"),
        ]
        active_vel = [(col, c, lbl) for col, c, lbl in vel_cfg if col in df.columns]
        if active_vel:
            time_ms = time_axis * 1000
            nv = len(active_vel)
            fig_wf = make_subplots(rows=nv, cols=1, shared_xaxes=True,
                                   subplot_titles=[lbl for _, _, lbl in active_vel],
                                   vertical_spacing=0.06)
            for i2, (col, color, lbl) in enumerate(active_vel, start=1):
                sig = df[col].values
                fig_wf.add_trace(go.Scatter(x=time_ms, y=sig, mode="lines",
                                            line=dict(color=color, width=1), showlegend=False),
                                 row=i2, col=1)
            tick_v = list(range(0, int(time_ms[-1]) + 100, 100))
            fig_wf.update_xaxes(tickvals=tick_v, row=nv, col=1)
            fig_wf.update_layout(height=max(200, int(200 * nv)), margin=dict(t=70, b=30, l=40, r=20), font=dict(size=9))
            for ann in fig_wf.layout.annotations:
                ann.update(yshift=16)
            img_wf_bytes = fig_wf.to_image(format="png", width=1200, height=max(200, int(200 * nv)), scale=2)
            img_wf = RLImage(io.BytesIO(img_wf_bytes), width=usable_w, height=wave_h)
            img_wf.drawOn(c, MARGIN, wave_bottom)

        # Record values + SNI chart
        rec_vals = _record_values_from_df(df, time_axis, sps, meta)
        if rec_vals:
            left_w = usable_w * 0.45
            right_w = usable_w - left_w
            c.setFont(title_font, 10)
            c.drawCentredString(MARGIN + (left_w * 0.5), body_bottom + bottom_block_h + 6, "Record Values")
            rv_headers = ["Channel", "Maximum", "Time", "Frequency"]
            rv_data = [[Paragraph(h, S["th_sm"]) for h in rv_headers]]
            for r in rec_vals:
                rv_data.append([
                    Paragraph(str(r["channel"]), S["td_sm"]),
                    Paragraph(f"{r['max']:.2f}", S["td_c_sm"]),
                    Paragraph(f"{r['time_ms']:.1f} ms", S["td_c_sm"]),
                    Paragraph(f"{r['freq']} Hz" if r.get("freq") is not None else "-", S["td_c_sm"]),
                ])
            row_h = max(10, (bottom_block_h) / max(1, len(rv_data)))
            rv_tbl = Table(
                rv_data,
                colWidths=[left_w * 0.38, left_w * 0.22, left_w * 0.20, left_w * 0.20],
                rowHeights=[row_h] * len(rv_data),
            )
            rv_tbl.setStyle(TableStyle(base_ts(rl_colors.HexColor("#E0E0E0"))))
            rv_h = draw_table(c, rv_tbl, MARGIN, body_bottom + bottom_block_h - 8)

            ppv_points = _ppv_points_from_metadata(meta, df, sps)
            if ppv_points:
                c.setFont(title_font, 10)
                c.drawCentredString(MARGIN + left_w + (right_w * 0.5), body_bottom + bottom_block_h + 6, "SNI 7571:2023")
                fig_sni = build_sni_chart(ppv_points)
                fig_sni.update_layout(
                    height=300,
                    width=420,
                    margin=dict(t=10, b=60, l=40, r=20),
                    legend=dict(orientation="h", y=-0.38, x=0, font=dict(size=8)),
                    yaxis_title_standoff=14,
                )
                sni_img = fig_sni.to_image(format="png", width=420, height=300, scale=2)
                sni_h = min(bottom_block_h * 0.94, rv_h)
                sni_w = right_w * 0.88
                sni_x = MARGIN + left_w + (right_w - sni_w)
                sni_y = body_bottom + bottom_block_h - sni_h - 8
                sni_img_rl = RLImage(io.BytesIO(sni_img), width=sni_w, height=sni_h)
                sni_img_rl.drawOn(c, sni_x, sni_y)
                c.setLineWidth(0.6)
                c.rect(sni_x, sni_y, sni_w, sni_h)

        c.showPage()
        page_num += 1

        if options.get("inc_ad"):
            draw_header_footer(c, meta.get("_filename", ""), "Derivative + Integration", page_num)
            y = body_top
            acc_cols = [c for c in df.columns if c.startswith("A_")]
            disp_cols = [c for c in df.columns if c.startswith("D_")]
            color_map = {
                "A_Vert": "#00897B",
                "A_Long": "#E53935",
                "A_Tran": "#5C6BC0",
                "D_Vert": "#00897B",
                "D_Long": "#E53935",
                "D_Tran": "#5C6BC0",
            }
            half_h = (body_top - body_bottom - 24) / 2
            if acc_cols:
                c.setFont(title_font, 11)
                c.drawCentredString(PAGE_W / 2, body_top - 12, "Acceleration (Derivative)")
                fig_a = make_subplots(rows=len(acc_cols), cols=1, shared_xaxes=True,
                                      subplot_titles=acc_cols, vertical_spacing=0.12)
                for i2, col in enumerate(acc_cols, start=1):
                    key = col.split(" ")[0]
                    fig_a.add_trace(go.Scatter(x=time_axis*1000, y=df[col].values, mode="lines",
                                               line=dict(color=color_map.get(key, "#E53935"), width=1),
                                               showlegend=False),
                                    row=i2, col=1)
                fig_a_h = max(200, int(140 * len(acc_cols)))
                fig_a.update_layout(height=fig_a_h, margin=dict(t=60, b=20, l=40, r=20), font=dict(size=9))
                for ann in fig_a.layout.annotations:
                    ann.update(yshift=20)
                img_a = fig_a.to_image(format="png", width=1000, height=fig_a_h, scale=2)
                img_a_h = min(half_h, usable_w * (fig_a_h / 1000))
                RLImage(io.BytesIO(img_a), width=usable_w, height=img_a_h).drawOn(
                    c, MARGIN, body_bottom + half_h + (half_h - img_a_h) / 2 + 6
                )
            if disp_cols:
                c.setFont(title_font, 11)
                c.drawCentredString(PAGE_W / 2, body_bottom + half_h - 8, "Displacement (Integration)")
                fig_d = make_subplots(rows=len(disp_cols), cols=1, shared_xaxes=True,
                                      subplot_titles=disp_cols, vertical_spacing=0.12)
                for i2, col in enumerate(disp_cols, start=1):
                    key = col.split(" ")[0]
                    fig_d.add_trace(go.Scatter(x=time_axis*1000, y=df[col].values, mode="lines",
                                               line=dict(color=color_map.get(key, "#1E88E5"), width=1),
                                               showlegend=False),
                                    row=i2, col=1)
                fig_d_h = max(200, int(140 * len(disp_cols)))
                fig_d.update_layout(height=fig_d_h, margin=dict(t=60, b=20, l=40, r=20), font=dict(size=9))
                for ann in fig_d.layout.annotations:
                    ann.update(yshift=20)
                img_d = fig_d.to_image(format="png", width=1000, height=fig_d_h, scale=2)
                img_d_h = min(half_h, usable_w * (fig_d_h / 1000))
                RLImage(io.BytesIO(img_d), width=usable_w, height=img_d_h).drawOn(
                    c, MARGIN, body_bottom + (half_h - img_d_h) / 2
                )
            c.showPage()
            page_num += 1

        if options.get("inc_fft"):
            draw_header_footer(c, meta.get("_filename", ""), "FFT Analysis", page_num)
            y = draw_title(c, "FFT Analysis", body_top)
            vel_cols = [c for c in df.columns if "(mm/s)" in c and "A_" not in c and "D_" not in c]
            if vel_cols:
                n_samp = len(df)
                color_map = {
                    "Vertical (mm/s)": "#00897B",
                    "Longitudinal (mm/s)": "#E53935",
                    "Transversal (mm/s)": "#5C6BC0",
                }
                fig_fft = make_subplots(rows=len(vel_cols), cols=1, shared_xaxes=True,
                                        subplot_titles=[c.replace(" (mm/s)", "") for c in vel_cols],
                                        vertical_spacing=0.18)
                for i2, col in enumerate(vel_cols, start=1):
                    sig = df[col].values
                    fft_mag = np.abs(np.fft.rfft(sig)) / n_samp
                    freqs = np.fft.rfftfreq(n_samp, d=1 / sps)
                    mask = freqs <= 200
                    fig_fft.add_trace(go.Scatter(
                        x=freqs[mask], y=fft_mag[mask],
                        name=col.replace(" (mm/s)", ""),
                        mode="lines", line=dict(width=1.1, color=color_map.get(col, "#888888")),
                        showlegend=False,
                    ), row=i2, col=1)
                fig_fft_h = max(240, int(140 * len(vel_cols)))
                fig_fft.update_layout(
                    xaxis_title=None, yaxis_title=None,
                    height=fig_fft_h, margin=dict(t=60, b=40, l=40, r=20),
                    font=dict(size=9),
                )
                for ann in fig_fft.layout.annotations:
                    ann.update(yshift=24)
                img_fft = fig_fft.to_image(format="png", width=1000, height=fig_fft_h, scale=2)
                img_fft_h = min(body_top - body_bottom - 20, usable_w * (fig_fft_h / 1000))
                fft_y = body_top - img_fft_h - 4
                RLImage(io.BytesIO(img_fft), width=usable_w, height=img_fft_h).drawOn(
                    c, MARGIN, fft_y
                )
                c.setFont(title_font, 11)
                c.drawString(MARGIN + 4, fft_y + (img_fft_h * 0.53), "Amplitude")
                c.drawCentredString(PAGE_W / 2, fft_y - 12, "Frequency (Hz)")
            c.showPage()
            page_num += 1

    if options.get("report_notes"):
        draw_header_footer(c, "Notes", "Notes", page_num)
        c.setFont(body_font, 9)
        c.drawString(MARGIN, body_top, f"Notes: {options['report_notes']}")
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.read()


# ══════════════════════════════════════════════════════════════════════════════
# Helper: measurement summary rows
# ══════════════════════════════════════════════════════════════════════════════

def _build_summary_rows(df, time_axis, sampling_rate, metadata) -> list:
    rows = []
    channel_info  = metadata.get('Channel info', [])
    geophone_test = metadata.get('Geophone test', [])
    ch_lookup     = {ch['index']: ch for ch in channel_info} if channel_info else {}

    AXIS_MATCH = {
        'Vertical':     ('Vertical', 'X'),
        'Longitudinal': ('Longitudinal', 'Y'),
        'Transversal':  ('Transverse', 'Z'),
    }

    def find_idx(axis_label, block):
        valid = AXIS_MATCH.get(axis_label, (axis_label,))
        for idx, ch in ch_lookup.items():
            if ch['axis'] in valid and ch['belongs_to_block'] == block:
                return idx
        return None

    def get_info(ch_idx):
        if ch_idx is None or ch_idx not in ch_lookup:
            return '-', '-'
        ch = ch_lookup[ch_idx]
        transducer = ch.get('type', '-')
        if ch_idx <= 7 and geophone_test:
            tr   = geophone_test[ch_idx - 1]
            icon = 'OK' if tr == 'OK' else ('WARN' if tr == 'Not performed' else 'FAIL')
            return transducer, f"{icon}: {tr}"
        return transducer, '-'

    col_map = [
        ('Vertical (mm/s)',        'Vertical',     1),
        ('Longitudinal (mm/s)',    'Longitudinal', 1),
        ('Transversal (mm/s)',     'Transversal',  1),
        ('Vertical B2 (mm/s)',     'Vertical',     2),
        ('Longitudinal B2 (mm/s)', 'Longitudinal', 2),
        ('Transversal B2 (mm/s)',  'Transversal',  2),
    ]
    for col, axis, block in col_map:
        if col not in df.columns:
            continue
        ppv  = df[col].abs().max()
        freq = calculate_frequency(tuple(df[col].values), sampling_rate, DEFAULT_FREQUENCY_METHOD)
        idx  = find_idx(axis, block)
        trans, test = get_info(idx)
        warn     = ' !' if ppv < LOW_AMPLITUDE_THRESHOLD else ''
        ch_label = axis if 'B2' not in col else f"{axis} B2"
        rows.append({
            'Channel':    ch_label,
            'Block':      str(block),
            'PPV':        f"{ppv:.2f} mm/s{warn}",
            'Frequency':  f"{freq} Hz",
            'Transducer': trans,
            'Test':       test,
        })

    pa_col = next((c for c in df.columns if '(Pa)' in c), None)
    if pa_col:
        ppv  = df[pa_col].abs().max()
        freq = calculate_frequency(tuple(df[pa_col].values), sampling_rate, DEFAULT_FREQUENCY_METHOD)
        rows.append({'Channel': 'Air Pressure', 'Block': '-',
                     'PPV': f"{ppv:.2f} Pa", 'Frequency': f"{freq} Hz",
                     'Transducer': 'Microphone', 'Test': '-'})
    return rows

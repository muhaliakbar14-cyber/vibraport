# pages/report.py
"""
PDF Report Generation page — exports a professional measurement report
covering Recording Info, Measurement Summary, Signal Analysis, and
structural vibration compliance results.

reportlab is imported lazily inside _build_pdf() so this module can be
imported even when the package is not yet installed.  The ImportError
only surfaces when the user actually clicks Generate PDF.
"""

from __future__ import annotations

import io
import math
import concurrent.futures
import numpy as np
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core import calculate_frequency, detect_equipment_model
from core.waveform import parse_sis_file, parse_file
from core.sni_chart import build_sni_chart
from core.sni_chart import SNI_LIMITS
from core.compliance import (
    STANDARD_ORDER,
    STANDARDS,
    assessment_label,
    assessment_options,
    build_compliance_chart,
    category_options,
    chart_title,
    evaluate_point,
    evaluate_points,
    format_limit,
    measurement_basis,
    measurement_explanation,
    overall_status,
)
from config import DEFAULT_FREQUENCY_METHOD, LOW_AMPLITUDE_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════════
# Bounded Kaleido image export
# ══════════════════════════════════════════════════════════════════════════════
# fig.to_image() (Kaleido -> headless Chrome) has a long history of hanging
# indefinitely with zero error when Chrome fails to start/respond — common on
# Streamlit Community Cloud if Kaleido can't find a Chrome binary. There's no
# built-in timeout, so a stuck call previously meant "Generate PDF" spun
# forever with no feedback. We bound every export with a timeout and raise a
# real, catchable error instead. See requirements.txt for the matching
# kaleido version pin.

class ImageExportTimeoutError(RuntimeError):
    pass


_IMG_EXPORT_TIMEOUT_S = 25
_img_export_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="kaleido-export")


def _to_image(fig, **kwargs) -> bytes:
    future = _img_export_pool.submit(fig.to_image, **kwargs)
    try:
        return future.result(timeout=_IMG_EXPORT_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise ImageExportTimeoutError(
            f"Chart image export did not finish within {_IMG_EXPORT_TIMEOUT_S}s. "
            "This usually means Kaleido/Chrome failed to start in this environment "
            "— check the kaleido version pin in requirements.txt."
        )
    except Exception as exc:
        raise RuntimeError(f"Chart image export failed: {exc}") from exc


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

    st.markdown("**Compliance assessment:**")
    compliance_standard = st.selectbox(
        "Compliance Standard",
        options=STANDARD_ORDER,
        format_func=lambda value: STANDARDS[value].title,
        key="report_compliance_standard",
    )
    durations = assessment_options(compliance_standard)
    assessment = st.selectbox(
        "Assessment Duration",
        options=durations,
        format_func=assessment_label,
        disabled=len(durations) == 1,
        key=f"report_assessment_{compliance_standard}",
    )
    categories = category_options(compliance_standard)
    category_index = 2 if compliance_standard == "sni_7571_2023" else min(1, len(categories) - 1)
    compliance_category = st.selectbox(
        "Structure Category",
        options=[category.id for category in categories],
        index=category_index,
        format_func=lambda value: next(category.label for category in categories if category.id == value),
        key=f"report_category_{compliance_standard}",
    )
    st.caption(measurement_explanation(compliance_standard, assessment))

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
            compliance_standard=compliance_standard,
            compliance_assessment=assessment,
            compliance_category=compliance_category,
        )
        try:
            with st.spinner("Building PDF..."):
                files = _build_report_files(
                    selected_files,
                    active=(df, time_axis, metadata, sampling_rate),
                    uploaded_files_dict=uploaded_files_dict or {},
                )
                pdf_bytes = _build_vibraport_pdf(files, options)
        except ImageExportTimeoutError as e:
            st.error(
                f"⚠️ PDF generation timed out while rendering a chart: {e} "
                "If this keeps happening, it's very likely a Kaleido/Chrome "
                "problem in this deployment — see the comment above kaleido "
                "in requirements.txt."
            )
            return
        except ImportError as e:
            st.error(
                f"Missing dependency: {e}. "
                "Run `pip install reportlab kaleido` in your environment, then restart Streamlit."
            )
            return
        except RuntimeError as e:
            st.error(f"PDF chart rendering failed: {e}")
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
            img_wf_bytes = _to_image(fig_wf, format='png', width=720, height=180 * nv, scale=2)
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
            img_fft_bytes = _to_image(fig_fft, format='png', width=720, height=300, scale=2)
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
        metadata, df, time_axis_seconds, sampling_rate = parse_sis_file(file_bytes)
        # Report invariant: all time axes are milliseconds. app.py already
        # supplies the active file in milliseconds; the SIS parser returns
        # seconds for the additional selected files.
        return metadata, df, time_axis_seconds * 1000, sampling_rate
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
    # _build_report_files() guarantees milliseconds for every file.
    time_ms = time_axis
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
        frequency = _freq_for(axis, block)
        if frequency is None:
            frequency = calculate_frequency(tuple(sig), sampling_rate, DEFAULT_FREQUENCY_METHOD)
        rows.append({
            "channel": f"{axis}{' B2' if block == 2 else ''}",
            "max": float(abs(sig[idx])),
            "unit": "mm/s",
            "time_ms": float(time_ms[idx]),
            "freq": frequency,
        })

    pa_col = next((c for c in df.columns if "(Pa)" in c), None)
    if pa_col:
        sig = df[pa_col].values
        idx = int(abs(sig).argmax())
        frequency = _freq_for("Pressure", 1, magnitude="Pressure")
        if frequency is None:
            frequency = calculate_frequency(tuple(sig), sampling_rate, DEFAULT_FREQUENCY_METHOD)
        rows.append({
            "channel": "Air Pressure",
            "max": float(abs(sig[idx])),
            "unit": "Pa",
            "time_ms": float(time_ms[idx]),
            "freq": frequency,
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
    HEADER_H = 18 * mm
    FOOTER_H = 10 * mm
    usable_w = PAGE_W - 2 * MARGIN
    body_top = PAGE_H - MARGIN - HEADER_H - 4
    body_bottom = MARGIN + FOOTER_H + 4

    base = getSampleStyleSheet()
    def P(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    body_font = "Helvetica"
    title_font = "Helvetica-Bold"
    bold_font = "Helvetica-Bold"
    try:
        font_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "fonts"))
        pdfmetrics.registerFont(TTFont("Inter", os.path.join(font_dir, "Inter-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Inter SemiBold", os.path.join(font_dir, "Inter-SemiBold.ttf")))
        pdfmetrics.registerFont(TTFont("Inter Bold", os.path.join(font_dir, "Inter-Bold.ttf")))
        body_font = "Inter"
        title_font = "Inter SemiBold"
        bold_font = "Inter Bold"
    except Exception:
        pass

    S = {
        "title": P("rt_title", fontSize=13, fontName=title_font, alignment=TA_CENTER),
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

    def _clean_text(value):
        value = str(value or "").strip()
        return "" if value in ("", "-") else value

    def _nice_symmetric_limit(series):
        peak = max((float(np.max(np.abs(values))) for values in series if len(values)), default=1.0)
        if not np.isfinite(peak) or peak <= 0:
            return 1.0
        target = peak * 1.08
        exponent = math.floor(math.log10(target))
        fraction = target / (10 ** exponent)
        nice_fraction = next(v for v in (1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10) if fraction <= v)
        return nice_fraction * (10 ** exponent)

    def _style_signal_figure(fig, row_count, shared_limit, time_end_ms, title_unit):
        major_x = max(100.0, math.ceil((time_end_ms / 10.0) / 100.0) * 100.0)
        for row in range(1, row_count + 1):
            fig.update_yaxes(
                range=[-shared_limit, shared_limit],
                tickmode="linear", dtick=shared_limit / 2,
                showgrid=True, gridcolor="#B7BDC5", gridwidth=0.8,
                zeroline=True, zerolinecolor="#B7BDC5", zerolinewidth=0.8,
                linecolor="#59616A", linewidth=0.7,
                tickfont=dict(size=8),
                row=row, col=1,
            )
            fig.update_xaxes(
                tickmode="linear", dtick=major_x,
                showgrid=True, gridcolor="#C4C9D0", gridwidth=0.7,
                minor=dict(showgrid=True, dtick=major_x / 2, gridcolor="#E2E5E9"),
                linecolor="#59616A", linewidth=0.7,
                tickfont=dict(size=8),
                title_text="Time (ms)" if row == row_count else None,
                title_font=dict(size=9),
                row=row, col=1,
            )
        fig.update_layout(
            plot_bgcolor="white", paper_bgcolor="white",
            margin=dict(t=42, b=34, l=58, r=16),
            font=dict(size=8, color="#30343B"),
        )
        for ann in fig.layout.annotations:
            ann.update(x=0.01, xanchor="left", yshift=12, font=dict(size=9, color="#30343B"))
        return f"Shared scale: +/-{shared_limit:g} {title_unit}"

    compliance_standard = options.get("compliance_standard", "sni_7571_2023")
    compliance_assessment = options.get("compliance_assessment", "short_term")
    compliance_category = int(options.get("compliance_category", options.get("sni_class", 3)))
    compliance_spec = STANDARDS[compliance_standard]
    compliance_category_spec = next(
        category for category in category_options(compliance_standard)
        if category.id == compliance_category
    )
    compliance_heading = chart_title(compliance_standard, compliance_assessment)

    def draw_header_footer(c, metadata, page_num: int, total_pages: int):
        header_y = PAGE_H - MARGIN + 2
        footer_y = MARGIN - 6
        project = _clean_text(options.get("project_name"))
        c.setFillColor(rl_colors.black)
        c.setFont(title_font, 9)
        c.drawString(MARGIN, header_y, "VIBRAPORT")
        if project:
            c.setFont(body_font, 7)
            c.drawString(MARGIN, header_y - 10, f"Project: {project}")

        if metadata:
            note_lines = [_clean_text(metadata.get(f"Note {i}")) for i in range(1, 4)]
            note_lines = [line for line in note_lines if line]
            c.setFont(title_font, 7.5)
            for line_no, line in enumerate(note_lines[:3]):
                c.drawRightString(PAGE_W - MARGIN, header_y - (line_no * 9), line[:72])
        else:
            client = _clean_text(options.get("client_name"))
            if client:
                c.setFont(body_font, 7)
                c.drawRightString(PAGE_W - MARGIN, header_y, client)
        c.setStrokeColor(rl_colors.black)
        c.setLineWidth(0.6)
        c.line(MARGIN, PAGE_H - MARGIN - 22, PAGE_W - MARGIN, PAGE_H - MARGIN - 22)
        c.setFont(title_font, 8)
        c.drawString(MARGIN, footer_y, "VIBRAPORT by ABDIYASA")
        c.drawRightString(PAGE_W - MARGIN, footer_y, f"Page {page_num} of {total_pages}")
        c.line(MARGIN, MARGIN + 6, PAGE_W - MARGIN, MARGIN + 6)

    def draw_table(c, table: Table, x, y_top):
        w, h = table.wrap(0, 0)
        table.drawOn(c, x, y_top - h)
        return h

    def draw_title(c, text, y_top):
        c.setFillColor(rl_colors.black)
        c.setFont(title_font, 14)
        c.drawCentredString(PAGE_W / 2, y_top, text)
        return y_top - 14 - 6

    page_num = 1
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    total_pages = (1 if options.get("inc_records") and len(files) > 1 else 0)
    total_pages += len(files) * (1 + int(bool(options.get("inc_ad"))) + int(bool(options.get("inc_fft"))))
    c.setTitle(f"Vibraport Vibration Report - {options.get('project_name') or 'Measurement'}")
    c.setAuthor(options.get("operator") or "Vibraport")
    c.setSubject(
        f"Vibration measurement, waveform analysis, and {compliance_heading} compliance"
    )
    c.setCreator("Vibraport by ABDIYASA")

    # Records summary page (multi-file)
    if options.get("inc_records") and len(files) > 1:
        draw_header_footer(c, None, page_num, total_pages)
        y = draw_title(c, "Records summary", body_top)
        headers = ["No", "Record / Date & Time", "Source notes", "Duration", "Measurements", "Compliance"]
        data = [[Paragraph(h, S["th_sm"]) for h in headers]]
        for i, f in enumerate(files, start=1):
            meta = f["metadata"]
            rec_vals = _record_values_from_df(f["df"], f["time_axis"], f["sampling_rate"], meta)
            rec_txt = "<br/>".join([
                f"{r['channel']}: {r['max']:.2f} {r['unit']}"
                + (f" ({r['freq']:.0f} Hz)" if r.get("freq") is not None else "")
                for r in rec_vals
            ])
            vs = meta.get("Vector sum", {})
            if vs and (vs.get("ch1_3") or 0) > 0:
                rec_txt += f"<br/>PVS1: {vs.get('ch1_3'):.2f} mm/s"
            ppv_points = _ppv_points_from_metadata(
                meta, f["df"], f["sampling_rate"]
            )
            compliance_results = evaluate_points(
                ppv_points, compliance_standard, compliance_assessment, compliance_category
            )
            record_status = overall_status(compliance_results)
            source_notes = "<br/>".join(
                filter(None, (_clean_text(meta.get(f"Note {n}")) for n in range(1, 4)))
            ) or "-"
            row = [
                Paragraph(str(i), S["td_c_sm"]),
                Paragraph(f"{meta.get('_filename','-')}<br/>{meta.get('Date','-')} {meta.get('Time','-')}<br/>SN {meta.get('Serial number','-')}", S["td_sm"]),
                Paragraph(source_notes, S["td_sm"]),
                Paragraph(str(meta.get("Record length", "-")), S["td_c_sm"]),
                Paragraph(rec_txt or "-", S["td_sm"]),
                Paragraph(
                    f"{compliance_spec.title}<br/>{compliance_category_spec.short_label}"
                    f"<br/><b>{record_status}</b>",
                    S["td_c_sm"],
                ),
            ]
            data.append(row)
        tbl = Table(data, colWidths=[usable_w * f for f in (0.05, 0.23, 0.17, 0.10, 0.34, 0.11)])
        tbl.setStyle(TableStyle(base_ts(rl_colors.HexColor("#E0E0E0")) + [
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F7F7F7")]),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
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
        draw_header_footer(c, meta, page_num, total_pages)
        y = draw_title(c, "Data summary", body_top)

        left = [
            ("Equipment", meta.get("Equipment", "-")),
            ("Serial number", meta.get("Serial number", "-")),
            ("Date of calibration", meta.get("Calibration date", "-")),
            ("Sampling rate", meta.get("Sampling rate", f"{sps:g} sps")),
            ("Record length", meta.get("Record length", "-")),
            ("Prepared by", options.get("operator") or "-"),
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
            ("TOPPADDING", (0, 0), (-1, -1), 2.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ]))
        y -= draw_table(c, info_tbl, MARGIN, y) + 9

        compliance_note = Paragraph(
            f"<b>{compliance_heading} - {compliance_category_spec.short_label}:</b> "
            + measurement_explanation(compliance_standard, compliance_assessment),
            S["td_sm"],
        )
        note_w, note_h = compliance_note.wrap(usable_w - 10, 30)
        c.setFillColor(rl_colors.HexColor("#F2F4F7"))
        c.roundRect(MARGIN, y - note_h - 6, usable_w, note_h + 6, 2, fill=1, stroke=0)
        compliance_note.drawOn(c, MARGIN + 5, y - note_h - 3)
        y -= note_h + 11

        if options.get("report_notes") and idx == 1:
            c.setFillColor(rl_colors.HexColor("#F2F4F7"))
            c.roundRect(MARGIN, y - 13, usable_w, 13, 2, fill=1, stroke=0)
            c.setFillColor(rl_colors.HexColor("#30343B"))
            c.setFont(body_font, 6.8)
            note_text = str(options["report_notes"]).replace("\n", " ")[:220]
            c.drawString(MARGIN + 5, y - 9, f"Report note: {note_text}")
            y -= 17

        c.setFont(title_font, 12)
        c.drawCentredString(PAGE_W / 2, y - 2, "Velocity (mm/s)")
        y -= 10

        bottom_block_h = 76 * mm
        wave_bottom = body_bottom + bottom_block_h + 18
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
            time_ms = time_axis
            nv = len(active_vel)
            shared_velocity_limit = _nice_symmetric_limit([df[col].values for col, _, _ in active_vel])
            subplot_labels = [
                f"{label}  |  PPV {float(np.max(np.abs(df[col].values))):.2f} mm/s"
                for col, _, label in active_vel
            ]
            fig_wf = make_subplots(rows=nv, cols=1, shared_xaxes=True,
                                   subplot_titles=subplot_labels,
                                   vertical_spacing=0.075)
            for i2, (col, color, lbl) in enumerate(active_vel, start=1):
                sig = df[col].values
                fig_wf.add_trace(go.Scatter(x=time_ms, y=sig, mode="lines",
                                            line=dict(color=color, width=0.9), showlegend=False),
                                 row=i2, col=1)
            scale_caption = _style_signal_figure(
                fig_wf, nv, shared_velocity_limit, float(time_ms[-1]), "mm/s"
            )
            fig_wf.update_layout(height=max(240, int(180 * nv)))
            c.setFont(body_font, 6.5)
            c.setFillColor(rl_colors.HexColor("#4D535A"))
            c.drawRightString(PAGE_W - MARGIN, y + 1, scale_caption)
            img_wf_bytes = _to_image(fig_wf, format="png", width=1200, height=max(200, int(200 * nv)), scale=2)
            img_wf = RLImage(io.BytesIO(img_wf_bytes), width=usable_w, height=wave_h)
            img_wf.drawOn(c, MARGIN, wave_bottom)

        # Record values + selected compliance chart
        rec_vals = _record_values_from_df(df, time_axis, sps, meta)
        if rec_vals:
            panel_gap = 7
            left_w = right_w = (usable_w - panel_gap) / 2
            panel_title_y = body_bottom + bottom_block_h + 6
            panel_top = body_bottom + bottom_block_h - 8
            panel_bottom = body_bottom + 2
            panel_h = panel_top - panel_bottom
            velocity_rows = [r for r in rec_vals if r.get("unit") == "mm/s" and r.get("freq") is not None]
            for r in velocity_rows:
                result = evaluate_point(
                    {"channel": r["channel"], "ppv": r["max"], "freq": r["freq"]},
                    compliance_standard,
                    compliance_assessment,
                    compliance_category,
                )
                r["compliance_limit"] = result.limit
                r["compliance_status"] = result.status
                r["compliance_note"] = result.note
            c.setFillColor(rl_colors.black)
            c.setFont(bold_font, 12)
            c.drawCentredString(MARGIN + (left_w * 0.5), panel_title_y, "Record Values")
            rv_headers = ["Channel", "Peak / Time", "Freq.", "Limit", "Result"]
            rv_data = [[Paragraph(h, S["th_sm"]) for h in rv_headers]]
            for r in rec_vals:
                is_velocity = r.get("unit") == "mm/s" and r.get("freq") is not None
                rv_data.append([
                    Paragraph(str(r["channel"]), S["td_sm"]),
                    Paragraph(f"{r['max']:.2f} {r['unit']}<br/>{r['time_ms']:.1f} ms", S["td_c_sm"]),
                    Paragraph(f"{r['freq']} Hz" if r.get("freq") is not None else "-", S["td_c_sm"]),
                    Paragraph(
                        f"{format_limit(r.get('compliance_limit'))} mm/s"
                        if is_velocity and r.get("compliance_limit") is not None else "-",
                        S["td_c_sm"],
                    ),
                    Paragraph(
                        f"<b>{r.get('compliance_status', 'REVIEW')}</b>" if is_velocity else "-",
                        S["td_c_sm"],
                    ),
                ])

            vector_sum = meta.get("Vector sum", {}) or {}
            pvs_parts = []
            if (vector_sum.get("ch1_3") or 0) > 0:
                pvs_parts.append(f"Block 1: {float(vector_sum['ch1_3']):.2f} mm/s")
            if (vector_sum.get("ch4_6") or 0) > 0:
                pvs_parts.append(f"Block 2: {float(vector_sum['ch4_6']):.2f} mm/s")
            pvs_text = " &nbsp;&nbsp; | &nbsp;&nbsp; ".join(pvs_parts) if pvs_parts else "Not available"
            pvs_row_idx = len(rv_data)
            rv_data.append([
                Paragraph("<b>Peak Vector Sum (PVS)</b>", S["td_sm"]),
                Paragraph(pvs_text, S["td_sm"]), "", "", "",
            ])

            row_h = panel_h / len(rv_data)
            rv_tbl = Table(
                rv_data,
                colWidths=[left_w * f for f in (0.25, 0.27, 0.14, 0.17, 0.17)],
                rowHeights=[row_h] * len(rv_data),
            )
            rv_style = TableStyle(base_ts(rl_colors.HexColor("#DCE1E7")) + [
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#F7F8FA")]),
            ])
            for row_idx, row in enumerate(rec_vals, start=1):
                if row.get("compliance_status") == "PASS":
                    rv_style.add("TEXTCOLOR", (4, row_idx), (4, row_idx), rl_colors.HexColor("#176B3A"))
                elif row.get("compliance_status") == "FAIL":
                    rv_style.add("TEXTCOLOR", (4, row_idx), (4, row_idx), rl_colors.HexColor("#B42318"))
                elif row.get("compliance_status") == "REVIEW":
                    rv_style.add("TEXTCOLOR", (4, row_idx), (4, row_idx), rl_colors.HexColor("#9A6700"))
            rv_style.add("SPAN", (1, pvs_row_idx), (4, pvs_row_idx))
            rv_style.add("BACKGROUND", (0, pvs_row_idx), (-1, pvs_row_idx), rl_colors.HexColor("#EEF1F4"))
            rv_tbl.setStyle(rv_style)
            draw_table(c, rv_tbl, MARGIN, panel_top)

            ppv_points = _ppv_points_from_metadata(meta, df, sps)
            if ppv_points:
                panel_x = MARGIN + left_w + panel_gap
                c.setFillColor(rl_colors.black)
                c.setFont(bold_font, 12)
                c.drawCentredString(panel_x + (right_w * 0.5), panel_title_y, compliance_heading)
                c.setFont(body_font, 5.2)
                c.setFillColor(rl_colors.HexColor("#59616A"))
                c.drawCentredString(
                    panel_x + (right_w * 0.5), panel_title_y - 8,
                    measurement_basis(compliance_standard, compliance_assessment)[:86],
                )
                compliance_fig = build_compliance_chart(
                    ppv_points,
                    standard_id=compliance_standard,
                    assessment=compliance_assessment,
                    selected_category=compliance_category,
                    compact=True,
                )
                source_w = 480
                source_h = max(300, round(source_w * (panel_h / right_w)))
                compliance_fig.update_layout(
                    title=None,
                    height=source_h, width=source_w,
                    margin=dict(t=8, b=28, l=40, r=8),
                )
                compliance_img = _to_image(
                    compliance_fig, format="png", width=source_w, height=source_h, scale=2
                )
                compliance_img_rl = RLImage(
                    io.BytesIO(compliance_img), width=right_w, height=panel_h
                )
                compliance_img_rl.drawOn(c, panel_x, panel_bottom)

        c.showPage()
        page_num += 1

        if options.get("inc_ad"):
            draw_header_footer(c, meta, page_num, total_pages)
            draw_title(c, "Derived Signal Analysis", body_top)
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
            friendly_names = {
                "A_Vert": "Vertical acceleration", "A_Long": "Longitudinal acceleration",
                "A_Tran": "Transversal acceleration", "D_Vert": "Vertical displacement",
                "D_Long": "Longitudinal displacement", "D_Tran": "Transversal displacement",
            }
            half_h = (body_top - body_bottom - 42) / 2
            if acc_cols:
                c.setFont(title_font, 11)
                c.drawCentredString(PAGE_W / 2, body_top - 28, "Acceleration")
                acc_limit = _nice_symmetric_limit([df[col].values for col in acc_cols])
                fig_a = make_subplots(rows=len(acc_cols), cols=1, shared_xaxes=True,
                                      subplot_titles=[
                                          f"{friendly_names.get(col.split(' ')[0], col)}  |  Peak "
                                          f"{float(np.max(np.abs(df[col].values))):.1f} mm/s2"
                                          for col in acc_cols
                                      ], vertical_spacing=0.12)
                for i2, col in enumerate(acc_cols, start=1):
                    key = col.split(" ")[0]
                    fig_a.add_trace(go.Scatter(x=time_axis, y=df[col].values, mode="lines",
                                               line=dict(color=color_map.get(key, "#E53935"), width=0.9),
                                               showlegend=False),
                                    row=i2, col=1)
                fig_a_h = max(200, int(140 * len(acc_cols)))
                acc_scale = _style_signal_figure(
                    fig_a, len(acc_cols), acc_limit, float(time_axis[-1]), "mm/s2"
                )
                fig_a.update_layout(height=fig_a_h)
                img_a = _to_image(fig_a, format="png", width=1000, height=fig_a_h, scale=2)
                img_a_h = min(half_h, usable_w * (fig_a_h / 1000))
                acc_y = body_bottom + half_h + (half_h - img_a_h) / 2 + 5
                RLImage(io.BytesIO(img_a), width=usable_w, height=img_a_h).drawOn(
                    c, MARGIN, acc_y
                )
                c.setFont(body_font, 6.5)
                c.drawString(MARGIN + 2, acc_y - 7, acc_scale)
            if disp_cols:
                c.setFont(title_font, 11)
                c.drawCentredString(PAGE_W / 2, body_bottom + half_h - 12, "Displacement")
                disp_limit = _nice_symmetric_limit([df[col].values for col in disp_cols])
                fig_d = make_subplots(rows=len(disp_cols), cols=1, shared_xaxes=True,
                                      subplot_titles=[
                                          f"{friendly_names.get(col.split(' ')[0], col)}  |  Peak "
                                          f"{float(np.max(np.abs(df[col].values))):.4f} mm"
                                          for col in disp_cols
                                      ], vertical_spacing=0.12)
                for i2, col in enumerate(disp_cols, start=1):
                    key = col.split(" ")[0]
                    fig_d.add_trace(go.Scatter(x=time_axis, y=df[col].values, mode="lines",
                                               line=dict(color=color_map.get(key, "#1E88E5"), width=0.9),
                                               showlegend=False),
                                    row=i2, col=1)
                fig_d_h = max(200, int(140 * len(disp_cols)))
                disp_scale = _style_signal_figure(
                    fig_d, len(disp_cols), disp_limit, float(time_axis[-1]), "mm"
                )
                fig_d.update_layout(height=fig_d_h)
                img_d = _to_image(fig_d, format="png", width=1000, height=fig_d_h, scale=2)
                img_d_h = min(half_h, usable_w * (fig_d_h / 1000))
                disp_y = body_bottom + (half_h - img_d_h) / 2
                RLImage(io.BytesIO(img_d), width=usable_w, height=img_d_h).drawOn(
                    c, MARGIN, disp_y
                )
                c.setFont(body_font, 6.5)
                c.drawString(MARGIN + 2, disp_y - 7, disp_scale)
            c.showPage()
            page_num += 1

        if options.get("inc_fft"):
            draw_header_footer(c, meta, page_num, total_pages)
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
                fft_series = []
                for i2, col in enumerate(vel_cols, start=1):
                    sig = df[col].values
                    fft_mag = np.abs(np.fft.rfft(sig)) / n_samp
                    freqs = np.fft.rfftfreq(n_samp, d=1 / sps)
                    mask = freqs <= 200
                    fft_series.append(fft_mag[mask])
                    fig_fft.add_trace(go.Scatter(
                        x=freqs[mask], y=fft_mag[mask],
                        name=col.replace(" (mm/s)", ""),
                        mode="lines", line=dict(width=1.1, color=color_map.get(col, "#888888")),
                        showlegend=False,
                    ), row=i2, col=1)
                fig_fft_h = max(240, int(140 * len(vel_cols)))
                fft_limit = _nice_symmetric_limit(fft_series)
                for row in range(1, len(vel_cols) + 1):
                    fig_fft.update_yaxes(
                        range=[0, fft_limit], showgrid=True,
                        gridcolor="#B7BDC5", gridwidth=0.8,
                        linecolor="#59616A", tickfont=dict(size=8), row=row, col=1,
                    )
                    fig_fft.update_xaxes(
                        showgrid=True, gridcolor="#C4C9D0", gridwidth=0.7,
                        minor=dict(showgrid=True, gridcolor="#E2E5E9"),
                        linecolor="#59616A", tickfont=dict(size=8), row=row, col=1,
                    )
                fig_fft.update_layout(
                    xaxis_title=None, yaxis_title=None,
                    height=fig_fft_h, margin=dict(t=48, b=40, l=55, r=20),
                    font=dict(size=8), plot_bgcolor="white", paper_bgcolor="white",
                )
                for ann in fig_fft.layout.annotations:
                    ann.update(x=0.01, xanchor="left", yshift=14, font=dict(size=9))
                img_fft = _to_image(fig_fft, format="png", width=1000, height=fig_fft_h, scale=2)
                img_fft_h = min(body_top - body_bottom - 20, usable_w * (fig_fft_h / 1000))
                fft_y = body_top - img_fft_h - 4
                RLImage(io.BytesIO(img_fft), width=usable_w, height=img_fft_h).drawOn(
                    c, MARGIN, fft_y
                )
                c.setFont(title_font, 11)
                c.saveState()
                c.translate(MARGIN + 5, fft_y + (img_fft_h * 0.5))
                c.rotate(90)
                c.drawCentredString(0, 0, "Amplitude")
                c.restoreState()
                c.drawCentredString(PAGE_W / 2, fft_y - 12, "Frequency (Hz)")
            c.showPage()
            page_num += 1

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

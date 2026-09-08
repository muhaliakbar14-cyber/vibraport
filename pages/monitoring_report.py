"""Configurable PDF reports for long-term bargraph monitoring records."""

from __future__ import annotations

import io
import os
from xml.sax.saxutils import escape

import numpy as np
import streamlit as st

from core import detect_equipment_model
from core.compliance import (
    STANDARD_ORDER,
    STANDARDS,
    assessment_label,
    assessment_options,
    build_compliance_chart,
    category_options,
    chart_title,
    measurement_explanation,
)
from core.monitoring import (
    aggregate_monitoring_trends,
    detect_events_for_channels,
    evaluate_bargraph_ppv,
    get_bargraph_channels,
    infer_monitoring_interval,
    ppv_compliance_eligibility,
    summarize_channel,
)
from pages.monitoring_compliance import (
    _channel_summary_rows,
    _critical_chart_points,
    _overall_record_status,
)
from pages.monitoring_trends import (
    STATISTICS,
    _build_trend_figure,
    _shared_axis_compatible,
)
from pages.report import ImageExportTimeoutError, _to_image


SECTION_OVERVIEW = "Monitoring overview"
SECTION_TRENDS = "Aggregated trend"
SECTION_EVENTS = "Operational events"
SECTION_COMPLIANCE = "PPV compliance"
SECTION_OPTIONS = (
    SECTION_OVERVIEW,
    SECTION_TRENDS,
    SECTION_EVENTS,
    SECTION_COMPLIANCE,
)

TREND_WINDOWS = {
    "1 minute": 60.0,
    "5 minutes": 300.0,
    "15 minutes": 900.0,
    "1 hour": 3600.0,
}
MAX_EVENT_ROWS = 100


def render(df, time_axis, metadata, sampling_rate):
    """Render monitoring-specific report controls and PDF download."""

    st.title("Bargraph Monitoring PDF Report")
    st.caption(
        "Build a concise report from the active monitoring recording and choose "
        "which analysis sections to include."
    )
    st.divider()

    if metadata.get("is_waveform", True):
        st.info("This report is available for Bargraph recordings only.")
        return

    channels = get_bargraph_channels(df, metadata)
    if not channels:
        st.warning("No bargraph channels are available to report.")
        return

    times = np.asarray(time_axis, dtype=float)
    interval_seconds = metadata.get("Monitoring interval seconds")
    if not interval_seconds:
        interval_seconds = (
            infer_monitoring_interval(times, fallback=sampling_rate) or 1.0
        )
    duration_seconds = _recording_duration(times, interval_seconds)

    st.subheader("Report details")
    details_1, details_2 = st.columns(2)
    project_name = details_1.text_input("Project / Site Name", value="")
    client_name = details_1.text_input("Client / Company", value="")
    operator = details_2.text_input("Prepared by", value="")
    report_notes = details_2.text_area(
        "Additional Notes (optional)", value="", height=68
    )

    eligible_channels = [
        channel
        for channel in channels
        if ppv_compliance_eligibility(channel)[0]
    ]
    default_sections = [SECTION_OVERVIEW, SECTION_TRENDS]
    if eligible_channels:
        default_sections.append(SECTION_COMPLIANCE)

    st.subheader("Sections to include")
    selected_sections = st.multiselect(
        "Report content",
        options=list(SECTION_OPTIONS),
        default=default_sections,
        help="The cover and report details are always included.",
        key="monitoring_report_sections",
    )
    if not selected_sections:
        st.warning("Select at least one report section.")

    options = {
        "project_name": project_name,
        "client_name": client_name,
        "operator": operator,
        "report_notes": report_notes,
        "sections": selected_sections,
    }

    if SECTION_TRENDS in selected_sections:
        st.markdown("#### Trend options")
        trend_1, trend_2, trend_3 = st.columns(3)
        available_windows = {
            label: seconds
            for label, seconds in TREND_WINDOWS.items()
            if seconds >= interval_seconds and duration_seconds >= seconds
        }
        if not available_windows:
            available_windows = {
                f"Native interval ({interval_seconds:g} s)": interval_seconds
            }
        default_window = (
            "1 minute"
            if "1 minute" in available_windows
            else next(iter(available_windows))
        )
        trend_window_label = trend_1.selectbox(
            "Aggregation window",
            options=list(available_windows),
            index=list(available_windows).index(default_window),
            key="monitoring_report_trend_window",
        )
        trend_statistic_label = trend_2.selectbox(
            "Trend statistic",
            options=list(STATISTICS),
            key="monitoring_report_trend_statistic",
        )
        layout_options = ["Stacked panels (shared Y-axis)"]
        if _shared_axis_compatible(channels):
            layout_options.append("Combined overlay")
        trend_layout = trend_3.selectbox(
            "Trend chart layout",
            options=layout_options,
            key="monitoring_report_trend_layout",
        )
        options.update(
            trend_bucket_seconds=available_windows[trend_window_label],
            trend_window_label=trend_window_label,
            trend_statistic_label=trend_statistic_label,
            trend_statistic_key=STATISTICS[trend_statistic_label],
            trend_layout=trend_layout,
        )

    if SECTION_EVENTS in selected_sections:
        st.markdown("#### Operational event options")
        st.caption(
            "These are user-defined screening alarms, not regulatory limits."
        )
        thresholds = _render_event_thresholds(channels)
        grouping_1, grouping_2, grouping_3 = st.columns(3)
        minimum_duration = grouping_1.number_input(
            "Minimum event duration (s)",
            min_value=0.0,
            value=float(interval_seconds),
            step=float(interval_seconds),
            key="monitoring_report_event_minimum_duration",
        )
        gap_tolerance = grouping_2.number_input(
            "Quiet-gap tolerance (s)",
            min_value=0.0,
            value=0.0,
            step=float(interval_seconds),
            key="monitoring_report_event_gap",
        )
        hysteresis_percent = grouping_3.slider(
            "Release hysteresis (%)",
            min_value=0,
            max_value=50,
            value=10,
            step=1,
            key="monitoring_report_event_hysteresis",
        )
        options.update(
            event_thresholds=thresholds,
            event_minimum_duration=minimum_duration,
            event_gap_tolerance=gap_tolerance,
            event_hysteresis_percent=hysteresis_percent,
        )

    if SECTION_COMPLIANCE in selected_sections:
        st.markdown("#### PPV compliance options")
        if not eligible_channels:
            st.warning(
                "No Velocity · Interval peak · mm/s channels are eligible. "
                "The PDF will explain why compliance could not be evaluated."
            )
        compliance_1, compliance_2, compliance_3 = st.columns(3)
        standard_id = compliance_1.selectbox(
            "Standard",
            options=STANDARD_ORDER,
            format_func=lambda value: STANDARDS[value].title,
            key="monitoring_report_compliance_standard",
        )
        assessments = assessment_options(standard_id)
        assessment = compliance_2.selectbox(
            "Assessment",
            options=assessments,
            format_func=assessment_label,
            disabled=len(assessments) == 1,
            key=f"monitoring_report_assessment_{standard_id}",
        )
        categories = category_options(standard_id)
        default_category_index = (
            2 if standard_id == "sni_7571_2023" else min(1, len(categories) - 1)
        )
        category_id = compliance_3.selectbox(
            "Building category",
            options=[category.id for category in categories],
            index=default_category_index,
            format_func=lambda value: next(
                category.label for category in categories if category.id == value
            ),
            key=f"monitoring_report_category_{standard_id}",
        )
        st.caption(measurement_explanation(standard_id, assessment))
        options.update(
            compliance_standard=standard_id,
            compliance_assessment=assessment,
            compliance_category=category_id,
        )

    st.divider()
    signature = _options_signature(options)
    if st.button(
        "Generate Monitoring PDF",
        type="primary",
        disabled=not selected_sections,
    ):
        try:
            with st.spinner("Building monitoring report..."):
                pdf_bytes = _build_monitoring_pdf(
                    df,
                    times,
                    metadata,
                    sampling_rate,
                    options,
                )
        except ImageExportTimeoutError as exc:
            st.error(f"PDF chart rendering timed out: {exc}")
        except (ImportError, RuntimeError, ValueError) as exc:
            st.error(f"Monitoring report generation failed: {exc}")
        else:
            base_name = metadata.get("_filename", "bargraph").rsplit(".", 1)[0]
            st.session_state["monitoring_report_download"] = {
                "signature": signature,
                "bytes": pdf_bytes,
                "filename": f"vibraport-monitoring-{base_name}.pdf",
            }

    prepared = st.session_state.get("monitoring_report_download")
    if prepared and prepared.get("signature") == signature:
        st.success("Monitoring report ready.")
        st.download_button(
            "Download Monitoring PDF",
            data=prepared["bytes"],
            file_name=prepared["filename"],
            mime="application/pdf",
        )


def _render_event_thresholds(channels):
    quantities = {channel["quantity"] for channel in channels}
    thresholds = {}
    threshold_columns = st.columns(2)
    if "Velocity" in quantities:
        with threshold_columns[0]:
            st.markdown("**Velocity (mm/s)**")
            yellow_col, red_col = st.columns(2)
            yellow = yellow_col.number_input(
                "Yellow",
                min_value=0.1,
                value=1.0,
                step=0.1,
                key="monitoring_report_velocity_yellow",
            )
            red = red_col.number_input(
                "Red",
                min_value=0.1,
                value=5.0,
                step=0.1,
                key="monitoring_report_velocity_red",
            )
            thresholds["Velocity"] = (yellow, red)
    if "Pressure" in quantities:
        with threshold_columns[1]:
            st.markdown("**Pressure (Pa)**")
            yellow_col, red_col = st.columns(2)
            yellow = yellow_col.number_input(
                "Yellow",
                min_value=1.0,
                value=50.0,
                step=1.0,
                key="monitoring_report_pressure_yellow",
            )
            red = red_col.number_input(
                "Red",
                min_value=1.0,
                value=100.0,
                step=1.0,
                key="monitoring_report_pressure_red",
            )
            thresholds["Pressure"] = (yellow, red)
    for quantity, (yellow, red) in thresholds.items():
        if red <= yellow:
            st.warning(
                f"{quantity}: the red threshold should be greater than yellow. "
                "Values at or above yellow will still be reported as events."
            )
    return thresholds


def _build_monitoring_pdf(
    df,
    time_axis,
    metadata,
    sampling_rate,
    options,
    *,
    image_export=None,
):
    """Build a selectable-section bargraph PDF from full-resolution data."""

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import (
        Image,
        LongTable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    exporter = image_export or _to_image
    times = np.asarray(time_axis, dtype=float)
    channels = get_bargraph_channels(df, metadata)
    interval_seconds = metadata.get("Monitoring interval seconds")
    if not interval_seconds:
        interval_seconds = (
            infer_monitoring_interval(times, fallback=sampling_rate) or 1.0
        )
    duration_seconds = _recording_duration(times, interval_seconds)
    selected_sections = list(options.get("sections") or [])
    if not selected_sections:
        raise ValueError("At least one report section is required")

    body_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    try:
        font_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
        )
        pdfmetrics.registerFont(
            TTFont("Inter", os.path.join(font_dir, "Inter-Regular.ttf"))
        )
        pdfmetrics.registerFont(
            TTFont("Inter SemiBold", os.path.join(font_dir, "Inter-SemiBold.ttf"))
        )
        body_font = "Inter"
        bold_font = "Inter SemiBold"
    except Exception:
        pass

    navy = colors.HexColor("#1A237E")
    blue = colors.HexColor("#3949AB")
    light = colors.HexColor("#F3F5FA")
    green = colors.HexColor("#E8F5E9")
    red = colors.HexColor("#FFEBEE")
    amber = colors.HexColor("#FFF8E1")
    grey = colors.HexColor("#59616A")

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "monitoring_title",
            parent=base["Title"],
            fontName=bold_font,
            fontSize=20,
            leading=24,
            textColor=navy,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "section": ParagraphStyle(
            "monitoring_section",
            parent=base["Heading1"],
            fontName=bold_font,
            fontSize=14,
            leading=18,
            textColor=blue,
            spaceAfter=8,
        ),
        "subsection": ParagraphStyle(
            "monitoring_subsection",
            parent=base["Heading2"],
            fontName=bold_font,
            fontSize=10,
            textColor=navy,
            spaceBefore=5,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "monitoring_body",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=8.5,
            leading=12,
        ),
        "small": ParagraphStyle(
            "monitoring_small",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=7,
            leading=9,
            textColor=grey,
        ),
        "th": ParagraphStyle(
            "monitoring_th",
            parent=base["BodyText"],
            fontName=bold_font,
            fontSize=7,
            leading=8,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "td": ParagraphStyle(
            "monitoring_td",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=7,
            leading=9,
        ),
        "td_c": ParagraphStyle(
            "monitoring_td_c",
            parent=base["BodyText"],
            fontName=body_font,
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
        ),
    }

    def txt(value):
        if value is None:
            return "-"
        if isinstance(value, float) and not np.isfinite(value):
            return "-"
        return escape(str(value))

    def table_style(header=True):
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B9BEC7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            commands.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), navy),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]),
                ]
            )
        else:
            commands.append(
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, light])
            )
        return TableStyle(commands)

    def draw_page_frame(canvas, page_number, total_pages):
        page_width, page_height = A4
        margin = 15 * mm
        canvas.resetTransforms()
        canvas.saveState()
        canvas.setStrokeColor(navy)
        canvas.setLineWidth(0.8)
        canvas.line(margin, page_height - 16 * mm, page_width - margin, page_height - 16 * mm)
        canvas.setFillColor(navy)
        canvas.setFont(bold_font, 8)
        canvas.drawString(margin, page_height - 12 * mm, "VIBRAPORT")
        canvas.setFillColor(grey)
        canvas.setFont(body_font, 7)
        canvas.drawRightString(
            page_width - margin,
            page_height - 12 * mm,
            "Bargraph Monitoring Report",
        )
        canvas.line(margin, 14 * mm, page_width - margin, 14 * mm)
        canvas.drawString(margin, 10 * mm, "VIBRAPORT by ABDIYASA")
        canvas.drawRightString(
            page_width - margin,
            10 * mm,
            f"Page {page_number} of {total_pages}",
        )
        canvas.restoreState()

    class HeaderFooterCanvas(Canvas):
        """Replay completed pages so headers and footers stay above flowables."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total_pages = len(self._saved_page_states)
            for page_number, state in enumerate(self._saved_page_states, start=1):
                self.__dict__.update(state)
                draw_page_frame(self, page_number, total_pages)
                Canvas.showPage(self)
            Canvas.save(self)

    story = [Spacer(1, 8 * mm), Paragraph("Bargraph Monitoring Report", styles["title"])]
    cover_rows = [
        ("Project / Site", options.get("project_name") or "-", "Client", options.get("client_name") or "-"),
        ("Prepared by", options.get("operator") or "-", "File", metadata.get("_filename", "-")),
        ("Equipment", metadata.get("Equipment") or detect_equipment_model(metadata.get("Serial number", "")), "Serial number", metadata.get("Serial number", "-")),
        ("Date & time", f"{metadata.get('Date', '-')} {metadata.get('Time', '-')}", "Calibration", metadata.get("Calibration date", "-")),
        ("Duration", _format_duration(duration_seconds), "Monitoring interval", _format_interval(interval_seconds)),
    ]
    cover_data = [
        [
            Paragraph(f"<b>{txt(label_1)}</b>", styles["td"]),
            Paragraph(txt(value_1), styles["td"]),
            Paragraph(f"<b>{txt(label_2)}</b>", styles["td"]),
            Paragraph(txt(value_2), styles["td"]),
        ]
        for label_1, value_1, label_2, value_2 in cover_rows
    ]
    cover_table = Table(cover_data, colWidths=[32 * mm, 54 * mm, 32 * mm, 54 * mm])
    cover_table.setStyle(table_style(header=False))
    story.extend(
        [
            cover_table,
            Spacer(1, 7 * mm),
            Paragraph(
                "<b>Included sections:</b> "
                + ", ".join(txt(section) for section in selected_sections),
                styles["body"],
            ),
        ]
    )
    notes = options.get("report_notes")
    if notes:
        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph(f"<b>Report notes:</b> {txt(notes)}", styles["body"]),
            ]
        )
    story.extend(
        [
            Spacer(1, 8 * mm),
            Paragraph(
                "Bargraph values are interval summaries stored by the instrument. "
                "Unflagged channels are reported as interval peaks; Vibraport does "
                "not reconstruct waveform RMS or VDV from these values.",
                styles["small"],
            ),
            PageBreak(),
        ]
    )

    section_number = 0
    for section in selected_sections:
        section_number += 1
        if section == SECTION_OVERVIEW:
            _append_overview_section(
                story,
                df,
                channels,
                metadata,
                duration_seconds,
                interval_seconds,
                section_number,
                styles,
                table_style,
                txt,
                Table,
                Paragraph,
                Spacer,
                mm,
            )
        elif section == SECTION_TRENDS:
            _append_trend_section(
                story,
                df,
                times,
                channels,
                interval_seconds,
                options,
                section_number,
                styles,
                table_style,
                txt,
                exporter,
                Table,
                Paragraph,
                Spacer,
                Image,
                mm,
            )
        elif section == SECTION_EVENTS:
            _append_events_section(
                story,
                df,
                times,
                channels,
                interval_seconds,
                options,
                section_number,
                styles,
                table_style,
                txt,
                LongTable,
                Table,
                Paragraph,
                Spacer,
                mm,
                green,
                red,
                amber,
            )
        elif section == SECTION_COMPLIANCE:
            _append_compliance_section(
                story,
                df,
                times,
                channels,
                options,
                section_number,
                styles,
                table_style,
                txt,
                exporter,
                Table,
                Paragraph,
                Spacer,
                Image,
                mm,
                green,
                red,
                amber,
            )
        if section != selected_sections[-1]:
            story.append(PageBreak())

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=21 * mm,
        bottomMargin=18 * mm,
        title=f"Vibraport Bargraph Monitoring Report - {metadata.get('_filename', '')}",
        author=options.get("operator") or "Vibraport",
    )
    document.build(story, canvasmaker=HeaderFooterCanvas)
    return buffer.getvalue()


def _append_overview_section(
    story,
    df,
    channels,
    metadata,
    duration_seconds,
    interval_seconds,
    section_number,
    styles,
    table_style,
    txt,
    Table,
    Paragraph,
    Spacer,
    mm,
):
    story.append(Paragraph(f"{section_number}. Monitoring Overview", styles["section"]))
    story.append(
        Paragraph(
            f"The recording contains <b>{len(df):,}</b> intervals across "
            f"<b>{len(channels)}</b> channels over <b>{txt(_format_duration(duration_seconds))}</b>. "
            f"The nominal monitoring interval is <b>{txt(_format_interval(interval_seconds))}</b>.",
            styles["body"],
        )
    )
    story.extend([Spacer(1, 4 * mm), Paragraph("Channel summary", styles["subsection"])])
    headers = ["Channel", "Stored metric", "Valid", "Maximum", "Freq. at max", "Mean", "P95", "P99"]
    rows = [[Paragraph(header, styles["th"]) for header in headers]]
    invalid_total = 0
    over_range = []
    for channel in channels:
        frequency_column = channel.get("frequency_column")
        frequencies = (
            df[frequency_column].to_numpy(dtype=float)
            if frequency_column and frequency_column in df.columns
            else None
        )
        summary = summarize_channel(
            df[channel["amplitude_column"]].to_numpy(dtype=float), frequencies
        )
        invalid_total += summary["invalid_count"]
        if channel.get("over_range"):
            over_range.append(channel["label"])
        metric = f"{channel['quantity']} / {channel['statistic']} / {channel['unit'] or '-'}"
        values = [
            channel["label"],
            metric,
            f"{summary['valid_count']:,}",
            _number(summary["maximum"]),
            _number(summary["frequency_at_peak"], 3, suffix=" Hz"),
            _number(summary["mean"]),
            _number(summary["p95"]),
            _number(summary["p99"]),
        ]
        rows.append(
            [
                Paragraph(txt(value), styles["td"] if column < 2 else styles["td_c"])
                for column, value in enumerate(values)
            ]
        )
    table = Table(
        rows,
        repeatRows=1,
        colWidths=[24 * mm, 39 * mm, 16 * mm, 19 * mm, 24 * mm, 17 * mm, 17 * mm, 17 * mm],
    )
    table.setStyle(table_style())
    story.append(table)
    story.append(Spacer(1, 4 * mm))
    if over_range:
        quality = "Instrument over-range flag present: " + ", ".join(over_range) + "."
    elif invalid_total:
        quality = f"Data-quality warning: {invalid_total:,} non-finite channel values."
    else:
        quality = "Data-quality check: no over-range flags or non-finite amplitudes were found."
    story.append(Paragraph(txt(quality), styles["small"]))
    notes = [metadata.get(f"Note {index}") for index in range(1, 4)]
    notes = [note for note in notes if note]
    if notes:
        story.extend(
            [
                Spacer(1, 3 * mm),
                Paragraph("Source notes", styles["subsection"]),
                Paragraph("<br/>".join(txt(note) for note in notes), styles["body"]),
            ]
        )


def _append_trend_section(
    story,
    df,
    times,
    channels,
    interval_seconds,
    options,
    section_number,
    styles,
    table_style,
    txt,
    exporter,
    Table,
    Paragraph,
    Spacer,
    Image,
    mm,
):
    bucket_seconds = float(options.get("trend_bucket_seconds", 60.0))
    statistic_label = options.get("trend_statistic_label", "Maximum")
    statistic_key = options.get("trend_statistic_key", STATISTICS[statistic_label])
    layout_label = options.get("trend_layout", "Stacked panels (shared Y-axis)")
    combined = layout_label == "Combined overlay" and _shared_axis_compatible(channels)
    records = aggregate_monitoring_trends(
        df,
        times,
        channels,
        bucket_seconds,
        interval_seconds=interval_seconds,
    )
    _, figure = _build_trend_figure(
        records,
        channels,
        statistic_key,
        statistic_label,
        chart_layout="Combined overlay" if combined else "Stacked panels",
        synchronize_y_axis=not combined and _shared_axis_compatible(channels),
    )
    figure.update_layout(
        height=560 if not combined else 430,
        width=1000,
        margin=dict(t=65, b=55, l=60, r=25),
        font=dict(size=10),
    )
    image_bytes = exporter(
        figure,
        format="png",
        width=1000,
        height=560 if not combined else 430,
        scale=2,
    )

    story.append(Paragraph(f"{section_number}. Aggregated Trend", styles["section"]))
    story.append(
        Paragraph(
            f"<b>{txt(statistic_label)}</b> of the stored interval metric, aggregated in "
            f"<b>{txt(_format_interval(bucket_seconds))}</b> buckets. Calculations use all "
            "original intervals; chart reduction, if needed, is display-only.",
            styles["body"],
        )
    )
    story.extend([Spacer(1, 3 * mm), Image(io.BytesIO(image_bytes), width=180 * mm, height=(101 if not combined else 77) * mm)])
    story.append(
        Paragraph(
            "These bucket statistics are not reconstructed waveform RMS or VDV.",
            styles["small"],
        )
    )
    story.extend([Spacer(1, 3 * mm), Paragraph("Full-recording statistics", styles["subsection"])])
    headers = ["Channel", "Maximum", "Mean", "Median", "P95", "P99"]
    rows = [[Paragraph(header, styles["th"]) for header in headers]]
    for channel in channels:
        summary = summarize_channel(df[channel["amplitude_column"]].to_numpy(dtype=float))
        values = [
            channel["label"],
            _number(summary["maximum"]),
            _number(summary["mean"]),
            _number(summary["median"]),
            _number(summary["p95"]),
            _number(summary["p99"]),
        ]
        rows.append(
            [
                Paragraph(txt(value), styles["td"] if column == 0 else styles["td_c"])
                for column, value in enumerate(values)
            ]
        )
    table = Table(rows, colWidths=[45 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm, 27 * mm])
    table.setStyle(table_style())
    story.append(table)


def _append_events_section(
    story,
    df,
    times,
    channels,
    interval_seconds,
    options,
    section_number,
    styles,
    table_style,
    txt,
    LongTable,
    Table,
    Paragraph,
    Spacer,
    mm,
    green,
    red,
    amber,
):
    thresholds = options.get("event_thresholds") or {}
    events = detect_events_for_channels(
        df,
        times,
        channels,
        thresholds,
        interval_seconds=interval_seconds,
        gap_tolerance_seconds=float(options.get("event_gap_tolerance", 0.0)),
        hysteresis_percent=float(options.get("event_hysteresis_percent", 10.0)),
        minimum_duration_seconds=float(options.get("event_minimum_duration", interval_seconds)),
    )
    story.append(Paragraph(f"{section_number}. Operational Events", styles["section"]))
    threshold_text = ", ".join(
        f"{quantity}: yellow {yellow:g}, red {red_value:g}"
        for quantity, (yellow, red_value) in thresholds.items()
    ) or "No threshold-eligible quantity"
    story.append(
        Paragraph(
            f"<b>Screening thresholds:</b> {txt(threshold_text)}. "
            f"Minimum duration {float(options.get('event_minimum_duration', interval_seconds)):g} s; "
            f"quiet-gap tolerance {float(options.get('event_gap_tolerance', 0.0)):g} s; "
            f"release hysteresis {float(options.get('event_hysteresis_percent', 10.0)):g}%.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    red_count = sum(event["severity"] == "Red" for event in events)
    summary_rows = [
        [Paragraph("Total events", styles["th"]), Paragraph("Red events", styles["th"]), Paragraph("Longest", styles["th"]), Paragraph("Highest peak", styles["th"])],
        [
            Paragraph(f"{len(events):,}", styles["td_c"]),
            Paragraph(f"{red_count:,}", styles["td_c"]),
            Paragraph(_format_duration(max((event["duration_seconds"] for event in events), default=0.0)), styles["td_c"]),
            Paragraph(
                (
                    f"{max(events, key=lambda event: event['peak'])['peak']:.4f} "
                    f"{max(events, key=lambda event: event['peak'])['unit']}"
                    if events
                    else "-"
                ),
                styles["td_c"],
            ),
        ],
    ]
    summary = Table(summary_rows, colWidths=[45 * mm] * 4)
    summary_style = table_style()
    if events:
        summary_style.add("BACKGROUND", (0, 1), (-1, 1), red if red_count else green)
    summary.setStyle(summary_style)
    story.append(summary)
    story.extend([Spacer(1, 5 * mm), Paragraph("Event register", styles["subsection"])])
    if not events:
        story.append(Paragraph("No events match the selected settings.", styles["body"]))
        return

    headers = ["Event", "Severity", "Channel", "Start", "Duration", "Peak", "Freq. at peak"]
    rows = [[Paragraph(header, styles["th"]) for header in headers]]
    for index, event in enumerate(events[:MAX_EVENT_ROWS], start=1):
        values = [
            f"E{index:04d}",
            event["severity"],
            event["channel"],
            f"{event['start_seconds'] / 60:.3f} min",
            _format_duration(event["duration_seconds"]),
            f"{event['peak']:.4f} {event['unit']}",
            _number(event["frequency_at_peak"], 3, suffix=" Hz"),
        ]
        rows.append(
            [
                Paragraph(txt(value), styles["td"] if column == 2 else styles["td_c"])
                for column, value in enumerate(values)
            ]
        )
    table = LongTable(
        rows,
        repeatRows=1,
        colWidths=[16 * mm, 19 * mm, 35 * mm, 23 * mm, 23 * mm, 33 * mm, 31 * mm],
    )
    event_style = table_style()
    for row_index, event in enumerate(events[:MAX_EVENT_ROWS], start=1):
        event_style.add(
            "BACKGROUND",
            (0, row_index),
            (-1, row_index),
            red if event["severity"] == "Red" else amber,
        )
    table.setStyle(event_style)
    story.append(table)
    if len(events) > MAX_EVENT_ROWS:
        story.append(
            Paragraph(
                f"Showing the first {MAX_EVENT_ROWS:,} of {len(events):,} chronological events. "
                "Use the Events & Thresholds CSV export for the complete register.",
                styles["small"],
            )
        )
    story.append(
        Paragraph(
            "Operational events are user-defined screening results and are not regulatory compliance conclusions.",
            styles["small"],
        )
    )


def _append_compliance_section(
    story,
    df,
    times,
    channels,
    options,
    section_number,
    styles,
    table_style,
    txt,
    exporter,
    Table,
    Paragraph,
    Spacer,
    Image,
    mm,
    green,
    red,
    amber,
):
    standard_id = options.get("compliance_standard", "sni_7571_2023")
    assessment = options.get("compliance_assessment", "short_term")
    category_id = int(options.get("compliance_category", 3))
    categories = category_options(standard_id)
    category = next(category for category in categories if category.id == category_id)
    eligible = [channel for channel in channels if ppv_compliance_eligibility(channel)[0]]
    records = evaluate_bargraph_ppv(
        df,
        times,
        eligible,
        standard_id,
        assessment,
        category_id,
    )

    story.append(Paragraph(f"{section_number}. PPV Compliance", styles["section"]))
    story.append(
        Paragraph(
            f"<b>{txt(chart_title(standard_id, assessment))}</b> - {txt(category.label)}<br/>"
            + txt(measurement_explanation(standard_id, assessment)),
            styles["body"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    if not records:
        story.append(
            Paragraph(
                "No Velocity / Interval peak / mm/s channels are eligible for PPV assessment. "
                "RMS and other stored metrics were not relabelled or converted.",
                styles["body"],
            )
        )
        return

    overall = _overall_record_status(records)
    pass_count = sum(record["status"] == "PASS" for record in records)
    fail_count = sum(record["status"] == "FAIL" for record in records)
    review_count = sum(record["status"] == "REVIEW" for record in records)
    utilizations = [
        record["utilization_percent"]
        for record in records
        if record["utilization_percent"] is not None
    ]
    worst = max(utilizations) if utilizations else None
    summary_rows = [
        [Paragraph("Overall", styles["th"]), Paragraph("Evaluated", styles["th"]), Paragraph("Pass / Fail / Review", styles["th"]), Paragraph("Worst utilization", styles["th"])],
        [
            Paragraph(f"<b>{overall}</b>", styles["td_c"]),
            Paragraph(f"{len(records):,}", styles["td_c"]),
            Paragraph(f"{pass_count:,} / {fail_count:,} / {review_count:,}", styles["td_c"]),
            Paragraph(f"{worst:.1f}%" if worst is not None else "-", styles["td_c"]),
        ],
    ]
    summary = Table(summary_rows, colWidths=[38 * mm, 38 * mm, 57 * mm, 47 * mm])
    summary_style = table_style()
    summary_style.add(
        "BACKGROUND",
        (0, 1),
        (-1, 1),
        red if overall == "FAIL" else amber if overall == "REVIEW" else green,
    )
    summary.setStyle(summary_style)
    story.append(summary)
    story.extend([Spacer(1, 4 * mm), Paragraph("Channel assessment", styles["subsection"])])
    headers = ["Channel", "Result", "Intervals", "Pass", "Fail", "Review", "Worst util.", "Critical PPV / Hz"]
    rows = [[Paragraph(header, styles["th"]) for header in headers]]
    for row in _channel_summary_rows(records):
        values = [
            row["Channel"],
            row["Result"],
            f"{row['Intervals']:,}",
            f"{row['Pass']:,}",
            f"{row['Fail']:,}",
            f"{row['Review']:,}",
            _number(row["Worst utilization (%)"], 2, suffix="%"),
            f"{_number(row['Critical PPV (mm/s)'])} / {_number(row['Critical frequency (Hz)'], 3)}",
        ]
        rows.append(
            [
                Paragraph(txt(value), styles["td"] if column == 0 else styles["td_c"])
                for column, value in enumerate(values)
            ]
        )
    channel_table = Table(
        rows,
        colWidths=[31 * mm, 20 * mm, 21 * mm, 18 * mm, 18 * mm, 20 * mm, 24 * mm, 28 * mm],
    )
    channel_table.setStyle(table_style())
    story.append(channel_table)

    chart_points = _critical_chart_points(records)
    if chart_points:
        figure = build_compliance_chart(
            chart_points,
            standard_id=standard_id,
            assessment=assessment,
            selected_category=category_id,
            compact=True,
        )
        figure.update_layout(
            title=None,
            width=900,
            height=430,
            margin=dict(t=15, b=55, l=60, r=20),
        )
        image_bytes = exporter(
            figure,
            format="png",
            width=900,
            height=430,
            scale=2,
        )
        story.extend(
            [
                Spacer(1, 4 * mm),
                Paragraph("Most critical interval per channel", styles["subsection"]),
                Image(io.BytesIO(image_bytes), width=174 * mm, height=83 * mm),
            ]
        )
    else:
        story.append(
            Paragraph(
                "No compliance chart is available because all eligible intervals have missing or zero dominant frequency; those intervals remain REVIEW.",
                styles["small"],
            )
        )
    story.append(
        Paragraph(
            "This is an engineering screening aid, not a certification. Confirm the selected standard, category, sensor location, and measurement basis before formal use.",
            styles["small"],
        )
    )


def _recording_duration(times, interval_seconds):
    finite = np.asarray(times, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not finite.size:
        return float(interval_seconds)
    return float(finite[-1] - finite[0] + interval_seconds)


def _format_duration(seconds):
    hours, remainder = divmod(float(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{int(hours)}h")
    if minutes:
        parts.append(f"{int(minutes)}m")
    if seconds or not parts:
        parts.append(f"{seconds:.0f}s")
    return " ".join(parts)


def _format_interval(seconds):
    seconds = float(seconds)
    if seconds >= 3600 and seconds % 3600 == 0:
        return f"{seconds / 3600:g} h"
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds / 60:g} min"
    return f"{seconds:g} s"


def _number(value, digits=4, suffix=""):
    if value is None or not np.isfinite(value):
        return "-"
    return f"{float(value):.{digits}f}{suffix}"


def _options_signature(options):
    return repr(_freeze(options))


def _freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value

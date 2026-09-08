"""Frequency-aware structural PPV assessment for bargraph recordings."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core.compliance import (
    STANDARD_ORDER,
    STANDARDS,
    assessment_label,
    assessment_options,
    build_compliance_chart,
    category_options,
    measurement_explanation,
)
from core.monitoring import (
    evaluate_bargraph_ppv,
    get_bargraph_channels,
    ppv_compliance_eligibility,
)


MAX_TABLE_ROWS = 2_000


def render(df, time_axis, metadata, sampling_rate):
    del sampling_rate
    st.title("📐 PPV Compliance")
    st.caption(
        "Assess every eligible interval-peak velocity bar using its stored "
        "dominant frequency"
    )
    st.divider()

    if metadata.get("is_waveform", True):
        st.info(
            "This page is for **Bargraph** recordings only. "
            "The current file is a Waveform recording."
        )
        return

    channels = get_bargraph_channels(df, metadata)
    if not channels:
        st.warning("No bargraph amplitude data found in file.")
        return

    eligible_channels = []
    capability_rows = []
    for channel in channels:
        eligible, reason = ppv_compliance_eligibility(channel)
        if eligible:
            eligible_channels.append(channel)
        capability_rows.append(
            {
                "Channel": channel["label"],
                "Stored metric": (
                    f"{channel['quantity']} · {channel['statistic']} · "
                    f"{channel['unit'] or 'unit unavailable'}"
                ),
                "Dominant frequency": (
                    "Available" if channel.get("frequency_available") else "Missing / zero"
                ),
                "PPV assessment": "Eligible" if eligible else "Not eligible",
                "Reason": reason,
            }
        )

    with st.expander("Channel eligibility", expanded=not eligible_channels):
        st.dataframe(
            pd.DataFrame(capability_rows),
            width="stretch",
            hide_index=True,
        )

    if not eligible_channels:
        st.warning(
            "This recording has no interval-peak velocity channels in mm/s. "
            "RMS, acceleration, pressure, and other stored metrics are not "
            "relabelled as PPV."
        )
        return

    selector_1, selector_2, selector_3 = st.columns(3)
    standard_id = selector_1.selectbox(
        "Standard",
        options=STANDARD_ORDER,
        format_func=lambda value: STANDARDS[value].title,
        key="monitoring_compliance_standard",
    )
    duration_options = assessment_options(standard_id)
    assessment = selector_2.selectbox(
        "Assessment",
        options=duration_options,
        format_func=assessment_label,
        disabled=len(duration_options) == 1,
        key=f"monitoring_compliance_assessment_{standard_id}",
    )
    categories = category_options(standard_id)
    default_category_index = (
        2 if standard_id == "sni_7571_2023" else min(1, len(categories) - 1)
    )
    selected_category = selector_3.selectbox(
        "Building category",
        options=[category.id for category in categories],
        index=default_category_index,
        format_func=lambda value: next(
            category.label for category in categories if category.id == value
        ),
        key=f"monitoring_compliance_category_{standard_id}",
    )

    st.info(measurement_explanation(standard_id, assessment))
    st.caption(
        "Each finite bar is evaluated at full resolution. The bar's stored "
        "dominant frequency is used directly; missing or zero frequency is "
        "reported as REVIEW and is never estimated."
    )

    records = evaluate_bargraph_ppv(
        df,
        np.asarray(time_axis, dtype=float),
        eligible_channels,
        standard_id,
        assessment,
        selected_category,
    )
    if not records:
        st.warning("No finite interval-peak velocity values are available to assess.")
        return

    status = _overall_record_status(records)
    category_label = next(
        category.label for category in categories if category.id == selected_category
    )
    failed_count = sum(record["status"] == "FAIL" for record in records)
    review_count = sum(record["status"] == "REVIEW" for record in records)
    passed_count = sum(record["status"] == "PASS" for record in records)
    utilizations = [
        record["utilization_percent"]
        for record in records
        if record["utilization_percent"] is not None
    ]
    worst_utilization = max(utilizations) if utilizations else None

    if status == "PASS":
        st.success(f"✅ All evaluated intervals pass: **{category_label}**")
    elif status == "FAIL":
        st.error(
            f"⚠️ {failed_count:,} interval(s) exceed the selected limit — "
            f"**{category_label}**"
        )
    else:
        st.warning(
            f"Review required for {review_count:,} interval(s) — "
            f"**{category_label}**"
        )

    metric_1, metric_2, metric_3, metric_4 = st.columns(4)
    metric_1.metric("Evaluated intervals", f"{len(records):,}")
    metric_2.metric("Pass", f"{passed_count:,}")
    metric_3.metric("Fail / Review", f"{failed_count:,} / {review_count:,}")
    metric_4.metric(
        "Worst utilization",
        f"{worst_utilization:.1f}%" if worst_utilization is not None else "—",
    )

    st.markdown("## Channel Summary")
    st.dataframe(
        pd.DataFrame(_channel_summary_rows(records)),
        width="stretch",
        hide_index=True,
    )

    chart_points = _critical_chart_points(records)
    if chart_points:
        st.markdown("## Most Critical Interval per Channel")
        st.caption(
            "The chart shows the highest limit-utilization interval for each "
            "channel. Counts and tables above and below use every stored interval."
        )
        figure = build_compliance_chart(
            chart_points,
            standard_id=standard_id,
            assessment=assessment,
            selected_category=selected_category,
        )
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False},
        )
    else:
        st.warning(
            "A compliance chart cannot be plotted because every eligible interval "
            "has missing or zero dominant frequency. All such intervals remain REVIEW."
        )

    st.markdown("## Interval Results")
    result_view = st.radio(
        "Rows to show",
        ["Exceptions only", "Highest utilization", "All intervals"],
        horizontal=True,
        key="monitoring_compliance_result_view",
    )
    result_table = _result_dataframe(records)
    if result_view == "Exceptions only":
        display_table = result_table[result_table["Result"] != "PASS"]
    elif result_view == "Highest utilization":
        display_table = result_table.sort_values(
            ["Utilization (%)", "PPV (mm/s)"],
            ascending=False,
            na_position="last",
        )
    else:
        display_table = result_table

    if display_table.empty:
        st.success("No FAIL or REVIEW intervals for the selected assessment.")
    else:
        hidden_count = max(0, len(display_table) - MAX_TABLE_ROWS)
        st.dataframe(
            display_table.head(MAX_TABLE_ROWS),
            width="stretch",
            hide_index=True,
        )
        if hidden_count:
            st.caption(
                f"Showing {MAX_TABLE_ROWS:,} of {len(display_table):,} matching "
                "rows. The CSV export contains every evaluated interval."
            )

    filename = metadata.get("_filename", "bargraph").rsplit(".", 1)[0]
    st.download_button(
        "⬇️ Export full compliance results as CSV",
        data=result_table.to_csv(index=False).encode("utf-8"),
        file_name=f"{filename}-ppv-compliance.csv",
        mime="text/csv",
    )
    st.caption(
        "This is an engineering screening aid, not a certification. Confirm the "
        "selected standard, building category, sensor location, and measurement "
        "basis before using the result in a formal assessment."
    )


def _overall_record_status(records):
    statuses = {record["status"] for record in records}
    if "FAIL" in statuses:
        return "FAIL"
    if "REVIEW" in statuses:
        return "REVIEW"
    return "PASS"


def _channel_summary_rows(records):
    rows = []
    channel_order = list(dict.fromkeys(record["channel"] for record in records))
    for channel in channel_order:
        channel_records = [record for record in records if record["channel"] == channel]
        channel_status = _overall_record_status(channel_records)
        valid_limits = [
            record for record in channel_records if record["utilization_percent"] is not None
        ]
        worst = (
            max(valid_limits, key=lambda record: record["utilization_percent"])
            if valid_limits
            else None
        )
        rows.append(
            {
                "Channel": channel,
                "Result": channel_status,
                "Intervals": len(channel_records),
                "Pass": sum(record["status"] == "PASS" for record in channel_records),
                "Fail": sum(record["status"] == "FAIL" for record in channel_records),
                "Review": sum(record["status"] == "REVIEW" for record in channel_records),
                "Worst utilization (%)": (
                    round(worst["utilization_percent"], 2) if worst else None
                ),
                "Critical PPV (mm/s)": round(worst["ppv"], 4) if worst else None,
                "Critical frequency (Hz)": (
                    round(worst["frequency_hz"], 3) if worst else None
                ),
            }
        )
    return rows


def _critical_chart_points(records):
    points = []
    channel_order = list(dict.fromkeys(record["channel"] for record in records))
    for channel in channel_order:
        valid = [
            record
            for record in records
            if record["channel"] == channel
            and record["utilization_percent"] is not None
            and record["frequency_hz"] > 0
        ]
        if not valid:
            continue
        worst = max(valid, key=lambda record: record["utilization_percent"])
        points.append(
            {
                "channel": worst["channel"],
                "ppv": worst["ppv"],
                "freq": worst["frequency_hz"],
            }
        )
    return points


def _result_dataframe(records):
    return pd.DataFrame(
        [
            {
                "Channel": record["channel"],
                "Interval": record["interval_index"] + 1,
                "Time (min)": round(record["time_seconds"] / 60, 4),
                "PPV (mm/s)": round(record["ppv"], 4),
                "Dominant frequency (Hz)": (
                    round(record["frequency_hz"], 3)
                    if record["frequency_hz"] > 0
                    else None
                ),
                "Applied limit (mm/s)": (
                    record["limit"]
                    if record["limit"] is not None
                    else None
                ),
                "Utilization (%)": (
                    round(record["utilization_percent"], 2)
                    if record["utilization_percent"] is not None
                    else None
                ),
                "Result": record["status"],
                "Note": record["note"],
            }
            for record in records
        ]
    )

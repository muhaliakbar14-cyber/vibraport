"""Tests for selectable-section bargraph monitoring PDFs."""

import io

import numpy as np
import pandas as pd
import pytest
from PIL import Image
from pypdf import PdfReader

from pages.monitoring_report import (
    SECTION_COMPLIANCE,
    SECTION_EVENTS,
    SECTION_OVERVIEW,
    SECTION_TRENDS,
    _build_monitoring_pdf,
)


def test_overview_only_pdf_excludes_unselected_sections():
    df, times, metadata = _monitoring_fixture()
    pdf_bytes = _build_monitoring_pdf(
        df,
        times,
        metadata,
        1.0,
        {
            "sections": [SECTION_OVERVIEW],
            "project_name": "North Pit",
            "client_name": "Example Client",
            "operator": "Test Engineer",
        },
        image_export=_fake_image_export,
    )

    text = _pdf_text(pdf_bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert "Bargraph Monitoring Report" in text
    assert "North Pit" in text
    assert "Monitoring Overview" in text
    assert "Aggregated Trend" not in text
    assert "Operational Events" not in text
    assert "PPV Compliance" not in text


def test_full_monitoring_pdf_contains_every_selected_section():
    df, times, metadata = _monitoring_fixture()
    pdf_bytes = _build_monitoring_pdf(
        df,
        times,
        metadata,
        1.0,
        {
            "sections": [
                SECTION_OVERVIEW,
                SECTION_TRENDS,
                SECTION_EVENTS,
                SECTION_COMPLIANCE,
            ],
            "trend_bucket_seconds": 60.0,
            "trend_statistic_label": "Maximum",
            "trend_statistic_key": "maximum",
            "trend_layout": "Stacked panels (shared Y-axis)",
            "event_thresholds": {"Velocity": (1.0, 2.0)},
            "event_minimum_duration": 1.0,
            "event_gap_tolerance": 0.0,
            "event_hysteresis_percent": 10.0,
            "compliance_standard": "sni_7571_2023",
            "compliance_assessment": "short_term",
            "compliance_category": 3,
        },
        image_export=_fake_image_export,
    )

    text = _pdf_text(pdf_bytes)
    assert "Monitoring Overview" in text
    assert "Aggregated Trend" in text
    assert "Operational Events" in text
    assert "Event register" in text
    assert "PPV Compliance" in text
    assert "Worst utilization" in text
    assert text.count("Page ") >= 5


def test_monitoring_pdf_requires_at_least_one_section():
    df, times, metadata = _monitoring_fixture()

    with pytest.raises(ValueError, match="At least one"):
        _build_monitoring_pdf(
            df,
            times,
            metadata,
            1.0,
            {"sections": []},
            image_export=_fake_image_export,
        )


def _monitoring_fixture():
    times = np.arange(120, dtype=float)
    vertical = np.full(120, 0.4)
    longitudinal = np.full(120, 0.7)
    transversal = np.full(120, 0.2)
    vertical[10:13] = [1.1, 2.4, 1.2]
    longitudinal[70:73] = [1.2, 1.4, 0.8]
    transversal[95] = 1.1
    frequencies = np.full(120, 12.0)

    channel_specs = [
        (1, "Vertical", "vertical_amplitude", "vertical_frequency"),
        (2, "Longitudinal", "longitudinal_amplitude", "longitudinal_frequency"),
        (3, "Transversal", "transversal_amplitude", "transversal_frequency"),
    ]
    metadata_channels = []
    for index, axis, amplitude_column, frequency_column in channel_specs:
        metadata_channels.append(
            {
                "index": index,
                "axis": axis,
                "label": f"{axis} (Ch{index})",
                "magnitude": "Velocity",
                "quantity": "Velocity",
                "statistic": "Interval peak",
                "unit": "mm/s",
                "amplitude_column": amplitude_column,
                "frequency_column": frequency_column,
                "frequency_available": True,
                "transducer_type": "Geophone 8.0 Hz fn",
                "sample_count": 120,
                "over_range": False,
                "is_virtual": False,
            }
        )

    df = pd.DataFrame(
        {
            "vertical_amplitude": vertical,
            "vertical_frequency": frequencies,
            "longitudinal_amplitude": longitudinal,
            "longitudinal_frequency": frequencies,
            "transversal_amplitude": transversal,
            "transversal_frequency": frequencies,
        }
    )
    metadata = {
        "_filename": "syntheticM.sis",
        "is_waveform": False,
        "Equipment": "Vibracord Tellus",
        "Serial number": "TE123",
        "Date": "2026-09-08",
        "Time": "09:00:00",
        "Calibration date": "2026-01-01",
        "Monitoring interval seconds": 1.0,
        "Bargraph channels": metadata_channels,
        "Note 1": "Synthetic monitoring fixture",
    }
    return df, times, metadata


def _fake_image_export(*_args, **_kwargs):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 24), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _pdf_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)

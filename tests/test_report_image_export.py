"""Regression tests for bounded, recoverable Plotly image export."""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
from PIL import Image
from pypdf import PdfReader

from pages import report


def test_report_export_wrapper_uses_isolated_renderer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        report,
        "render_figure",
        lambda figure, **kwargs: calls.append((figure, kwargs)) or b"image",
    )

    figure = object()
    assert report._to_image(figure, format="png", width=100) == b"image"
    assert calls == [(figure, {"format": "png", "width": 100})]


def test_synthetic_multi_file_report_with_every_optional_section(monkeypatch):
    files = [
        _waveform_report_file("synthetic-1.sis", amplitude=1.0),
        _waveform_report_file("synthetic-2.sis", amplitude=1.4),
    ]

    def fake_image_export(*_args, **_kwargs):
        buffer = io.BytesIO()
        Image.new("RGB", (80, 48), "white").save(buffer, format="PNG")
        return buffer.getvalue()

    monkeypatch.setattr(report, "_to_image", fake_image_export)
    pdf_bytes = report._build_metis_pdf(
        files,
        {
            "project_name": "Export recovery regression",
            "operator": "METIS Analytics test",
            "client_name": "Test client",
            "report_notes": "All optional waveform sections enabled.",
            "inc_records": True,
            "inc_ad": True,
            "inc_fft": True,
            "compliance_standard": "sni_7571_2023",
            "compliance_assessment": "short_term",
            "compliance_category": 3,
        },
    )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(reader.pages) == 7
    assert "Records summary" in text
    assert text.count("Derived Signal Analysis") == 2
    assert text.count("FFT Analysis") == 2


def _waveform_report_file(name: str, amplitude: float) -> dict:
    sampling_rate = 1024
    sample_count = 256
    time_seconds = np.arange(sample_count, dtype=float) / sampling_rate
    time_ms = time_seconds * 1000.0
    vertical = amplitude * np.sin(2 * np.pi * 12 * time_seconds)
    longitudinal = 0.8 * amplitude * np.sin(2 * np.pi * 16 * time_seconds)
    transversal = 0.6 * amplitude * np.sin(2 * np.pi * 20 * time_seconds)

    df = pd.DataFrame(
        {
            "Vertical (mm/s)": vertical,
            "Longitudinal (mm/s)": longitudinal,
            "Transversal (mm/s)": transversal,
            "A_Vert (mm/s²)": np.gradient(vertical, 1 / sampling_rate),
            "A_Long (mm/s²)": np.gradient(longitudinal, 1 / sampling_rate),
            "A_Tran (mm/s²)": np.gradient(transversal, 1 / sampling_rate),
            "D_Vert (mm)": np.cumsum(vertical) / sampling_rate,
            "D_Long (mm)": np.cumsum(longitudinal) / sampling_rate,
            "D_Tran (mm)": np.cumsum(transversal) / sampling_rate,
        }
    )
    channel_info = []
    for axis, frequency in (("Vertical", 12), ("Longitudinal", 16), ("Transversal", 20)):
        channel_info.append(
            {
                "axis": axis,
                "magnitude": "Velocity",
                "belongs_to_block": 1,
                "is_virtual": False,
                "freq_zero_crossing": frequency,
                "freq_fft_peak": frequency,
                "freq_energy_25": frequency,
                "freq_energy_50": frequency,
                "freq_energy_75": frequency,
            }
        )

    metadata = {
        "_filename": name,
        "Equipment": "Synthetic test recorder",
        "Serial number": "TEST-001",
        "Date": "2026-09-23",
        "Time": "12:00:00",
        "Calibration date": "2026-01-01",
        "Sampling rate": f"{sampling_rate} sps",
        "Record length": f"{sample_count / sampling_rate:.3f} s",
        "Pretrigger": "0 ms",
        "Clock source": "Synthetic",
        "Channel info": channel_info,
        "Vector sum": {"ch1_3": float(amplitude)},
    }
    return {
        "name": name,
        "df": df,
        "time_axis": time_ms,
        "metadata": metadata,
        "sampling_rate": sampling_rate,
    }

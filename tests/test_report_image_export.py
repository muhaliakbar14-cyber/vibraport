"""Regression tests for bounded, recoverable Plotly image export."""

from __future__ import annotations

import io
import threading

import numpy as np
import pandas as pd
import pytest
from PIL import Image
from pypdf import PdfReader

from pages import report


class _BlockingFigure:
    def __init__(self, block_calls: int):
        self.calls = 0
        self.block_calls = block_calls
        self.release_events: list[threading.Event] = []

    def to_image(self, **_kwargs):
        self.calls += 1
        if self.calls > self.block_calls:
            return b"recovered-image"
        release = threading.Event()
        self.release_events.append(release)
        release.wait(timeout=1.0)
        return b"recovered-image"


class _FastFigure:
    def to_image(self, **_kwargs):
        return b"fast-image"


def test_timeout_restarts_kaleido_and_retries_successfully(monkeypatch):
    figure = _BlockingFigure(block_calls=1)

    monkeypatch.setattr(report, "_IMG_EXPORT_TIMEOUT_S", 0.01)

    def recover(future):
        figure.release_events[-1].set()
        future.result(timeout=1.0)
        return True

    monkeypatch.setattr(report, "_recover_timed_out_export", recover)

    assert report._to_image(figure, format="png") == b"recovered-image"
    assert figure.calls == 2


def test_repeated_timeout_does_not_poison_later_exports(monkeypatch):
    figure = _BlockingFigure(block_calls=2)

    monkeypatch.setattr(report, "_IMG_EXPORT_TIMEOUT_S", 0.01)

    def recover(future):
        figure.release_events[-1].set()
        future.result(timeout=1.0)
        return True

    monkeypatch.setattr(report, "_recover_timed_out_export", recover)

    with pytest.raises(report.ImageExportTimeoutError, match="made 2 attempts"):
        report._to_image(figure, format="png")

    assert figure.calls == 2
    assert report._to_image(_FastFigure(), format="png") == b"fast-image"


def test_process_termination_falls_back_to_direct_kill(monkeypatch):
    class FakeProcess:
        pid = 123

        def __init__(self):
            self.running = True
            self.killed = False

        def poll(self):
            return None if self.running else 1

        def kill(self):
            self.running = False
            self.killed = True

    process = FakeProcess()
    monkeypatch.setattr(report.os, "name", "posix")

    report._terminate_process_tree(process)

    assert process.killed is True


def test_windows_process_termination_kills_the_renderer_tree(monkeypatch):
    class FakeProcess:
        pid = 456

        def __init__(self):
            self.running = True
            self.killed = False

        def poll(self):
            return None if self.running else 1

        def kill(self):
            self.killed = True

    process = FakeProcess()
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        process.running = False

    monkeypatch.setattr(report.os, "name", "nt")
    monkeypatch.setattr(report.subprocess, "run", fake_run)

    report._terminate_process_tree(process)

    assert commands == [["taskkill", "/PID", "456", "/T", "/F"]]
    assert process.killed is False


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

"""Regression tests for bounded, recoverable Plotly image export."""

from __future__ import annotations

import io
import threading
from pathlib import Path

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


def test_real_sis_multi_file_report_with_every_optional_section(monkeypatch):
    fixture_paths = sorted(
        Path(__file__).resolve().parents[1].joinpath("testfile-sis").glob("*.sis")
    )[:2]
    assert len(fixture_paths) == 2

    files = []
    for path in fixture_paths:
        metadata, df, time_axis, sampling_rate = report._parse_any_file(
            path.read_bytes(), path.name
        )
        metadata["_filename"] = path.name
        files.append(
            {
                "name": path.name,
                "df": df,
                "time_axis": time_axis,
                "metadata": metadata,
                "sampling_rate": sampling_rate,
            }
        )

    def fake_image_export(*_args, **_kwargs):
        buffer = io.BytesIO()
        Image.new("RGB", (80, 48), "white").save(buffer, format="PNG")
        return buffer.getvalue()

    monkeypatch.setattr(report, "_to_image", fake_image_export)
    pdf_bytes = report._build_vibraport_pdf(
        files,
        {
            "project_name": "Export recovery regression",
            "operator": "Vibraport test",
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

"""Focused coverage for the isolated Plotly/Kaleido 1 report renderer."""

from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sys
import time

import pytest

from core import report_renderer


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only start method")
def test_default_posix_context_uses_fork_without_reimporting_streamlit():
    assert report_renderer._default_multiprocessing_context().get_start_method() == "fork"


def test_frozen_context_uses_spawn_for_pyinstaller(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert report_renderer._default_multiprocessing_context().get_start_method() == "spawn"


def _fake_worker(connection, _browser_path, mode, counter):
    if mode == "startup_error":
        connection.send(
            {
                "type": "startup_error",
                "code": report_renderer.BrowserStartupError.code,
                "message": "browser blocked by policy",
            }
        )
        return
    connection.send({"type": "ready"})
    while True:
        request = connection.recv()
        if request["command"] == "shutdown":
            connection.send({"type": "stopped"})
            return
        with counter.get_lock():
            call_index = counter.value
            counter.value += 1
        if mode == "timeout_once" and call_index == 0:
            time.sleep(30)
        elif mode == "timeout_twice_then_success" and call_index < 2:
            time.sleep(30)
        elif mode == "crash":
            os._exit(23)
        else:
            connection.send({"type": "result", "image": b"rendered-image"})


def _browser(tmp_path: Path) -> report_renderer.BrowserSelection:
    executable = tmp_path / "chrome"
    executable.write_text("browser", encoding="utf-8")
    executable.chmod(0o755)
    return report_renderer.BrowserSelection(
        "Google Chrome", str(executable), "test"
    )


def _manager(mode: str):
    context = multiprocessing.get_context("spawn")
    counter = context.Value("i", 0)
    manager = report_renderer.RendererManager(
        worker_target=_fake_worker,
        worker_args=(mode, counter),
        context=context,
    )
    return manager, counter


def test_valid_explicit_browser_path_is_respected(tmp_path):
    browser_path = tmp_path / "custom-browser"
    browser_path.write_text("browser", encoding="utf-8")
    browser_path.chmod(0o755)

    selected = report_renderer.discover_browser(
        env={"BROWSER_PATH": str(browser_path)},
        platform_name="linux",
        which=lambda _name: None,
    )

    assert selected.path == str(browser_path.resolve())
    assert selected.source == "BROWSER_PATH"


def test_explicit_firefox_path_is_rejected(tmp_path):
    firefox = tmp_path / "firefox"
    firefox.write_text("browser", encoding="utf-8")
    firefox.chmod(0o755)

    with pytest.raises(report_renderer.BrowserNotFoundError, match="Firefox"):
        report_renderer.discover_browser(
            env={"BROWSER_PATH": str(firefox)},
            platform_name="linux",
            which=lambda _name: None,
        )


def test_chrome_is_selected_before_edge(tmp_path):
    chrome = tmp_path / "google-chrome"
    edge = tmp_path / "microsoft-edge"
    for executable in (chrome, edge):
        executable.write_text("browser", encoding="utf-8")
        executable.chmod(0o755)
    found = {
        "google-chrome": str(chrome),
        "microsoft-edge": str(edge),
    }

    selected = report_renderer.discover_browser(
        env={}, platform_name="linux", which=found.get
    )

    assert selected.name == "Google Chrome"
    assert selected.path == str(chrome.resolve())


def test_edge_is_used_when_chrome_is_unavailable(tmp_path):
    edge = tmp_path / "microsoft-edge-stable"
    edge.write_text("browser", encoding="utf-8")
    edge.chmod(0o755)

    selected = report_renderer.discover_browser(
        env={},
        platform_name="linux",
        which=lambda name: str(edge) if name == "microsoft-edge-stable" else None,
    )

    assert selected.name == "Microsoft Edge"
    assert selected.path == str(edge.resolve())


def test_windows_standard_locations_prefer_chrome_over_edge(tmp_path):
    program_files = tmp_path / "Program Files"
    chrome = program_files / "Google" / "Chrome" / "Application" / "chrome.exe"
    edge = program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    for executable in (chrome, edge):
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("browser", encoding="utf-8")
        executable.chmod(0o755)

    selected = report_renderer.discover_browser(
        env={"PROGRAMFILES": str(program_files), "PROGRAMFILES(X86)": ""},
        platform_name="win32",
        which=lambda _name: None,
    )

    assert selected.name == "Google Chrome"
    assert selected.path == str(chrome.resolve())


def test_windows_standard_location_falls_back_to_edge(tmp_path):
    program_files = tmp_path / "Program Files"
    edge = program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.write_text("browser", encoding="utf-8")
    edge.chmod(0o755)

    selected = report_renderer.discover_browser(
        env={"PROGRAMFILES": str(program_files), "PROGRAMFILES(X86)": ""},
        platform_name="win32",
        which=lambda _name: None,
    )

    assert selected.name == "Microsoft Edge"
    assert selected.path == str(edge.resolve())


def test_missing_browser_diagnostics_are_actionable(monkeypatch):
    monkeypatch.setattr(
        report_renderer,
        "discover_browser",
        lambda: (_ for _ in ()).throw(
            report_renderer.BrowserNotFoundError("install Chrome or Edge")
        ),
    )

    diagnostics = report_renderer.get_renderer_diagnostics()

    assert diagnostics.status == "unavailable"
    assert diagnostics.error_code == "missing_browser"
    assert "Chrome or Edge" in diagnostics.message
    assert diagnostics.plotly_version
    assert diagnostics.kaleido_version


def test_worker_is_reused_for_successive_renders(tmp_path):
    manager, counter = _manager("success")
    try:
        first = manager.render("{}", {"format": "png"}, browser=_browser(tmp_path))
        worker_pid = manager._process.pid
        second = manager.render("{}", {"format": "png"}, browser=_browser(tmp_path))

        assert first == second == b"rendered-image"
        assert manager._process.pid == worker_pid
        assert counter.value == 2
    finally:
        manager.shutdown()


def test_timeout_kills_worker_and_retry_recovers(tmp_path):
    manager, counter = _manager("timeout_once")
    try:
        result = manager.render(
            "{}",
            {"format": "png"},
            browser=_browser(tmp_path),
            timeout=0.5,
            attempts=2,
        )

        assert result == b"rendered-image"
        assert counter.value == 2
    finally:
        manager.shutdown()


def test_retry_exhaustion_does_not_poison_later_export(tmp_path):
    manager, counter = _manager("timeout_twice_then_success")
    browser = _browser(tmp_path)
    try:
        with pytest.raises(report_renderer.ImageExportTimeoutError, match="2 isolated attempts"):
            manager.render(
                "{}",
                {"format": "png"},
                browser=browser,
                timeout=0.5,
                attempts=2,
            )

        assert manager.render(
            "{}",
            {"format": "png"},
            browser=browser,
            timeout=0.5,
            attempts=2,
        ) == b"rendered-image"
        assert counter.value == 3
    finally:
        manager.shutdown()


def test_renderer_crash_is_identified_after_retry(tmp_path):
    manager, _counter = _manager("crash")
    try:
        with pytest.raises(report_renderer.RendererCrashError, match="exit code 23"):
            manager.render(
                "{}",
                {"format": "png"},
                browser=_browser(tmp_path),
                timeout=2,
                attempts=2,
            )
    finally:
        manager.shutdown()


def test_crash_exit_code_waits_for_windows_process_state_update():
    class DelayedExitProcess:
        exitcode = None

        def join(self, timeout=None):
            assert timeout == report_renderer.CRASH_EXITCODE_WAIT_SECONDS
            self.exitcode = 23

    assert report_renderer._reap_process_exit_code(DelayedExitProcess()) == 23


def test_browser_startup_failure_is_identified(tmp_path):
    manager, _counter = _manager("startup_error")
    try:
        with pytest.raises(report_renderer.BrowserStartupError, match="could not start"):
            manager.render(
                "{}",
                {"format": "png"},
                browser=_browser(tmp_path),
                timeout=2,
                attempts=2,
            )
    finally:
        manager.shutdown()


def test_windows_cleanup_uses_taskkill_for_entire_process_tree(monkeypatch):
    class FakeProcess:
        pid = 456

        def __init__(self):
            self.running = True
            self.killed = False

        def is_alive(self):
            return self.running

        def join(self, timeout=None):
            return None

        def kill(self):
            self.killed = True
            self.running = False

        terminate = kill

    process = FakeProcess()
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        process.running = False

    monkeypatch.setattr(report_renderer.os, "name", "nt")
    monkeypatch.setattr(report_renderer.subprocess, "run", fake_run)

    report_renderer.terminate_process_tree(process)

    assert commands == [["taskkill", "/PID", "456", "/T", "/F"]]
    assert process.killed is False


def test_real_kaleido_render_when_supported_browser_is_available():
    try:
        report_renderer.discover_browser()
    except report_renderer.BrowserNotFoundError as exc:
        pytest.skip(str(exc))

    import plotly.graph_objects as go

    image = report_renderer.render_figure(
        go.Figure(go.Bar(x=["A", "B"], y=[1, 2])),
        width=320,
        height=180,
        scale=1,
    )
    assert image.startswith(b"\x89PNG")

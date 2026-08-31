from __future__ import annotations

import socket
from pathlib import Path

import launcher_windows


def test_bundle_root_points_to_checkout_in_development():
    expected = Path(launcher_windows.__file__).resolve().parent
    assert launcher_windows.bundle_root() == expected
    assert launcher_windows.app_script() == expected / "app.py"


def test_find_available_port_returns_bindable_local_port():
    port = launcher_windows.find_available_port()

    assert 0 < port < 65536
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((launcher_windows.HOST, port))


def test_streamlit_options_are_local_and_use_selected_port():
    options = launcher_windows.streamlit_options(54321)

    assert options["server.address"] == "127.0.0.1"
    assert options["server.port"] == 54321
    assert options["server.headless"] is True
    assert options["server.fileWatcherType"] == "none"
    assert options["global.developmentMode"] is False


def test_main_reports_startup_failure(monkeypatch):
    reported = []

    def fail():
        raise RuntimeError("simulated launcher failure")

    monkeypatch.setattr(launcher_windows, "run_streamlit", fail)
    monkeypatch.setattr(launcher_windows, "show_startup_error", reported.append)

    assert launcher_windows.main() == 1
    assert reported == ["simulated launcher failure"]

from __future__ import annotations

import socket
import sys
from types import SimpleNamespace
from pathlib import Path

import launcher_windows


def test_bundle_root_points_to_checkout_in_development():
    expected = Path(launcher_windows.__file__).resolve().parent
    assert launcher_windows.bundle_root() == expected
    assert launcher_windows.app_script() == expected / "app.py"
    assert launcher_windows.app_icon() == expected / "assets" / "icons" / "vibraport-logo.png"


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


def test_single_instance_state_round_trip(tmp_path):
    guard = launcher_windows.SingleInstanceGuard(tmp_path / "instance.json")
    guard._is_primary = True

    guard.publish_url("http://127.0.0.1:54321")

    assert guard.read_url() == "http://127.0.0.1:54321"
    guard.release()
    assert not guard.state_path.exists()


def test_single_instance_rejects_non_local_state(tmp_path):
    guard = launcher_windows.SingleInstanceGuard(tmp_path / "instance.json")
    guard.state_path.write_text('{"url": "https://example.com"}', encoding="utf-8")

    assert guard.read_url() is None


def test_controller_stops_attached_server():
    class FakeServer:
        stopped = False

        def stop(self):
            self.stopped = True

    controller = launcher_windows.AppController()
    server = FakeServer()
    controller.attach_server(server)

    controller.request_shutdown()

    assert server.stopped is True


def test_controller_stops_server_attached_after_exit_request():
    class FakeServer:
        stopped = False

        def stop(self):
            self.stopped = True

    controller = launcher_windows.AppController()
    controller.request_shutdown()
    server = FakeServer()

    controller.attach_server(server)

    assert server.stopped is True


def test_tray_menu_opens_browser_and_stops_server(monkeypatch):
    class FakeMenuItem:
        def __init__(self, text, action, default=False):
            self.text = text
            self.action = action
            self.default = default

    class FakeMenu(tuple):
        def __new__(cls, *items):
            return super().__new__(cls, items)

    class FakeIcon:
        def __init__(self, name, image, title, menu):
            self.name = name
            self.image = image
            self.title = title
            self.menu = menu
            self.stopped = False

        def stop(self):
            self.stopped = True

    fake_pystray = SimpleNamespace(
        Icon=FakeIcon,
        Menu=FakeMenu,
        MenuItem=FakeMenuItem,
    )
    monkeypatch.setitem(sys.modules, "pystray", fake_pystray)

    controller = launcher_windows.AppController()
    controller.set_url("http://127.0.0.1:54321")
    opened = []
    monkeypatch.setattr(controller, "open_browser", lambda: opened.append(True))
    shutdown = []
    monkeypatch.setattr(controller, "request_shutdown", lambda: shutdown.append(True))

    icon = launcher_windows.create_tray_icon(controller)
    open_item, exit_item = icon.menu
    open_item.action(icon, open_item)
    exit_item.action(icon, exit_item)

    assert open_item.text == "Open Vibraport"
    assert open_item.default is True
    assert exit_item.text == "Exit Vibraport"
    assert opened == [True]
    assert shutdown == [True]
    assert icon.stopped is True


def test_managed_server_registers_with_controller():
    class BaseServer:
        def __init__(self, marker):
            self.marker = marker

    attached = []
    controller = launcher_windows.AppController()
    controller.attach_server = attached.append
    ManagedServer = launcher_windows.managed_server_class(BaseServer, controller)

    server = ManagedServer("created")

    assert server.marker == "created"
    assert attached == [server]


def test_main_reports_startup_failure(monkeypatch):
    reported = []

    class FakeGuard:
        def acquire(self):
            return True

        def release(self):
            pass

    def fail(_guard):
        raise RuntimeError("simulated launcher failure")

    monkeypatch.setattr(launcher_windows, "SingleInstanceGuard", FakeGuard)
    monkeypatch.setattr(launcher_windows, "run_streamlit", fail)
    monkeypatch.setattr(launcher_windows, "show_startup_error", reported.append)

    assert launcher_windows.main() == 1
    assert reported == ["simulated launcher failure"]


def test_second_launch_reopens_existing_instance(monkeypatch):
    class FakeGuard:
        released = False

        def acquire(self):
            return False

        def open_existing(self):
            return True

        def release(self):
            self.released = True

    guard = FakeGuard()
    monkeypatch.setattr(launcher_windows, "SingleInstanceGuard", lambda: guard)

    assert launcher_windows.main() == 0
    assert guard.released is True

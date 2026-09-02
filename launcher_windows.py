"""Windows entry point for the frozen Vibraport distribution.

The launcher runs Streamlit in-process so it works both from a normal Python
checkout and from a PyInstaller executable. It intentionally contains no
packaging-specific imports; those will be supplied by the later spec file.
"""

from __future__ import annotations

import socket
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 30.0
INSTANCE_MUTEX_NAME = "Local\\Vibraport.SingleInstance"


def bundle_root() -> Path:
    """Return the source or PyInstaller bundle directory."""

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parent


def app_script() -> Path:
    """Resolve the bundled Streamlit entry point and fail clearly if absent."""

    script = bundle_root() / "app.py"
    if not script.is_file():
        raise FileNotFoundError(f"Vibraport application entry point not found: {script}")
    return script


def app_icon() -> Path:
    """Resolve the PNG used by the Windows tray icon."""

    icon = bundle_root() / "assets" / "icons" / "vibraport-logo.png"
    if not icon.is_file():
        raise FileNotFoundError(f"Vibraport application icon not found: {icon}")
    return icon


def find_available_port(host: str = HOST) -> int:
    """Ask Windows for an unused local TCP port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((host, 0))
        return int(listener.getsockname()[1])


def streamlit_options(port: int) -> dict[str, object]:
    """Build the fixed local-only Streamlit configuration for the launcher."""

    return {
        "browser.gatherUsageStats": False,
        "global.developmentMode": False,
        "server.address": HOST,
        "server.fileWatcherType": "none",
        "server.headless": True,
        "server.port": port,
        "server.runOnSave": False,
    }


def wait_for_server_and_open(
    url: str,
    timeout: float = STARTUP_TIMEOUT_SECONDS,
) -> bool:
    """Open the browser after Streamlit reports healthy, or time out quietly."""

    health_url = f"{url}/_stcore/health"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if response.status == 200:
                    webbrowser.open_new(url)
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    return False


class SingleInstanceGuard:
    """Own a Windows mutex and publish the primary instance's local URL."""

    def __init__(self, state_path: Path | None = None) -> None:
        if state_path is None:
            state_root = Path(
                os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            ) / "Vibraport"
            state_path = state_root / "instance.json"
        self.state_path = state_path
        self._mutex_handle: int | None = None
        self._is_primary = False

    def acquire(self) -> bool:
        """Return true for the primary instance and false for later launches."""

        if sys.platform != "win32":
            self._is_primary = True
            return True

        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.LPCWSTR,
        )
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(None, False, INSTANCE_MUTEX_NAME)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        error_already_exists = 183
        if ctypes.get_last_error() == error_already_exists:
            kernel32.CloseHandle(handle)
            return False

        self._mutex_handle = handle if isinstance(handle, int) else int(handle.value)
        self._is_primary = True
        return True

    def publish_url(self, url: str) -> None:
        """Atomically publish the primary instance URL for later launches."""

        if not self._is_primary:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.state_path.with_suffix(".tmp")
        temporary_path.write_text(
            json.dumps({"pid": os.getpid(), "url": url}),
            encoding="utf-8",
        )
        temporary_path.replace(self.state_path)

    def read_url(self) -> str | None:
        """Return a safe localhost URL published by the primary instance."""

        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            url = str(payload["url"])
            parsed = urllib.parse.urlparse(url)
            port = parsed.port
            if (
                parsed.scheme == "http"
                and parsed.hostname == HOST
                and port is not None
                and 0 < port < 65536
                and parsed.path in {"", "/"}
            ):
                return f"http://{HOST}:{port}"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass
        return None

    def open_existing(self, timeout: float = STARTUP_TIMEOUT_SECONDS) -> bool:
        """Wait for the primary URL, reopen it, and return whether it succeeded."""

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            url = self.read_url()
            if url:
                return wait_for_server_and_open(
                    url,
                    timeout=max(0.1, deadline - time.monotonic()),
                )
            time.sleep(0.2)
        return False

    def release(self) -> None:
        """Remove instance state and release the owned Windows mutex."""

        if self._is_primary:
            try:
                self.state_path.unlink()
            except FileNotFoundError:
                pass

        if self._mutex_handle is not None and sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            kernel32.CloseHandle(self._mutex_handle)

        self._mutex_handle = None
        self._is_primary = False


class AppController:
    """Coordinate browser, tray, and Streamlit server lifecycle actions."""

    def __init__(self) -> None:
        self.url: str | None = None
        self._server = None
        self._shutdown_requested = threading.Event()
        self._lock = threading.Lock()

    def set_url(self, url: str) -> None:
        self.url = url

    def open_browser(self) -> None:
        if not self.url:
            return
        threading.Thread(
            target=wait_for_server_and_open,
            args=(self.url,),
            name="vibraport-browser-launcher",
            daemon=True,
        ).start()

    def attach_server(self, server) -> None:
        with self._lock:
            self._server = server
            shutdown_requested = self._shutdown_requested.is_set()
        if shutdown_requested:
            server.stop()

    def request_shutdown(self) -> None:
        """Ask Streamlit's server to finish sessions and stop its event loop."""

        self._shutdown_requested.set()
        with self._lock:
            server = self._server
        if server is not None:
            server.stop()


def create_tray_icon(controller: AppController):
    """Create the native Windows tray icon and its two lifecycle commands."""

    import pystray
    from PIL import Image

    image = Image.open(app_icon()).convert("RGBA")

    def open_vibraport(_icon, _item) -> None:
        controller.open_browser()

    def exit_vibraport(icon, _item) -> None:
        controller.request_shutdown()
        icon.stop()

    return pystray.Icon(
        "Vibraport",
        image,
        "Vibraport",
        menu=pystray.Menu(
            pystray.MenuItem("Open Vibraport", open_vibraport, default=True),
            pystray.MenuItem("Exit Vibraport", exit_vibraport),
        ),
    )


def start_tray_icon(controller: AppController):
    """Start the Windows tray event loop without blocking Streamlit."""

    if sys.platform != "win32":
        return None
    icon = create_tray_icon(controller)
    threading.Thread(
        target=icon.run,
        name="vibraport-system-tray",
        daemon=True,
    ).start()
    return icon


def managed_server_class(base_server, controller: AppController):
    """Return a Streamlit Server subclass captured by the lifecycle controller."""

    class ManagedServer(base_server):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            controller.attach_server(self)

    return ManagedServer


def run_streamlit(instance_guard: SingleInstanceGuard | None = None) -> None:
    """Run Vibraport on localhost until the user closes the process."""

    from streamlit.web import bootstrap

    port = find_available_port()
    url = f"http://{HOST}:{port}"
    options = streamlit_options(port)
    controller = AppController()
    controller.set_url(url)
    if instance_guard is not None:
        instance_guard.publish_url(url)
    tray_icon = start_tray_icon(controller)
    controller.open_browser()

    # Capture the Server instance created inside Streamlit's bootstrap layer so
    # the tray Exit command can call its graceful stop method from another
    # thread. This API is pinned by requirements-windows.txt and smoke-tested.
    base_server = bootstrap.Server

    bootstrap.Server = managed_server_class(base_server, controller)

    # The programmatic bootstrap API does not apply flag options before its
    # server is created, so load them explicitly. The CLI normally performs
    # this step before calling bootstrap.run().
    try:
        bootstrap.load_config_options(options)
        bootstrap.run(
            str(app_script()),
            False,
            [],
            options,
        )
    finally:
        bootstrap.Server = base_server
        if tray_icon is not None:
            tray_icon.stop()


def show_startup_error(message: str) -> None:
    """Show a native Windows error dialog, with a stderr fallback elsewhere."""

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Vibraport startup error", 0x10)
    else:
        print(f"Vibraport startup error: {message}", file=sys.stderr)


def main() -> int:
    instance_guard = SingleInstanceGuard()
    try:
        if not instance_guard.acquire():
            if instance_guard.open_existing():
                return 0
            show_startup_error(
                "Vibraport is already running, but its browser interface "
                "could not be reopened. Use the system-tray icon or end the "
                "existing Vibraport process in Task Manager."
            )
            return 1
        run_streamlit(instance_guard)
    except Exception as exc:  # The packaged app must surface startup failures.
        show_startup_error(str(exc))
        return 1
    finally:
        instance_guard.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

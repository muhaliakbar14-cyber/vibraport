"""Windows entry point for a future frozen Vibraport distribution.

The launcher runs Streamlit in-process so it works both from a normal Python
checkout and from a PyInstaller executable. It intentionally contains no
packaging-specific imports; those will be supplied by the later spec file.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


HOST = "127.0.0.1"
STARTUP_TIMEOUT_SECONDS = 30.0


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


def run_streamlit() -> None:
    """Run Vibraport on localhost until the user closes the process."""

    from streamlit.web import bootstrap

    port = find_available_port()
    url = f"http://{HOST}:{port}"
    options = streamlit_options(port)
    browser_thread = threading.Thread(
        target=wait_for_server_and_open,
        args=(url,),
        name="vibraport-browser-launcher",
        daemon=True,
    )
    browser_thread.start()

    # The programmatic bootstrap API does not apply flag options before its
    # server is created, so load them explicitly. The CLI normally performs
    # this step before calling bootstrap.run().
    bootstrap.load_config_options(options)
    bootstrap.run(
        str(app_script()),
        False,
        [],
        options,
    )


def show_startup_error(message: str) -> None:
    """Show a native Windows error dialog, with a stderr fallback elsewhere."""

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Vibraport startup error", 0x10)
    else:
        print(f"Vibraport startup error: {message}", file=sys.stderr)


def main() -> int:
    try:
        run_streamlit()
    except Exception as exc:  # The packaged app must surface startup failures.
        show_startup_error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

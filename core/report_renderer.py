"""Bounded Plotly/Kaleido 1 image rendering for PDF reports.

The browser lives in an isolated, reusable worker process. If browser startup
or a render blocks, the complete worker/browser process tree is terminated and
one clean retry is attempted without interrupting Streamlit.
"""

from __future__ import annotations

import atexit
from dataclasses import asdict, dataclass
from importlib import metadata as importlib_metadata
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
from typing import Callable, Mapping


DEFAULT_RENDER_TIMEOUT_SECONDS = 60.0
DEFAULT_RENDER_ATTEMPTS = 2
MINIMUM_BROWSER_STARTUP_TIMEOUT_SECONDS = 5.0
WORKER_SHUTDOWN_TIMEOUT_SECONDS = 5.0
CRASH_EXITCODE_WAIT_SECONDS = 1.0


class RendererError(RuntimeError):
    """Base error for actionable chart-renderer failures."""

    code = "render_failed"


class BrowserNotFoundError(RendererError):
    code = "missing_browser"


class BrowserStartupError(RendererError):
    code = "browser_startup_failure"


class ImageExportTimeoutError(RendererError):
    code = "render_timeout"


class RendererCrashError(RendererError):
    code = "renderer_crash"


@dataclass(frozen=True)
class BrowserSelection:
    name: str
    path: str
    source: str


@dataclass(frozen=True)
class RendererDiagnostics:
    status: str
    browser_name: str | None
    browser_path: str | None
    browser_source: str | None
    plotly_version: str
    kaleido_version: str
    error_code: str | None = None
    message: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _package_version(name: str) -> str:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return "not installed"


def _browser_name(path: Path, fallback: str = "Chromium browser") -> str:
    lowered = path.name.lower()
    full = str(path).lower()
    if "firefox" in lowered or "firefox" in full:
        return "Firefox"
    if "edge" in lowered or "microsoft edge" in full:
        return "Microsoft Edge"
    if "chrome" in lowered or "google/chrome" in full or "google\\chrome" in full:
        return "Google Chrome"
    return fallback


def _usable_browser_file(path: Path) -> bool:
    if not path.is_file():
        return False
    return os.name == "nt" or os.access(path, os.X_OK)


def _standard_browser_candidates(
    *,
    platform_name: str,
    env: Mapping[str, str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return Chrome candidates first and Edge candidates second."""

    chrome: list[tuple[str, str]] = []
    edge: list[tuple[str, str]] = []
    if platform_name == "win32":
        local = env.get("LOCALAPPDATA", "")
        program_files = env.get("PROGRAMFILES", r"C:\Program Files")
        program_files_x86 = env.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        chrome.extend(
            ("Google Chrome", path)
            for path in (
                os.path.join(local, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
            )
            if path
        )
        edge.extend(
            ("Microsoft Edge", path)
            for path in (
                os.path.join(local, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
            )
            if path
        )
    elif platform_name == "darwin":
        chrome.append(
            (
                "Google Chrome",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            )
        )
        edge.append(
            (
                "Microsoft Edge",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            )
        )
    else:
        chrome.extend(
            ("Google Chrome", path)
            for path in (
                "/usr/bin/google-chrome-stable",
                "/usr/bin/google-chrome",
                "/opt/google/chrome/chrome",
            )
        )
        edge.extend(
            ("Microsoft Edge", path)
            for path in (
                "/usr/bin/microsoft-edge-stable",
                "/usr/bin/microsoft-edge",
                "/opt/microsoft/msedge/msedge",
            )
        )
    return chrome, edge


def discover_browser(
    *,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> BrowserSelection:
    """Select explicit BROWSER_PATH, otherwise Chrome first and then Edge."""

    environment = os.environ if env is None else env
    platform_key = sys.platform if platform_name is None else platform_name
    explicit = environment.get("BROWSER_PATH", "").strip().strip('"')
    if explicit:
        path = Path(os.path.expandvars(explicit)).expanduser()
        if _browser_name(path) == "Firefox":
            raise BrowserNotFoundError(
                "BROWSER_PATH points to Firefox, which Kaleido cannot use. Set "
                "BROWSER_PATH to Google Chrome or Microsoft Edge instead."
            )
        if not _usable_browser_file(path):
            raise BrowserNotFoundError(
                f"BROWSER_PATH does not point to a runnable browser: {path}. "
                "Set it to an installed Google Chrome or Microsoft Edge executable."
            )
        return BrowserSelection(_browser_name(path), str(path.resolve()), "BROWSER_PATH")

    chrome_paths, edge_paths = _standard_browser_candidates(
        platform_name=platform_key,
        env=environment,
    )
    chrome_names = (
        ("Google Chrome", "chrome.exe"),
        ("Google Chrome", "google-chrome-stable"),
        ("Google Chrome", "google-chrome"),
        ("Google Chrome", "chrome"),
    )
    edge_names = (
        ("Microsoft Edge", "msedge.exe"),
        ("Microsoft Edge", "microsoft-edge-stable"),
        ("Microsoft Edge", "microsoft-edge"),
        ("Microsoft Edge", "msedge"),
    )

    for name, candidate in [*chrome_paths, *chrome_names, *edge_paths, *edge_names]:
        if os.path.isabs(candidate):
            resolved = Path(candidate)
            source = "standard location"
        else:
            found = which(candidate)
            if not found:
                continue
            resolved = Path(found)
            source = "PATH"
        if _usable_browser_file(resolved):
            return BrowserSelection(name, str(resolved.resolve()), source)

    raise BrowserNotFoundError(
        "No supported browser was found for PDF chart rendering. Install Google "
        "Chrome (preferred) or Microsoft Edge, or set BROWSER_PATH to its executable. "
        "METIS Analytics will not download a browser automatically; all non-PDF "
        "workflows remain available offline."
    )


def _classify_worker_exception(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    startup_markers = (
        "chromenotfound",
        "browserfailed",
        "browserdeps",
        "failed to start",
        "failed to open",
        "cannot start",
        "could not start",
        "permissionerror",
    )
    if any(marker in text for marker in startup_markers):
        return BrowserStartupError.code
    return RendererError.code


def _renderer_worker(connection, browser_path: str) -> None:
    """Own one persistent Kaleido sync server inside an isolated process."""

    if os.name != "nt":
        try:
            os.setsid()
        except OSError:
            pass
    os.environ["BROWSER_PATH"] = browser_path

    try:
        import kaleido

        kaleido.start_sync_server()
        connection.send({"type": "ready"})
    except BaseException as exc:  # Report startup diagnostics to the parent.
        try:
            connection.send(
                {
                    "type": "startup_error",
                    "code": _classify_worker_exception(exc),
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
        connection.close()
        return

    try:
        while True:
            try:
                request = connection.recv()
            except EOFError:
                break
            command = request.get("command")
            if command == "shutdown":
                connection.send({"type": "stopped"})
                break
            if command != "render":
                connection.send(
                    {
                        "type": "render_error",
                        "code": RendererError.code,
                        "message": f"Unknown renderer command: {command!r}",
                    }
                )
                continue
            try:
                figure = json.loads(request["figure_json"])
                image = kaleido.calc_fig_sync(figure, opts=request["options"])
                connection.send({"type": "result", "image": image})
            except BaseException as exc:
                connection.send(
                    {
                        "type": "render_error",
                        "code": _classify_worker_exception(exc),
                        "message": f"{type(exc).__name__}: {exc}",
                    }
                )
    finally:
        try:
            kaleido.stop_sync_server()
        except BaseException:
            pass
        connection.close()


def _default_multiprocessing_context():
    """Choose a start method that is safe for Streamlit and frozen Windows."""

    if os.name == "nt" or getattr(sys, "frozen", False):
        # PyInstaller dispatches this through freeze_support() in the launcher.
        return multiprocessing.get_context("spawn")
    # spawn and forkserver both import the current __main__ file in a fresh
    # interpreter. Under Streamlit that file is app.py, so importing it as a
    # worker can execute the page script without a ScriptRunContext. The worker
    # does not inherit an initialized browser; Kaleido is imported and started
    # only inside _renderer_worker after this fork.
    return multiprocessing.get_context("fork")


def terminate_process_tree(process, *, wait_seconds: float = WORKER_SHUTDOWN_TIMEOUT_SECONDS) -> None:
    """Terminate a renderer worker and every Chrome/Edge child it owns."""

    if process is None:
        return
    try:
        if not process.is_alive():
            process.join(timeout=0)
            return
    except (AttributeError, ValueError):
        return

    if os.name == "nt" and process.pid:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=wait_seconds,
                creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    elif process.pid:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    process.join(timeout=wait_seconds)
    if process.is_alive():
        if os.name != "nt" and process.pid:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        try:
            process.kill()
        except (AttributeError, OSError):
            process.terminate()
        process.join(timeout=wait_seconds)


def _reap_process_exit_code(process, *, wait_seconds: float = CRASH_EXITCODE_WAIT_SECONDS):
    """Allow Windows multiprocessing to publish an exited worker's return code."""

    if process is None:
        return None
    try:
        process.join(timeout=wait_seconds)
    except (AssertionError, ValueError):
        pass
    return process.exitcode


class RendererManager:
    """Serialize requests through one reusable, replaceable render worker."""

    def __init__(
        self,
        *,
        worker_target: Callable = _renderer_worker,
        worker_args: tuple = (),
        context=None,
    ) -> None:
        self._context = context or _default_multiprocessing_context()
        self._worker_target = worker_target
        self._worker_args = worker_args
        self._process = None
        self._connection = None
        self._browser_path: str | None = None
        self._lock = threading.Lock()
        self._atexit_registered = False

    def _reset(self) -> None:
        connection, process = self._connection, self._process
        self._connection = None
        self._process = None
        self._browser_path = None
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        terminate_process_tree(process)

    def _start(self, browser: BrowserSelection, timeout: float) -> None:
        if (
            self._process is not None
            and self._process.is_alive()
            and self._browser_path == browser.path
        ):
            return
        self._reset()
        parent_connection, child_connection = self._context.Pipe(duplex=True)
        process = self._context.Process(
            target=self._worker_target,
            args=(child_connection, browser.path, *self._worker_args),
            name="metis-report-renderer",
            daemon=False,
        )
        process.start()
        # multiprocessing registers its own process-join exit callback during
        # the first start. Register our graceful shutdown afterward so LIFO
        # ordering stops Kaleido before multiprocessing attempts that join.
        if not self._atexit_registered:
            atexit.register(self.shutdown)
            self._atexit_registered = True
        child_connection.close()
        self._connection = parent_connection
        self._process = process
        self._browser_path = browser.path

        if not parent_connection.poll(timeout):
            self._reset()
            raise BrowserStartupError(
                f"{browser.name} did not start within {timeout:g} seconds at "
                f"{browser.path}. Check security policy/antivirus access and that the "
                "browser can launch normally."
            )
        try:
            response = parent_connection.recv()
        except (EOFError, OSError) as exc:
            self._reset()
            raise RendererCrashError(
                f"The renderer worker exited while starting {browser.name}: {exc}"
            ) from None
        if response.get("type") != "ready":
            self._reset()
            raise BrowserStartupError(
                f"{browser.name} could not start from {browser.path}: "
                f"{response.get('message', 'unknown startup error')}"
            )

    def _render_once(
        self,
        figure_json: str,
        options: dict[str, object],
        browser: BrowserSelection,
        timeout: float,
    ) -> bytes:
        self._start(
            browser,
            max(timeout, MINIMUM_BROWSER_STARTUP_TIMEOUT_SECONDS),
        )
        connection = self._connection
        process = self._process
        try:
            connection.send(
                {
                    "command": "render",
                    "figure_json": figure_json,
                    "options": options,
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            self._reset()
            raise RendererCrashError("The renderer worker crashed before rendering began.") from None

        if not connection.poll(timeout):
            self._reset()
            raise ImageExportTimeoutError(
                f"Chart rendering exceeded the {timeout:g}-second limit using "
                f"{browser.name} at {browser.path}."
            )
        try:
            response = connection.recv()
        except (EOFError, OSError):
            # On Windows the pipe can reach EOF just before multiprocessing's
            # process handle reports its final exit code. Briefly reap the
            # already-exiting worker so diagnostics retain the real code.
            exit_code = _reap_process_exit_code(process)
            self._reset()
            raise RendererCrashError(
                f"The renderer worker crashed (exit code {exit_code}) while using "
                f"{browser.name}."
            ) from None

        response_type = response.get("type")
        if response_type == "result":
            return response["image"]
        message = response.get("message", "unknown renderer error")
        code = response.get("code")
        self._reset()
        if code == BrowserStartupError.code:
            raise BrowserStartupError(
                f"{browser.name} was found at {browser.path} but could not render a "
                f"chart: {message}"
            )
        raise RendererError(f"Chart rendering failed in the isolated worker: {message}")

    def render(
        self,
        figure_json: str,
        options: dict[str, object],
        *,
        browser: BrowserSelection,
        timeout: float = DEFAULT_RENDER_TIMEOUT_SECONDS,
        attempts: int = DEFAULT_RENDER_ATTEMPTS,
    ) -> bytes:
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        with self._lock:
            last_error: RendererError | None = None
            for attempt in range(1, attempts + 1):
                try:
                    return self._render_once(figure_json, options, browser, timeout)
                except RendererError as exc:
                    last_error = exc
                    self._reset()
                    if attempt == attempts:
                        break
            assert last_error is not None
            error_type = type(last_error)
            raise error_type(
                f"{last_error} METIS Analytics made {attempts} isolated attempts; "
                "the timed-out/crashed browser process tree was removed after each failure."
            ) from None

    def shutdown(self) -> None:
        with self._lock:
            if self._connection is not None and self._process is not None:
                try:
                    self._connection.send({"command": "shutdown"})
                    if self._connection.poll(WORKER_SHUTDOWN_TIMEOUT_SECONDS):
                        self._connection.recv()
                    self._process.join(timeout=WORKER_SHUTDOWN_TIMEOUT_SECONDS)
                except (BrokenPipeError, EOFError, OSError):
                    pass
            self._reset()


_renderer_manager = RendererManager()


def render_figure(
    figure,
    *,
    format: str = "png",
    width: int | None = None,
    height: int | None = None,
    scale: float | None = None,
    timeout: float = DEFAULT_RENDER_TIMEOUT_SECONDS,
    attempts: int = DEFAULT_RENDER_ATTEMPTS,
) -> bytes:
    """Render a Plotly figure to bytes through the isolated worker."""

    browser = discover_browser()
    if hasattr(figure, "to_json"):
        figure_json = figure.to_json()
    else:
        from plotly.utils import PlotlyJSONEncoder

        figure_json = json.dumps(figure, cls=PlotlyJSONEncoder)
    options = {"format": format}
    if width is not None:
        options["width"] = width
    if height is not None:
        options["height"] = height
    if scale is not None:
        options["scale"] = scale
    return _renderer_manager.render(
        figure_json,
        options,
        browser=browser,
        timeout=timeout,
        attempts=attempts,
    )


def get_renderer_diagnostics(*, run_self_test: bool = False) -> RendererDiagnostics:
    """Return versions/browser selection and optionally exercise a real render."""

    plotly_version = _package_version("plotly")
    kaleido_version = _package_version("kaleido")
    try:
        browser = discover_browser()
    except BrowserNotFoundError as exc:
        return RendererDiagnostics(
            status="unavailable",
            browser_name=None,
            browser_path=None,
            browser_source=None,
            plotly_version=plotly_version,
            kaleido_version=kaleido_version,
            error_code=exc.code,
            message=str(exc),
        )

    if not run_self_test:
        return RendererDiagnostics(
            status="browser_found",
            browser_name=browser.name,
            browser_path=browser.path,
            browser_source=browser.source,
            plotly_version=plotly_version,
            kaleido_version=kaleido_version,
        )

    try:
        import plotly.graph_objects as go

        render_figure(
            go.Figure(go.Scatter(x=[0, 1], y=[0, 1])),
            format="png",
            width=320,
            height=180,
            scale=1,
        )
    except RendererError as exc:
        return RendererDiagnostics(
            status="failed",
            browser_name=browser.name,
            browser_path=browser.path,
            browser_source=browser.source,
            plotly_version=plotly_version,
            kaleido_version=kaleido_version,
            error_code=exc.code,
            message=str(exc),
        )
    return RendererDiagnostics(
        status="healthy",
        browser_name=browser.name,
        browser_path=browser.path,
        browser_source=browser.source,
        plotly_version=plotly_version,
        kaleido_version=kaleido_version,
        message="The renderer self-test completed successfully.",
    )


def shutdown_renderer() -> None:
    _renderer_manager.shutdown()

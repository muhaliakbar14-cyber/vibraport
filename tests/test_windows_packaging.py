from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "packaging" / "vibraport_windows.spec"
BUILD_SCRIPT_PATH = ROOT / "packaging" / "build_windows.ps1"


def test_windows_requirements_are_fully_pinned():
    lines = (ROOT / "requirements-windows.txt").read_text(encoding="utf-8").splitlines()
    requirements = [line for line in lines if line and not line.startswith("#")]

    assert requirements
    assert all("==" in requirement for requirement in requirements)
    assert "plotly==5.24.1" in requirements
    assert "kaleido==0.2.1" in requirements
    assert "pystray==0.19.5" in requirements
    assert any(requirement.startswith("pyinstaller==") for requirement in requirements)


def test_pyinstaller_spec_is_valid_python_and_declares_required_data():
    spec_text = SPEC_PATH.read_text(encoding="utf-8")
    ast.parse(spec_text, filename=str(SPEC_PATH))

    assert 'PROJECT_ROOT / "app.py"' in spec_text
    assert 'PROJECT_ROOT / "assets"' in spec_text
    assert '"streamlit", "plotly", "kaleido"' in spec_text
    assert 'contents_directory="_internal"' in spec_text
    assert 'assets" / "icons" / "vibraport.ico"' in spec_text
    assert "console=False" in spec_text
    assert "COLLECT(" in spec_text


def test_build_script_enforces_windows_and_verifies_bundle_outputs():
    script = BUILD_SCRIPT_PATH.read_text(encoding="utf-8")

    assert "[System.Environment]::OSVersion.Platform" in script
    assert "-3.12 -m venv" in script
    assert "64-bit Python is required" in script
    assert "-m pytest -q" in script
    assert "-m PyInstaller" in script
    assert 'Join-Path $BundleRoot "Vibraport.exe"' in script
    assert 'Join-Path $RuntimeRoot "app.py"' in script


def test_logo_and_windows_icon_are_valid_small_icon_assets():
    logo_path = ROOT / "assets" / "icons" / "vibraport-logo.png"
    icon_path = ROOT / "assets" / "icons" / "vibraport.ico"

    with Image.open(logo_path) as logo:
        assert logo.size == (1024, 1024)
        rgba = logo.convert("RGBA")
        assert rgba.getchannel("A").getextrema() == (0, 255)
        opaque_colors = Counter(
            pixel[:3] for pixel in rgba.get_flattened_data() if pixel[3] >= 250
        )
        dominant_colors = {color for color, _count in opaque_colors.most_common(2)}
        assert dominant_colors == {(31, 47, 120), (255, 255, 255)}

    with Image.open(icon_path) as icon:
        assert {16, 24, 32, 48, 64, 128, 256}.issubset(
            {width for width, height in icon.info["sizes"] if width == height}
        )

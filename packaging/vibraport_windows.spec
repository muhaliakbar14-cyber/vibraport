# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir specification for the Windows Vibraport bundle."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parent

# Streamlit loads app.py dynamically, so its import graph is not visible from
# launcher_windows.py. Declare Vibraport's packages and top-level modules here.
hiddenimports = ["app", "config"]
for package_name in ("core", "optimizer", "pages", "regression"):
    hiddenimports += collect_submodules(package_name)
if sys.platform == "win32":
    hiddenimports.append("pystray._win32")

# Streamlit contains its compiled frontend; Kaleido 0.2.1 contains the browser
# runtime used for offline Plotly image export. collect_all preserves their
# package data, binaries, metadata, and dynamic submodules.
datas = [
    (str(PROJECT_ROOT / "app.py"), "."),
    (str(PROJECT_ROOT / ".streamlit" / "config.toml"), ".streamlit"),
    (str(PROJECT_ROOT / "assets"), "assets"),
]
binaries = []
for package_name in ("streamlit", "plotly", "kaleido"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package_name)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports


a = Analysis(
    [str(PROJECT_ROOT / "launcher_windows.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Vibraport",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
    icon=str(PROJECT_ROOT / "assets" / "icons" / "vibraport.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Vibraport",
)

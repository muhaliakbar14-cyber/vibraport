[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildVenv = Join-Path $RepoRoot ".venv-windows"
$Python = Join-Path $BuildVenv "Scripts\python.exe"
$Requirements = Join-Path $RepoRoot "requirements-windows.txt"
$Spec = Join-Path $RepoRoot "packaging\vibraport_windows.spec"
$DistPath = Join-Path $RepoRoot "dist"
$WorkPath = Join-Path $RepoRoot "build"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Vibraport's Windows executable must be built on Windows."
}

Push-Location $RepoRoot
try {
    if (-not (Test-Path $Python)) {
        $PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
        if (-not $PyLauncher) {
            throw "Python Launcher (py.exe) was not found. Install 64-bit CPython 3.12 first."
        }
        & $PyLauncher.Source -3.12 -m venv $BuildVenv
        if ($LASTEXITCODE -ne 0) {
            throw "Could not create the Python 3.12 build environment."
        }
    }

    & $Python -c "import struct, sys; assert sys.version_info[:2] == (3, 12), sys.version; assert struct.calcsize('P') * 8 == 64, '64-bit Python is required'"
    if ($LASTEXITCODE -ne 0) {
        throw "The Windows build environment must use CPython 3.12."
    }

    & $Python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed."
    }
    & $Python -m pip install --requirement $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw "Windows dependency installation failed."
    }

    if (-not $SkipTests) {
        & $Python -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed; the Windows bundle was not built."
        }
    }

    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --distpath $DistPath `
        --workpath $WorkPath `
        $Spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed."
    }

    $BundleRoot = Join-Path $DistPath "Vibraport"
    $RuntimeRoot = Join-Path $BundleRoot "_internal"
    $RequiredOutputs = @(
        (Join-Path $BundleRoot "Vibraport.exe"),
        (Join-Path $RuntimeRoot "app.py"),
        (Join-Path $RuntimeRoot ".streamlit\config.toml"),
        (Join-Path $RuntimeRoot "assets\fonts\Inter-Regular.ttf"),
        (Join-Path $RuntimeRoot "assets\icons\vibraport-logo.png")
    )
    foreach ($RequiredOutput in $RequiredOutputs) {
        if (-not (Test-Path $RequiredOutput)) {
            throw "Required bundle output is missing: $RequiredOutput"
        }
    }

    Write-Host "Portable Vibraport bundle created at: $BundleRoot"
    Write-Host "Next: launch Vibraport.exe and complete the clean-Windows UI/PDF smoke test."
}
finally {
    Pop-Location
}

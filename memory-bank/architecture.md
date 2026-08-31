# Architecture

Last updated: 2026-08-31.

## Runtime and Routing
- `app.py`: Streamlit entrypoint, file manager/session registry, parse caching, navigation, and explicit page routing.
- `launcher_windows.py`: Windows packaging entrypoint; selects a free localhost port, applies local-only Streamlit settings, waits for server health, and opens the default browser. It runs Streamlit in-process so it can later be frozen by PyInstaller.
- `.streamlit/config.toml`: hides Streamlit's automatic pages navigation.

## Windows Build Pipeline
- `requirements-windows.txt`: pinned CPython 3.12 application, test, and PyInstaller dependencies for reproducible Windows x64 builds.
- `packaging/vibraport_windows.spec`: PyInstaller `onedir` definition. It includes the dynamically loaded `app.py`, application packages, Streamlit/Plotly/Kaleido data and binaries, configuration, and font assets under the `_internal` runtime directory.
- `packaging/build_windows.ps1`: Windows-only build entrypoint. It creates `.venv-windows`, installs the pinned dependencies, runs the full test suite, builds the portable bundle, and checks required outputs.
- Target portable artifact: `dist/Vibraport/Vibraport.exe`; the installer remains a later step after the portable artifact passes clean-Windows testing.
- `pages/`: Data Overview, Signal Analysis, Signature Hole Analysis, attenuation/safe-zone analysis, monitoring, and PDF reporting.

## Domain and Analysis
- `core/waveform.py`: `.sis`/`.csv` parsing and derived acceleration/displacement channels.
- `core/metrics.py`, `core/fft_analysis.py`: measurement and frequency calculations.
- `core/compliance/standards.py`: standard/category registry and limit curves.
- `core/compliance/evaluator.py`: shared PASS/FAIL/REVIEW evaluation.
- `core/compliance/chart.py`: shared Plotly compliance-chart generation.
- `core/sni_chart.py`: compatibility wrapper for older SNI call sites.
- `core/scaling.py`, `core/engine.py`, `core/superposition.py`: Signature Hole Analysis simulation and USBM scaling.
- `regression/` and `optimizer/`: attenuation and delay-analysis logic.

## Report Pipeline
- `pages/report.py` builds ReportLab PDFs and exports Plotly figures through bounded Kaleido calls.
- `assets/fonts/Inter-*.ttf`: embedded professional typeface assets.
- Data Overview and Print Report call the same compliance registry, evaluator, and chart code so limits and statuses remain consistent.

## UX Conventions
- Keep Streamlit first-class.
- Cache expensive parsing by file content.
- Use `st.form` for grouped calculations and `st.fragment` where isolated reruns materially help.
- Use `width="stretch"` instead of deprecated `use_container_width=True` in touched code.
- Measurement location is explanatory context, not a compliance selector.

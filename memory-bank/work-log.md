# Work Log

## 2026-05-18
- Migrated project trajectory from Streamlit-centric flow to FastAPI + React web approach.
- Validated backend routes for auth-protected file listing and upload/parse.
- Fixed major integration blockers:
  - invalid token troubleshooting
  - environment variable mismatch across terminals
  - Supabase schema exposure/grants
  - missing storage bucket
- Confirmed end-to-end parse + storage + summary persistence works.
- Established React session/login + API session flow.
- Added/iterated workbench structure with file pane + feature tabs.
- Added report endpoint wiring and started report/graph fidelity work.
- Added initial tools endpoints for attenuation and SHA.
- Created this memory-bank folder and baseline docs.
- Completed tools migration pass for Step 1 and Step 2:
  - Expanded React Tools UI for Attenuation/Safe Zone (channel selection, safe zone controls, block-aware imports, regression/confidence display).
  - Expanded React Tools UI for SHA (window start/end, block, holes/rows/decks, deck delay, delay increments, results table).
  - Added SHA API input guardrails in FastAPI (`block`, delay increments/ranges, counts, generated grid checks).
- Verification run:
  - `python -m py_compile api/main.py` passed.
  - `npm run build` passed in `web/`.
  - `pytest -q tests/test_metrics.py tests/test_superposition.py tests/test_delay.py tests/test_regression.py` passed (`30 passed`).
- Implemented offline desktop v1 foundation:
  - Added `desktop_offline/workspace.py` for project/workspace pathing and project save/open helpers.
  - Added `desktop_offline/persistence.py` for SQLite-backed files/regression sessions/workspace autosave state.
  - Added `desktop_offline/services.py` with offline contracts for parse/details, SHA, attenuation, report generation, and state/session persistence.
  - Added `desktop_offline/ui_main.py` + `desktop_offline/app.py` PySide6 shell with:
    - left library + tabbed right workspace,
    - background worker execution for import (parse), SHA, and report generation,
    - interactive SHA Plotly chart (Qt WebEngine),
    - attenuation regression save/load UI path.
- Added offline docs and tests:
  - `docs/offline_desktop_v1.md`
  - `requirements_desktop.txt`
  - `tests/test_offline_service.py`
- Verification run:
  - `python -m py_compile desktop_offline/*.py` passed.
  - `pytest -q tests/test_offline_service.py` passed (`3 passed`).
- Extended offline desktop implementation:
  - Implemented full interactive Signal Analysis charts (velocity/acceleration/displacement/FFT) in desktop tab.
  - Implemented full interactive Monitoring charts (bargraph amplitude/frequency, per-channel selection).
  - Added fixture-locked parity tests in `tests/test_offline_parity.py` for summary/SHA/attenuation outputs.
  - Added packaging assets:
    - `packaging/vibraport_offline.spec`
    - `packaging/build_offline.sh`
    - `packaging/build_windows.ps1`
    - `packaging/prepare_linux_kerberos_libs.sh`
  - Fixed packaged runtime entrypoint import (`desktop_offline/app.py`) for PyInstaller mode.
  - Produced a successful `dist/VibraportOffline` onedir build in this environment and smoke-ran binary startup.
- Verification run:
  - `pytest -q tests/test_metrics.py tests/test_superposition.py tests/test_delay.py tests/test_regression.py tests/test_offline_service.py tests/test_offline_parity.py` passed (`36 passed`).

## 2026-05-25
- Executed immediate offline desktop packaging/parity follow-up task from handoff:
  - attempted Windows build command: `pwsh -File packaging/build_windows.ps1`
  - blocker observed: `/bin/sh: line 1: pwsh: command not found`
  - environment check confirms Linux host (`uname -a`), so Windows-host build cannot be completed here.
- Completed all in-environment verifications for offline track:
  - `pytest -q tests/test_metrics.py tests/test_superposition.py tests/test_delay.py tests/test_regression.py tests/test_offline_service.py tests/test_offline_parity.py` passed (`36 passed`).
  - `./packaging/build_offline.sh` succeeded and produced `dist/VibraportOffline`.
  - Offscreen artifact smoke startup (`QT_QPA_PLATFORM=offscreen timeout 20s ./dist/VibraportOffline/VibraportOffline_bin`) ran without Python traceback.

## 2026-08-18
- Reverted the repository back to the original Streamlit-only app.
- Restored the original self-contained `app.py` entrypoint.
- Removed the offline desktop, web, API, and Supabase branches from the working tree.
- Updated the memory-bank to treat the Streamlit path as the current source of truth.

## 2026-08-18
- Restored `.sis` upload/parsing support in the Streamlit app.
- Reintroduced `Print Report` navigation and wired it to `pages/report.py`.
- Restored the PPV registry/session plumbing needed by the report page.
- Verified `app.py` still parses with `python -m py_compile app.py`.

## 2026-08-18
- Reframed the project around a Streamlit-first product path.
- Preserved `.sis` parsing and the report page as required behavior.
- Set the next UX goal to reduce full-page reruns and blinking with `st.form` and `st.fragment`.
- Rewrote the memory-bank so another AI can continue from the updated direction.

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

## 2026-08-18 — Claude session: repo verification + SaaS direction
- Cloned repo from GitHub, independently verified (not just read docs): py_compile clean, 30/30 tests pass, .sis parser tested against 5 real hardware samples (Tellus/Gaia/DX/dual-block), .csv parser tested against 4 real samples, app boots and serves HTTP 200.
- Found and flagged stale `.streamlit/config.toml` key (`ui.hideSidebarNav`) — non-fatal, cleanup TODO.
- Discussed SaaS direction: sign-in + save/resume projects, staying free/simple. Recommended Streamlit (no rewrite) + Supabase (Auth/Postgres/Storage) + Streamlit Community Cloud, explicitly avoiding repeat of the 2026-05-18 FastAPI+React+Supabase complexity by keeping Streamlit as the whole app.
- Found reference GitHub templates: antoineross/streamlit-saas-starter (full SaaS w/ Stripe), AstraBert/streamlit_supabase_auth_ui (lighter auth-only), mkhorasani/Streamlit-Authenticator (no external service, YAML-based fallback).
- Decision: recommended writing a thin custom `supabase-py` auth wrapper rather than depending on a third-party Streamlit auth UI package.
- Noted hard constraint: Streamlit Community Cloud free tier has an ephemeral filesystem — any "save project" feature requires an external DB/storage regardless of which auth approach is chosen.

## 2026-08-19 — Claude session: rerun/blink fixes, real bugs found+fixed, 3 pages restored
- Implemented the agreed rerun/blink fixes: st.cache_data on file parsing, st.fragment on make_chart(), st.form on SHA Step 2 (10 blast-parameter inputs).
- Found and fixed while touching the same code (not originally requested, but blocking/adjacent): CSV file selection crash (AttributeError on bytes.read()), a 1000x time-unit mismatch between .sis (seconds) and .csv (ms) that broke SHA truncation and chart time axes for .sis files, .sis metadata key mismatch causing "Calibrated"/"Date & Time" to show N/A, and a stale .streamlit/config.toml key that was silently failing to hide Streamlit's auto-generated pages nav.
- User reported displacement "looks weird" — tested actual math against 5 real files, found no drift/trend bug (values numerically sane, physically correct magnitude). Could not reproduce; asked user for a screenshot/more detail. Proactively improved the integration to use scipy.signal.detrend(linear) instead of mean-subtraction-only, and fixed a related inconsistency where Block 2 (dual-geophone) channels had their own duplicated, less-robust copy of the same logic.
- Restored ppv_analysis.py (attenuation regression + safe zone calculator + SNI 7571 tables) and monitoring.py (bargraph "M" file viewer) into app.py's navigation — both were present in the repo but never imported since the "Restore Streamlit baseline" revert. Also restored signal_analysis.py (stacked seismogram with Block 2 support) on follow-up request.
- Integration required converting time_axis units back from the app's ms-normalized form to raw seconds for monitoring.py and signal_analysis.py, which both expect seconds. Added a guard so bargraph files don't crash waveform-only pages.
- Every fix verified by actually executing the code against real sample files (not just reading/compiling) — CSV/`.sis` parsing, bargraph channel detection, PPV regression pipeline, and signal_analysis's metrics functions were all run end-to-end with real data from testfile-sis/ and csv_test/. Full pytest suite (30/30) and a headless streamlit boot/HTTP-200 check both re-verified after every round of changes.
- Known open item: Math Analysis (inline in app.py) and Signal Analysis (pages/signal_analysis.py) now both exist with overlapping purpose — not consolidated, flagged in the welcome screen and next-steps.md.

## 2026-08-19 — Self-correction: inconsistent Signal Analysis wiring
- Found a real process error: in the prior session pass, the Signal Analysis nav entry, welcome-screen text, and routing `elif` block were already added to `app.py` — but the corresponding `import` was never added, and a leftover duplicate import (`signal_analysis, signal_analysis`) was present. This means the previous "done" state would have crashed with a NameError if a user had selected that page.
- Compounding this: the previous summary to the user explicitly said Signal Analysis was "left alone, not wired in" — which was inaccurate given the code already partially referenced it. Corrected in this pass: fixed the duplicate import, removed the unused `make_chart_fn` parameter from `signal_analysis.render()` (confirmed dead via grep, never referenced in the function body) and updated the call site to match.
- Lesson for future sessions: verify claims about "what was/wasn't changed" against the actual diff before reporting status to the user, not just from memory of intent.

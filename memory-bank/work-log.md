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

## 2026-08-31 — Multi-standard compliance and professional report pass
- Added `core/compliance/` with a standards registry, shared evaluator, PASS/FAIL/REVIEW model, measurement-basis explanations, and generic Plotly chart builder.
- Added SNI 7571:2023, DIN 4150-3:2016 Short-term/Long-term, and BS 7385-2:1993 Short-term/Long-term options to Data Overview and Print Report.
- Kept measurement location out of the UI and displayed the applied basis/explanation instead.
- Preserved the existing `core.sni_chart` interface through a compatibility wrapper.
- Updated the active PDF report with generic compliance tables/charts, source Notes 1-3 in the header, Inter fonts, shared waveform scales, PVS, and standard/duration explanations.
- Fixed CSV report frequency fallback so chart points and Record Values use an evaluated frequency even when channel metadata is absent.
- Kept report chart export bounded by a timeout to prevent indefinite Kaleido hangs.
- Replaced deprecated `use_container_width=True` calls in the touched Overview paths with `width="stretch"`.
- Added `tests/test_compliance.py` covering boundary values, interpolation, chart construction, and status precedence.
- Validation:
  - `git diff --check` passed.
  - `python -m py_compile app.py pages/overview.py pages/report.py core/sni_chart.py core/compliance/*.py` passed.
  - `pytest -q` passed: **78 tests**.
  - Live Streamlit browser test passed for upload, SNI/DIN/BS selection, DIN/BS duration switching, explanations, Print Report options, and end-to-end PDF generation.
  - Browser console showed no errors in the tested workflow.
  - SNI, DIN Short-term/Long-term, and BS Short-term/Long-term PDFs were generated, raster-rendered, and visually inspected successfully.

## 2026-08-31 — Windows packaging step 1: isolated launcher skeleton
- Created branch `windows-packaging` from clean, pushed `main` commit `c468136`; no duplicate repository was created.
- Audited current resource paths. `app.py` and `pages/report.py` resolve font assets relative to their module locations, which is compatible with a future PyInstaller data bundle.
- Confirmed `build/` and `dist/` are already ignored.
- Added `launcher_windows.py`:
  - runs Streamlit through its in-process bootstrap API;
  - requests an available local port and binds only to `127.0.0.1`;
  - waits for the Streamlit health endpoint before opening the default browser;
  - disables file watching/run-on-save for the frozen runtime;
  - resolves normal and PyInstaller `_MEIPASS` resource roots;
  - surfaces startup errors through a Windows message box.
- Added `tests/test_windows_launcher.py` for development resource resolution, port selection, local Streamlit settings, and startup-error handling.
- Found and fixed during live validation: Streamlit's programmatic `bootstrap.run()` did not apply port/address options before creating the server. The launcher now explicitly calls `bootstrap.load_config_options()` first; the corrected smoke run bound to `127.0.0.1` on a dynamic port.
- Validation:
  - `python -m py_compile launcher_windows.py tests/test_windows_launcher.py`: passed.
  - `pytest -q tests/test_windows_launcher.py`: **4 passed**.
  - `pytest -q`: **82 passed**.
  - `git diff --check`: passed.
  - Live launcher smoke: `/_stcore/health` and `/` both returned HTTP 200.

## 2026-08-31 — Windows packaging step 2: reproducible onedir build definition
- Added `requirements-windows.txt` with pinned CPython 3.12-compatible versions for Streamlit, Pandas, NumPy, Plotly 5/Kaleido 0.2.1, SciPy, ReportLab, PyInstaller, and pytest.
- Added `packaging/vibraport_windows.spec`:
  - uses a windowed PyInstaller `onedir` executable with `_internal` contents;
  - includes `app.py`, `.streamlit/config.toml`, font assets, application modules, and Streamlit/Plotly/Kaleido data, binaries, metadata, and dynamic modules;
  - disables UPX to reduce antivirus/SmartScreen false-positive risk.
- Added `packaging/build_windows.ps1`:
  - refuses non-Windows hosts;
  - creates/reuses `.venv-windows` with 64-bit CPython 3.12;
  - installs the pinned manifest and runs the full suite before building;
  - verifies the executable and critical bundled resources after collection.
- Added `.venv-windows/` to `.gitignore` and added `tests/test_windows_packaging.py`.
- Installed PyInstaller 6.22.2 in the existing Linux development venv solely to execute a structural build.
- First frozen launch found `server.port does not work when global.developmentMode is true`; fixed the launcher to explicitly set `global.developmentMode=False` and added an assertion.
- Rebuilt successfully. The resulting Linux structural bundle was about 761 MB and contained `app.py`, Streamlit configuration, Inter fonts, and Kaleido's executable/runtime.
- Browser-driven frozen smoke test rendered the welcome screen and all six navigation choices with no console errors. This used the browser-control skill because loading the Streamlit page is required to execute the dynamically loaded app script.
- Validation:
  - focused launcher + packaging tests: **7 passed**;
  - full `pytest -q`: **85 passed**;
  - `git diff --check`: passed;
  - PyInstaller 6.22.2 structural `onedir` build: passed;
  - frozen local UI load: passed with no browser errors;
  - Windows x64/CPython 3.12 wheel resolution for all direct and transitive pinned dependencies: passed.

## 2026-09-02 — Windows packaging step 3: tray, single instance, and logo
- User confirmed the prior native Windows portable bundle built successfully and all application functions, including Print Report, worked before this lifecycle/branding update.
- Used the image-generation skill with `/home/bolay/ADI/Logo.bmp` as a style reference. Converted a read-only copy to PNG for inspection because the visual tool could not decode the BMP directly; the original company logo was not changed.
- Generated an original Vibraport V/vibration concept, then flattened the selected mark mechanically to a two-color navy (`#1F2F78`) and white transparent PNG.
- Added `assets/icons/vibraport-logo.png` and a Windows ICO containing 16, 24, 32, 48, 64, 128, and 256 px sizes. Verified the full-size and 16 px renders visually and validated the dominant opaque palette in tests.
- Integrated the mark as the PyInstaller executable icon, `pystray` image, and Streamlit favicon.
- Added a native tray menu:
  - **Open Vibraport** rechecks server health and opens the current URL;
  - **Exit Vibraport** calls the captured Streamlit `Server.stop()` and stops the tray loop.
- Added a `Local\\Vibraport.SingleInstance` Windows mutex. The primary publishes only its safe localhost URL under `%LOCALAPPDATA%/Vibraport`; later launches reopen the healthy primary and exit.
- Added controller tests for shutdown before/after server attachment, tray callbacks, instance URL state/validation, second-launch behavior, and Streamlit server capture.
- Added `pystray==0.19.5`, verified its Windows-compatible wheel resolution, and included the Windows tray backend in the PyInstaller spec.
- Validation:
  - focused launcher/packaging suite: **15 passed**;
  - full `pytest -q`: **93 passed**;
  - `git diff --check`: passed;
  - updated Linux structural PyInstaller `onedir` build: passed;
  - frozen Streamlit welcome UI and generated favicon: loaded successfully with no browser warnings/errors.
- At the end of this implementation pass, native Windows tray/mutex testing still remained; the following entry records its completion.

## 2026-09-02 — Updated native Windows bundle validation
- Committed and pushed the tray, single-instance, logo, packaging, tests, and memory-bank work to `windows-packaging` at `483a290` (`Add Windows tray lifecycle and Vibraport branding`).
- The user pulled the branch and rebuilt the portable Windows bundle.
- An initial `Failed to load Python DLL` dialog was traced to launching the intermediate `build\\vibraport_windows` executable. The correct distributable is `dist\\Vibraport\\Vibraport.exe`, accompanied by the complete `_internal` directory.
- Confirmed on Windows:
  - closing the browser leaves the Vibraport background process alive, as designed;
  - launching the executable again reopens/reuses the existing instance instead of starting another server on another port;
  - **Exit Vibraport** from the tray stops the process successfully after the graceful shutdown completes.
- Next release gate: run the updated complete portable directory on a clean Windows 10/11 x64 machine or VM with no Python installed and networking disabled, then recheck real `.sis`, `.csv`, PDF, and icon workflows before implementing an installer.

## 2026-09-02 — Clean Windows/offline portable acceptance
- The user reported that the complete updated portable bundle passed the clean Windows/offline acceptance checklist and all tested functions worked correctly.
- The portable `dist\\Vibraport` artifact is therefore considered self-contained for end users; Python is needed only on the Windows build machine, not on machines running the packaged bundle.
- ZIP distribution is now a viable release option. An Inno Setup installer is optional for execution but recommended when Start-menu/Desktop shortcuts, Add/Remove Programs registration, upgrades, and straightforward uninstall behavior are desired.
- If installer work proceeds, the `.iss` source can be authored in the repository on any OS, but the actual installer must be compiled and acceptance-tested on Windows against the native Windows PyInstaller bundle.

## 2026-09-07 — DIN compliance chart linear axes
- Changed the shared compliance chart builder so DIN 4150-3:2016 Short-term and Long-term use a linear 1-100 Hz frequency axis and a linear 0-60 mm/s PPV axis, matching the source figure's geometry.
- Repositioned DIN frequency-band and category-line labels in linear axis coordinates. This removes the apparent curve previously caused by plotting linearly interpolated DIN limits on a logarithmic PPV axis.
- Preserved SNI and BS logarithmic frequency axes and did not change compliance limits, interpolation, or PASS/FAIL/REVIEW evaluation.
- Added regression coverage for each standard's axis type, DIN's 1-100 Hz range, and DIN annotation positions.
- Corrected an initial delivery mistake: the first implementation was made only in an isolated `main` checkout, so the user's usual `/home/bolay/vibraport` launch still loaded the old chart. The same scoped change was then applied and verified in the usual checkout.
- Validation from `/home/bolay/vibraport`:
  - `python -m py_compile core/compliance/chart.py tests/test_compliance.py`: passed.
  - `pytest -q tests/test_compliance.py`: **37 passed**.
  - `pytest -q`: **94 passed**.
  - `git diff --check`: passed before the memory-bank update.
  - Live Streamlit test with a synthetic waveform CSV confirmed linear DIN band widths, straight guideline segments, and correct label alignment; browser console showed no warnings or errors.

## 2026-09-07 — Bargraph data model, overview, and timeline performance
- Inspected the supplied 42991D7140916M.sis as measurement data. Confirmed
  it is a Tellus bargraph record with 2,681 one-second intervals, three
  velocity channels in mm/s, interval amplitude plus dominant frequency, no
  RMS flag, and no raw acceleration waveform.
- Added `core/monitoring.py` with:
  - serializable normalized channel metadata;
  - interval inference from the actual time axis;
  - legacy metadata fallback;
  - finite-value full-resolution statistics;
  - peak-preserving min/max display downsampling.
- Extended `core.waveform.parse_sis_file()` to expose
  `Monitoring interval seconds` and `Bargraph channels`
  without changing the existing dataframe columns, waveform path, or CSV
  behavior.
- Reworked `pages/monitoring.py`:
  - data overview and quality/capability table;
  - explicit Interval peak/RMS statistic labelling;
  - cached Scattergl timelines instead of one SVG bar per interval;
  - full/15-minute/60-minute/custom view ranges;
  - capped visible alert markers and wheel-to-zoom disabled for normal page
    scrolling;
  - full-resolution maximum, frequency-at-maximum, mean, median, P95, P99,
    invalid values, and alert counts;
  - server-side frequency histogram aggregation;
  - user-facing distinction between operational thresholds and compliance.
- Added `tests/test_monitoring.py` with nine tests covering
  interval/statistic semantics, frequency availability, compatibility
  filtering, statistics, and extrema-preserving point caps.
- Validation:
  - Python compilation passed for `app.py`, `core/*.py`,
    `core/compliance/*.py`, `pages/*.py`, and the new tests.
  - `pytest -q tests/test_monitoring.py`: **9 passed**.
  - `pytest -q`: **88 passed**.
  - `git diff --check`: passed before and after implementation.
  - The supplied Tellus file parsed as three
    Velocity · Interval peak · mm/s channels with one-second intervals.
  - Live Streamlit browser validation passed with the supplied file.
  - A temporary synthetic two-hour, seven-channel, one-second SIS file
    rendered 7,200 intervals/channel as 12,593 peak-preserving line points
    across all channels rather than 50,400 SVG bars.
  - Switching that recording to the 15-minute view completed in about
    0.84 seconds. Scrolling and charts were visually inspected; browser logs
    contained no warnings or errors.

## 2026-09-07 — Monitoring spacing, events, and grouped navigation
- Increased monitoring subplot height and normalized vertical spacing so each
  channel has a clear visual gap from its neighbors. Kept wheel-to-zoom
  disabled so scrolling over the chart continues to move the page.
- Extended `core/monitoring.py` with full-resolution operational
  event detection:
  - yellow-threshold start;
  - red classification when an event reaches the red threshold;
  - percentage-based release hysteresis;
  - configurable quiet-gap bridging;
  - minimum-duration filtering;
  - peak, peak time, frequency-at-peak, duration, and interval counts.
- Added `pages/monitoring_events.py` with event grouping controls,
  summary metrics, a detailed event table, CSV export, and a selectable
  event-detail chart with threshold lines and highlighted event duration.
- Reworked `app.py` navigation into the requested top-level
  Waveform, Bargraph Monitoring, and Print Report workspaces. Bargraph
  Monitoring now exposes Data Overview and Events & Thresholds as separate
  destinations.
- Expanded `tests/test_monitoring.py` from 9 to 17 tests, covering
  event grouping, gap tolerance, hysteresis behavior, minimum duration,
  red/yellow classification, invalid settings, and multi-channel ordering.
- Validation:
  - Python compilation passed for all application/core/page modules.
  - `pytest -q tests/test_monitoring.py`: **17 passed**.
  - `pytest -q`: **96 passed**.
  - `git diff --check`: passed.
  - Live Streamlit testing with the supplied Tellus file verified the grouped
    menu, both monitoring views, increased graph separation, 18 default
    events, gap-tolerance regrouping, event selection/detail updates, and CSV
    export availability.
  - Visual inspection passed and browser logs contained no warnings or errors.

## 2026-09-08 — Frequency-aware bargraph PPV Compliance
- Added PPV channel eligibility and full-resolution interval assessment to
  `core/monitoring.py`. Only Velocity · Interval peak · mm/s channels are
  eligible; RMS and other quantities/units are preserved and excluded.
- Reused `core/compliance/evaluator.py` for every interval. Tightened the
  shared evaluator so missing, non-finite, and zero dominant frequency return
  an explicit `REVIEW` note stating that no PPV limit was guessed.
- Added `pages/monitoring_compliance.py` with channel eligibility disclosure;
  shared SNI/DIN/BS controls; full-resolution summaries; one critical chart
  point per channel; capped result display; complete CSV export; and an
  engineering-screening disclaimer.
- Added PPV Compliance to the Bargraph Monitoring submenu and explicit route in
  `app.py`.
- Expanded compliance and monitoring tests for eligibility, shared limit use,
  interval-level statuses/utilization, ineligible RMS/non-velocity channels,
  and missing/zero/non-finite frequency.
- Validation:
  - Python compilation passed for the touched application/core/page modules.
  - Targeted compliance + monitoring suite: **64 passed**.
  - Full `pytest -q`: **106 passed**.
  - `git diff --check`: passed before the memory-bank update.
  - The supplied Tellus file produced 8,043 interval-channel assessments. SNI
    and DIN default categories passed; BS Short-term produced 2,859 expected
    `REVIEW` results below 4 Hz and no guessed limits.
  - Live browser testing verified SNI, DIN Short-/Long-term, BS review handling,
    page layout, chart/table rendering, and CSV availability. Browser and
    Streamlit logs contained no warnings or errors.

## 2026-09-08 — Responsive Monitoring Trends
- Added reusable full-resolution time-bucket aggregation to
  `core/monitoring.py`. Each channel bucket contains start/end/midpoint,
  interval and valid counts, maximum, mean, median, P95, P99, and dominant
  frequency at the actual maximum.
- Added a fast native-interval path so one-second records remain one-to-one
  without repeatedly running percentile calculations on single-value buckets.
- Added `pages/monitoring_trends.py` with channel selection, native/preset/custom
  aggregation windows, Maximum/P95/P99/Mean/Median chart selection, separated
  stacked WebGL plots, full-recording summaries, capped aggregated tables, and
  complete aggregated CSV export.
- Added Trends to the Bargraph Monitoring submenu and explicit `app.py` route.
- Added seven aggregation tests covering bucket boundaries, original-value
  statistics, peak-frequency association, invalid values, native gaps, invalid
  bucket sizes, and time/amplitude length mismatches.
- Validation:
  - Python compilation passed for all application/core/page modules.
  - `pytest -q tests/test_monitoring.py`: **31 passed**.
  - Full `pytest -q`: **113 passed**.
  - `git diff --check`: passed before the memory-bank update.
  - The supplied Tellus file aggregated from 8,043 values to 135 one-minute
    channel buckets in about 0.025 seconds.
  - A synthetic two-hour/seven-channel record aggregated 50,400 values into
    840 one-minute buckets in about 0.14 seconds; native preparation completed
    in about 0.51 seconds before display downsampling.
  - Live browser testing verified the one-minute Maximum, five-minute P95,
    channel removal, custom 600-second window, empty-selection guard, chart
    spacing, tables, and export control. Browser and Streamlit logs were clean.

## 2026-09-08 — Monitoring trend channel comparison controls
- Kept separated channel panels as the default and added a
  `Synchronize Y-axis between channels` option for compatible selections.
- Added a `Combined overlay` layout for channels with the same normalized
  quantity and unit. Each channel remains selectable in the existing control
  and can also be hidden or shown through the Plotly legend.
- Prevented synchronized/combined layouts for mixed quantities or units.
- Added focused tests for compatibility gating, linked stacked axes, combined
  trace labels, legend availability, and the shared unit label.
- Validation:
  - `pytest -q tests/test_monitoring.py`: **34 passed**.
  - Full `pytest -q`: **116 passed**.
  - `git diff --check`: passed before the memory-bank update.
  - Live browser testing with the supplied Tellus file verified all three
    synchronized panels use identical 0-2 mm/s tick ranges, the combined view
    renders three channel traces, and clicking a legend entry hides its trace.
    Browser logs contained no warnings or errors.

## 2026-09-08 — Configurable bargraph monitoring PDF report
- Added `pages/monitoring_report.py` and routed active bargraph files from the
  existing Print Report menu to it. The existing waveform report remains the
  active path for waveform recordings.
- Added independent section selection for Monitoring Overview, Aggregated
  Trend, Operational Events, and PPV Compliance; the cover is always included.
- Added trend aggregation/statistic/layout options, explicit event threshold
  and grouping inputs, and the shared SNI/DIN/BS compliance selectors.
- Built print-oriented overview/statistics tables, synchronized stacked or
  compatible combined trend charts, capped chronological event registers, and
  full-resolution compliance summaries with the most critical point per
  channel. User alarms remain labelled operational and RMS/VDV is not inferred.
- Added `tests/test_monitoring_report.py` covering selective section inclusion,
  all-section PDF smoke generation, and empty-section validation.
- Validation:
  - Python compilation passed for application, core, page, and test modules.
  - `pytest -q tests/test_monitoring_report.py`: **3 passed**.
  - Full `pytest -q`: **119 passed**.
  - `git diff --check`: passed before the memory-bank update.
  - Live UI testing with the supplied Tellus file verified the Print Report
    route, defaults, Events opt-in, Combined overlay selection, successful PDF
    generation, and download availability. Browser logs were clean.
  - Generated a five-page all-sections DIN Short-term sample. Poppler rendering
    and visual inspection verified every page after fixing table-page frame
    layering and event-peak formatting; no clipping or overlap remained.

## 2026-09-08 — Main and Windows packaging synchronization
- Committed and pushed the complete bargraph monitoring/report implementation
  to `main` at `e023c0e` (`Add bargraph monitoring analysis and reports`).
- Preserved the usual `/home/bolay/vibraport` checkout's local DIN chart and
  memory edits in `ca1243d`, then merged `origin/main` into
  `windows-packaging` without dropping its launcher, tray, branding, pinned
  dependencies, PyInstaller spec, PowerShell build script, or packaging tests.
- Combined the main and Windows memory-bank histories during conflict
  resolution rather than selecting one branch's documentation wholesale.
- Added `output/` and `tmp/` ignore rules. The generated monitoring PDF and its
  rendered QA pages remain local and were not committed because they contain
  customer/project metadata.
- Validation:
  - `pytest -q` on `main`: **119 passed**.
  - `pytest -q` on synchronized `windows-packaging`: **134 passed**.
  - Python compilation and `git diff --check`: passed on both application and
    packaging code paths.

## 2026-09-09 — Windows-compatible monitoring-report tests
- Confirmed from the native Windows traceback that the build gate failed before
  PyInstaller because `tests/test_monitoring_report.py` invoked the unavailable
  external `pdftotext` executable.
- Replaced that subprocess with `pypdf.PdfReader`, added the general dependency,
  and pinned `pypdf==6.18.0` in `requirements-windows.txt`.
- Validation:
  - Synchronized Windows-branch full suite: **134 passed**.
  - Python compilation and `git diff --check`: passed.

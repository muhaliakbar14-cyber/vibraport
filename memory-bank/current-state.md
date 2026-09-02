# Current State

Last updated: 2026-09-02.

## Product Direction
- Vibraport remains a Streamlit-first vibration-analysis application; no framework rewrite is currently planned.
- The active product supports local/offline browser use now and can later be deployed online. A SaaS/authentication layer is deferred until the engineering workflow is stable.
- Primary priorities are reliable `.sis`/`.csv` handling, correct engineering calculations, professional reports, and clear compliance results.

## Live Application
- Entrypoint: `app.py`.
- Six explicitly routed pages: Data Overview, Signal Analysis, Signature Hole Analysis, Attenuation & Safe Zone, Bargraph Monitoring, and Print Report.
- Streamlit's automatic multipage navigation is disabled; every `pages/*.py` module must be imported and routed explicitly in `app.py`.
- Supported inputs: Vibracord `.sis` and waveform `.csv` files, including dual-geophone/Block 2 data and bargraph `M.sis` records.
- Active virtual environment in this checkout: `venv/`.

## Compliance Assessment
- Data Overview and Print Report share the generic `core/compliance/` engine.
- Supported standards:
  - SNI 7571:2023 — Short-term.
  - DIN 4150-3:2016 — Short-term and Long-term.
  - BS 7385-2:1993 — Short-term and Long-term.
- User-facing duration terms are **Short-term** and **Long-term**.
- There is intentionally no measurement-location selector. Each result states the applied measurement basis and explains when the user must compare against another standard column for the actual sensor location.
- DIN Short-term evaluates foundation/all-directions limits; DIN Long-term uses topmost-floor horizontal values and explains the separate floor-slab vertical values.
- BS Short-term evaluates building-base transient limits. Below 4 Hz, Line 2 returns `REVIEW` because the standard requires a displacement check.
- BS Long-term is a conservative 50% screening implementation. Exceeding it returns `REVIEW`, not automatic failure, because the reduction is condition-dependent.
- Compliance statuses are `PASS`, `FAIL`, and `REVIEW`; charts and reports use the same evaluator.

## Reporting and Presentation
- `pages/report.py` generates the active professional PDF report.
- Plotly image export is bounded by a timeout so Kaleido cannot leave report generation spinning indefinitely.
- PDF reports include source Notes 1-3 in the top-right header, shared waveform scales, professional Inter fonts, Record Values/PVS, and the selected compliance chart plus measurement-basis explanation.
- CSV report generation calculates a fallback dominant frequency when device metadata does not provide one.
- SNI, DIN, and BS report variants were rendered and visually inspected on 2026-08-31.

## Verification Status
- `python -m py_compile` passes for the modified application, page, and compliance modules.
- `pytest -q` passes: **78 tests**.
- `git diff --check` passes.
- Browser-driven testing completed on 2026-08-31 using a synthetic waveform CSV: upload, Data Overview, all standard/duration selectors, measurement-basis explanations, Print Report selectors, and end-to-end PDF generation all worked.
- No browser console errors appeared in the tested workflow.
- Representative SNI, DIN Short-term/Long-term, and BS Short-term/Long-term PDFs were raster-rendered and checked for overlap, clipping, chart readability, and table alignment.
- On branch `windows-packaging`, launcher and packaging checks pass and the full suite passes: **93 tests**.
- A live launcher smoke test bound Streamlit to a dynamically selected `127.0.0.1` port; both `/_stcore/health` and `/` returned HTTP 200.
- A Linux structural PyInstaller `onedir` build completed successfully and its frozen UI rendered all six pages in the navigation with no browser console errors. This is validation of the spec only, not a Windows deliverable.

## Windows Packaging Track
- Windows packaging work is isolated on branch `windows-packaging`; `main` remains the clean pushed application baseline at commit `c468136`.
- `launcher_windows.py` is the first packaging component. It runs Streamlit in-process, avoids a terminal subprocess dependency, opens the browser only after the health endpoint is ready, and shows a native Windows error dialog on startup failure.
- The pinned Windows manifest, PyInstaller spec, and PowerShell build script are implemented. All pinned direct and transitive dependencies resolve to CPython 3.12/Windows x64 wheels, including Kaleido's Windows runtime.
- The launcher now has a native Windows tray with **Open Vibraport** and **Exit Vibraport**. Exit calls Streamlit's graceful server stop; closing only the browser leaves the app available in the tray.
- A named Windows mutex enforces a single process. Later launches read the validated localhost URL published by the primary process, reopen it in the browser, and exit.
- A two-color Vibraport V/wave logo derived from the visual character of the user's Abdiyasa reference is integrated as the Windows executable icon, tray icon, and browser favicon.
- The user successfully built the prior native Windows portable bundle and checked all functions, including Print Report. The new tray/single-instance/logo revision must now be rebuilt and validated on Windows; no installer exists yet.
- The intended first artifact is a PyInstaller `onedir` portable build, followed by an Inno Setup installer after clean-Windows validation.

## Known Operational Notes
- Start locally from the repository root with `venv/bin/streamlit run app.py`.
- The completed compliance/report work is committed and pushed on `main` at `c468136`.
- Windows packaging source and tests are maintained on the separate `windows-packaging` branch.
- `core/sni_chart.py` remains as a compatibility wrapper around the generic compliance chart implementation.

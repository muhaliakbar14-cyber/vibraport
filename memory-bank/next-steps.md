# Next Steps

Last updated: 2026-09-28.

## Immediate
1. On a clean Windows 11/Python 3.12 build host, run
   `packaging\build_windows.ps1`. Confirm tests/build verification pass and the
   resulting `dist\METIS Analytics` tree contains no `chrome.exe`,
   `msedge.exe`, or `chromium.exe`.
2. With Chrome installed, launch `METIS Analytics.exe`, run PDF renderer
   diagnostics/self-test, and confirm it identifies Chrome. Generate two
   consecutive multi-file/all-section waveform reports and one all-section
   monitoring report in the same application session.
3. Make Chrome unavailable while Edge remains installed, restart the frozen
   app, and confirm diagnostics select Edge and all three report paths still
   complete. The Windows default browser must not affect selection.
4. Validate timeout/crash recovery by ending or blocking the renderer browser
   during export. Confirm one bounded retry, no orphaned Chrome/Edge or worker
   processes, and a later successful export without restarting Streamlit.
5. Validate diagnostics with neither Chrome nor Edge installed, an invalid
   `BROWSER_PATH`, a Firefox `BROWSER_PATH`, and a supported browser blocked by
   policy. Confirm ordinary parsing/analysis remains usable and each report
   error gives the correct actionable category.
6. Ask a vibration engineer to review the DIN/BS category wording,
   measurement-basis explanations, and the conservative BS Long-term screening
   policy before treating the output as certification-grade.
7. Validate the normalized monitoring and configurable report paths against
   representative Gaia, FX, and DX bargraph files without committing customer
   data.

## Product Hardening
1. Add fixture-locked tests sourced from worked examples for every implemented compliance curve and boundary, including DIN alternate sensor-location columns if those are later automated.
2. Expand PDF smoke coverage to page-count and long event-register edge cases,
   while retaining visual inspection for layout changes.
3. Review remaining Streamlit deprecation warnings outside the files touched in the compliance work.
4. Revisit the previously reported displacement appearance only if it is reproducible with a specific file or screenshot; numerical drift was not reproduced in the available samples.

## Deployment Decision — Deferred
- Local/offline Streamlit remains the current path.
- If online accounts and save/resume become the next priority, re-evaluate the earlier Streamlit + Supabase plan against current hosting limits before implementation.
- The portable application still includes Python and its libraries, but PDF
  charts now deliberately rely on an installed Chrome or Edge browser. No
  browser is bundled or downloaded. Installer work remains optional and
  deferred while native Windows renderer validation is completed.

# Current State

Last updated: 2026-09-08.

## Product Direction
- Vibraport remains a Streamlit-first vibration-analysis application; no framework rewrite is currently planned.
- The active product supports local/offline browser use now and can later be deployed online. A SaaS/authentication layer is deferred until the engineering workflow is stable.
- Primary priorities are reliable `.sis`/`.csv` handling, correct engineering calculations, professional reports, and clear compliance results.

## Live Application
- Entrypoint: `app.py`.
- Three top-level workspaces are explicitly routed: Waveform, Bargraph
  Monitoring, and Print Report. Waveform contains Data Overview, Signal
  Analysis, Signature Hole Analysis, and Attenuation & Safe Zone. Bargraph
  Monitoring contains Data Overview, Trends, Events & Thresholds, and PPV
  Compliance.
- Streamlit's automatic multipage navigation is disabled; every `pages/*.py` module must be imported and routed explicitly in `app.py`.
- Supported inputs: Vibracord `.sis` and waveform `.csv` files, including dual-geophone/Block 2 data and bargraph `M.sis` records.
- Active virtual environment in this checkout: `venv/`.

## Bargraph Monitoring
- SIS bargraph parsing now adds normalized channel metadata: quantity,
  statistic, unit, axis, transducer, interval count, dominant-frequency
  availability, virtual-channel state, and over-range state.
- Unflagged bargraph amplitudes are explicitly treated as
  instrument-reported **Interval peak** values; Tellus RMS flags are preserved
  as RMS. Vibraport does not infer RMS or VDV from peak-velocity bars.
- The monitoring Data Overview shows duration, interval, channel capabilities,
  data-quality warnings, full-resolution maximum/mean/median/P95/P99 values,
  and frequency at the maximum.
- The long timeline uses cached WebGL lines with peak-preserving min/max
  downsampling, range selection, and capped alert markers. Operational
  threshold counts and all statistics remain full-resolution.
- Frequency distributions are server-aggregated before plotting rather than
  sending every interval to the browser.
- Operational yellow/red thresholds are explicitly labelled as user-defined
  screening alarms, not regulatory compliance limits.
- Monitoring channel plots use taller subplot domains and larger vertical gaps
  so adjacent channel titles, limits, and traces remain visually distinct.
- Events & Thresholds groups full-resolution exceedances using configurable
  minimum duration, release hysteresis, and quiet-gap tolerance. It provides
  yellow/red event classification, duration/peak/frequency summaries, CSV
  export, and a selectable event-detail chart.
- PPV Compliance evaluates every finite interval for Velocity · Interval peak ·
  mm/s channels against the selected shared SNI/DIN/BS definition using that
  interval's stored dominant frequency. RMS, acceleration, pressure, and
  incompatible units remain explicitly ineligible.
- Missing, non-finite, or zero dominant frequency returns `REVIEW` with no
  guessed limit, including frequency-independent-looking assessment modes.
- Compliance counts, channel summaries, and CSV export use all intervals. The
  Plotly chart receives only the worst limit-utilization point per channel and
  the on-page result table is capped at 2,000 rows for browser responsiveness.
- Monitoring Trends aggregates every original stored interval into selectable
  native, 1-minute, 5-minute, 15-minute, 1-hour, or custom elapsed-time
  windows. Each bucket exposes maximum, mean, median, P95, P99, counts, and
  dominant frequency at the maximum.
- Trends supports channel selection and defaults to separated WebGL panels.
  When all selected channels have the same quantity and unit, the panels can
  synchronize their Y-axes or switch to a combined overlay with legend
  hide/show controls. Mixed-unit selections cannot share an axis. Long native
  views use peak-preserving display reduction only; aggregation, full-recording
  summaries, and CSV export always use the original arrays. Bucket P95/P99 are
  explicitly described as statistics of the stored interval metric, not raw
  waveform RMS or VDV.

## Compliance Assessment
- Data Overview and Print Report share the generic `core/compliance/` engine.
- Supported standards:
  - SNI 7571:2023 — Short-term.
  - DIN 4150-3:2016 — Short-term and Long-term.
  - BS 7385-2:1993 — Short-term and Long-term.
- User-facing duration terms are **Short-term** and **Long-term**.
- There is intentionally no measurement-location selector. Each result states the applied measurement basis and explains when the user must compare against another standard column for the actual sensor location.
- DIN Short-term evaluates foundation/all-directions limits; DIN Long-term uses topmost-floor horizontal values and explains the separate floor-slab vertical values.
- DIN compliance charts use linear 1-100 Hz frequency and 0-60 mm/s PPV axes, so each guideline segment is visually straight like the source figure. SNI and BS charts retain their logarithmic axes.
- BS Short-term evaluates building-base transient limits. Below 4 Hz, Line 2 returns `REVIEW` because the standard requires a displacement check.
- BS Long-term is a conservative 50% screening implementation. Exceeding it returns `REVIEW`, not automatic failure, because the reduction is condition-dependent.
- Compliance statuses are `PASS`, `FAIL`, and `REVIEW`; charts and reports use the same evaluator.
- Bargraph PPV Compliance also calls this evaluator; there is no monitoring-only
  copy of any standard limit curve.

## Reporting and Presentation
- `pages/report.py` generates the active professional PDF report.
- Print Report dispatches bargraph files to `pages/monitoring_report.py` instead
  of blocking them as non-waveform input. The monitoring report always includes
  a cover and lets users independently include Monitoring Overview, Aggregated
  Trend, Operational Events, and PPV Compliance.
- Trend reports expose aggregation/statistic/layout controls. Event reports use
  explicit operational thresholds and grouping settings. Compliance reports
  use the shared SNI/DIN/BS selectors and evaluate every eligible stored
  interval before summarizing the worst point per channel.
- Plotly image export is bounded by a timeout so Kaleido cannot leave report generation spinning indefinitely.
- PDF reports include source Notes 1-3 in the top-right header, shared waveform scales, professional Inter fonts, Record Values/PVS, and the selected compliance chart plus measurement-basis explanation.
- CSV report generation calculates a fallback dominant frequency when device metadata does not provide one.
- SNI, DIN, and BS report variants were rendered and visually inspected on 2026-08-31.

## Verification Status
- `python -m py_compile` passes for the modified application, page, and compliance modules.
- `pytest -q` passes on `main`: **119 tests**. The synchronized
  `windows-packaging` branch passes **134 tests**, including launcher and
  packaging coverage.
- `git diff --check` passes.
- Monitoring PDF tests use pure-Python `pypdf` text extraction instead of the
  external `pdftotext` executable, so the full test gate runs on clean Windows
  build machines as well as Linux.
- Browser-driven testing completed on 2026-08-31 using a synthetic waveform CSV: upload, Data Overview, all standard/duration selectors, measurement-basis explanations, Print Report selectors, and end-to-end PDF generation all worked.
- No browser console errors appeared in the tested workflow.
- Representative SNI, DIN Short-term/Long-term, and BS Short-term/Long-term PDFs were raster-rendered and checked for overlap, clipping, chart readability, and table alignment.
- On branch `windows-packaging`, launcher and packaging checks pass alongside
  the synchronized application suite.
- A live launcher smoke test bound Streamlit to a dynamically selected `127.0.0.1` port; both `/_stcore/health` and `/` returned HTTP 200.
- A Linux structural PyInstaller `onedir` build completed successfully and its frozen UI rendered the application navigation with no browser console errors. This is validation of the spec only, not a Windows deliverable.
- The updated native Windows bundle at commit `483a290` has now validated the tray lifecycle and single-instance behavior: browser close leaves the server available, a later executable launch reopens the existing instance without allocating another port, and tray Exit completes shutdown after a short delay.
- The user subsequently reported that the complete portable artifact passed the clean Windows/offline acceptance checklist. This confirms that end users do not need a separate Python installation when running the packaged `dist\\Vibraport` artifact.
- A live Streamlit check from `/home/bolay/vibraport` on 2026-09-07 confirmed the DIN Short-term chart's linear band widths and label alignment with no browser warnings or errors.
- Browser-driven testing on 2026-09-07 confirmed the DIN Short-term chart renders with linear frequency/PPV axes, straight guideline segments, correctly positioned labels, and no browser warnings or errors.
- Browser-driven monitoring testing on 2026-09-07 passed with the supplied
  Tellus bargraph file and a synthetic two-hour, seven-channel, one-second
  recording. The full recording rendered with 12,593 peak-preserving line
  points instead of 50,400 SVG bars; the 15-minute range update completed in
  about 0.84 seconds and browser logs contained no warnings or errors.
- A second live monitoring pass verified the increased channel spacing, grouped
  navigation, 18 default events from the supplied Tellus file, quiet-gap
  regrouping, event selection/detail updates, and CSV-export availability.
  Browser logs again contained no warnings or errors.
- Browser-driven PPV Compliance testing on 2026-09-08 used the supplied Tellus
  bargraph file and verified 8,043 full-resolution assessments, SNI, DIN
  Short-/Long-term, BS below-4-Hz `REVIEW` handling, the critical-point chart,
  table cap, and CSV export. Browser and Streamlit logs were clean.
- Browser-driven Trends testing on 2026-09-08 used the supplied Tellus file and
  verified default one-minute maximums, five-minute P95, channel selection,
  custom 600-second windows, the empty-selection guard, stacked chart spacing,
  summary/data tables, and CSV availability. Browser and Streamlit logs were
  clean.
- A follow-up Trends pass verified synchronized stacked Y-axes with identical
  tick ranges and the same-unit combined overlay with all three channel legend
  toggles. Browser logs contained no warnings or errors.
- Browser-driven monitoring-report testing used the supplied Tellus file and
  verified Print Report routing, selectable sections, conditional trend/event/
  compliance controls, combined trend layout, complete PDF generation, and the
  download control. Browser logs were clean.
- A representative five-page all-sections report was raster-rendered and
  visually checked for headers/footers, page numbering, chart clarity, table
  fit, clipping, and section transitions.

## Windows Packaging Track
- Windows packaging work remains isolated on branch `windows-packaging`, which
  now also incorporates the application changes pushed to `main` at `e023c0e`.
- `launcher_windows.py` runs Streamlit in-process, avoids a terminal subprocess
  dependency, opens the browser only after the health endpoint is ready, and
  shows a native Windows error dialog on startup failure.
- The pinned Windows manifest, PyInstaller spec, and PowerShell build script are implemented. All pinned direct and transitive dependencies resolve to CPython 3.12/Windows x64 wheels, including Kaleido's Windows runtime.
- The launcher has a native Windows tray with **Open Vibraport** and **Exit Vibraport**. Exit calls Streamlit's graceful server stop; closing only the browser leaves the app available in the tray.
- A named Windows mutex enforces a single process. Later launches read the validated localhost URL published by the primary process, reopen it in the browser, and exit.
- A two-color Vibraport V/wave logo is integrated as the Windows executable icon, tray icon, and browser favicon.
- The user successfully built the prior native Windows portable bundle and
  confirmed its tray lifecycle, single-instance behavior, and clean-machine/
  offline operation. ZIP distribution is functional; an installer remains an
  optional later milestone.

## Known Operational Notes
- Start locally from the repository root with `venv/bin/streamlit run app.py`.
- `main` is pushed at `e023c0e` with the corrected DIN chart and bargraph
  monitoring/report implementation.
- Windows packaging source and tests are maintained on the separate
  `windows-packaging` branch, synchronized with `main` for Windows rebuilds.
- `core/sni_chart.py` remains as a compatibility wrapper around the generic compliance chart implementation.
- The next engineering task is domain review of DIN/BS wording and screening
  policy, followed by broader bargraph fixture validation across equipment types.

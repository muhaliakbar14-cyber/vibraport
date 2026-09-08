# Latest Handoff (2026-09-08)

## Completed
- Vibraport remains a Streamlit application with `.sis`/`.csv`, dual-block
  waveform, SHA, attenuation, monitoring, and PDF-report workflows.
- Data Overview and Print Report now share `core/compliance/`.
- Compliance choices:
  - SNI 7571:2023 — Short-term.
  - DIN 4150-3:2016 — Short-term and Long-term.
  - BS 7385-2:1993 — Short-term and Long-term.
- No measurement-location selector was added. The UI and PDF state the applied basis and explain alternate standard columns/checks.
- The report includes Notes 1-3 in the header, Inter fonts, shared waveform scales, Record Values/PVS, and the selected standard chart.
- CSV frequency fallback and bounded Kaleido chart export are active.
- DIN Short-term and Long-term compliance charts now use linear 1-100 Hz frequency and 0-60 mm/s PPV axes. DIN frequency-band and category-label annotations use linear coordinates and every guideline segment is visually straight; SNI and BS remain logarithmic.
- Bargraph Monitoring now has a normalized data-capability layer and a stronger
  Data Overview. Channels expose quantity/statistic/unit/transducer/frequency
  and quality flags; unflagged SIS bars are labelled Interval peak rather than
  RMS.
- The monitoring timeline now uses cached, peak-preserving WebGL series,
  selectable full/15-minute/60-minute/custom ranges, capped alert markers, and
  server-aggregated frequency histograms. Full-resolution statistics and alarm
  counts are kept separate from display downsampling.
- RMS and VDV remain deliberately unavailable for peak-velocity bargraph files.
  User thresholds are explicitly operational alarms rather than compliance.
- Channel plots now have taller domains and larger vertical gaps so adjacent
  channel graphs are visually distinct.
- Navigation is grouped into Waveform, Bargraph Monitoring, and Print Report.
  Bargraph Monitoring contains Data Overview, Trends, Events & Thresholds, and
  PPV Compliance.
- The full-resolution event engine supports minimum duration, release
  hysteresis, and quiet-gap tolerance. The new event view provides summary
  metrics, a detailed table, CSV export, and jump-to-event charts.
- PPV Compliance evaluates every finite Velocity · Interval peak · mm/s bar at
  full resolution with the shared SNI/DIN/BS engine and the interval's stored
  dominant frequency. Missing/zero frequency is explicit `REVIEW`; RMS and
  non-velocity channels are not reinterpreted.
- The PPV page includes eligibility disclosure, standard/assessment/category
  controls, overall and per-channel counts, the most critical valid-frequency
  point per channel, capped interval display, and full CSV export.
- Monitoring Trends provides channel selection and native/preset/custom time
  buckets. Maximum, mean, median, P95, P99, valid counts, and frequency at the
  bucket maximum are calculated from original intervals. Stacked WebGL charts
  may synchronize Y-axes, and matching-unit channels may use a combined overlay
  with legend toggles. Mixed-unit channels remain separated. Plots may reduce
  displayed points, while summaries and CSV data remain full-resolution.
- Print Report now accepts active bargraph recordings. A dedicated configurable
  builder always adds a cover and optionally includes Monitoring Overview,
  Aggregated Trend, Operational Events, and PPV Compliance. The waveform report
  path remains unchanged.
- Monitoring PDFs print their trend/event/compliance settings, use the existing
  full-resolution domain helpers, and preserve shared SNI/DIN/BS evaluation.

## Verification
- `git diff --check`: passed.
- Python compilation: passed.
- `pytest -q`: **119 passed**.
- Live browser test: upload, standards/durations, Overview, Print Report, and PDF generation passed with no console errors.
- Five representative PDF variants were rendered and visually inspected successfully.
- Live DIN UI test passed with a synthetic waveform CSV: the frequency regions have linear widths, all guideline segments are straight, and no browser warnings/errors appeared.
- Live monitoring UI tests passed with the supplied Tellus M.sis file and a
  synthetic two-hour/seven-channel/one-second file. The 15-minute range
  interaction completed in about 0.84 seconds; visual inspection passed and
  browser logs showed no warnings or errors.
- A follow-up browser pass verified the increased graph spacing, grouped
  navigation, default detection of 18 events from the supplied file,
  quiet-gap regrouping, event selection/detail rendering, and CSV export
  availability. Browser logs contained no warnings or errors.
- Live PPV Compliance testing with the supplied Tellus file verified 8,043
  interval-channel results, SNI, DIN Short-/Long-term, BS below-4-Hz review,
  chart/table rendering, and CSV export. Browser and Streamlit logs were clean.
- Live Trends testing with the supplied Tellus file verified one-minute
  Maximum, five-minute P95, channel selection, custom 600-second aggregation,
  empty-selection handling, chart/table layout, and CSV availability. Browser
  and Streamlit logs were clean.
- A follow-up live Trends pass verified identical Y tick ranges across all
  synchronized stacked panels and a combined three-channel overlay whose
  legend entries hide/show their traces. Browser logs were clean.
- Live monitoring-report testing verified bargraph Print Report routing,
  section selection, conditional options, all-section PDF generation, and the
  download control with the supplied Tellus file. Browser logs were clean.
- The five-page sample report was raster-rendered. Headers, footers, page
  numbers, trend/compliance charts, overview/event tables, and section
  transitions passed visual inspection after correcting footer/header layering
  and event-peak formatting.

## Change Scope
- Monitoring implementation/test files: `core/monitoring.py`,
  `core/waveform.py`, `pages/monitoring.py`, and
  `pages/monitoring_trends.py`, `pages/monitoring_events.py`,
  `pages/monitoring_compliance.py`, `pages/monitoring_report.py`, `app.py`,
  `tests/test_monitoring.py`, and `tests/test_monitoring_report.py`.
- Shared missing-frequency behavior and regression coverage also touch
  `core/compliance/evaluator.py` and `tests/test_compliance.py`.
- Updated `architecture`, `current-state`,
  `decisions`, `handoff-latest`, `next-steps`,
  and `work-log`.

## Immediate Next Task
1. Ask a vibration engineer to review DIN/BS category wording, measurement
   explanations, and the conservative BS Long-term screening policy.
2. Validate normalized monitoring/report behavior against representative Gaia,
   FX, and DX bargraph fixtures without committing customer data.
3. Keep the already validated Windows packaging/installer track separate.

## Guardrails for the Next Session
- Read `memory-bank/current-state.md`, `decisions.md`, `next-steps.md`, and this file first.
- Keep compliance logic shared; do not reintroduce page-specific copies.
- Treat standards output as engineering support, not certification, until domain-reviewed against worked examples.
- Re-check that every live `pages/*.py` module is explicitly wired in `app.py`.
- Never compute monitoring statistics or compliance from display-downsampled
  arrays.
- Never label peak bars as RMS or derive VDV without a compatible stored
  metric/time history.

# Architecture

Last updated: 2026-09-08.

## Runtime and Routing
- `app.py`: Streamlit entrypoint, file manager/session registry,
  parse caching, grouped Waveform / Bargraph Monitoring / Print Report
  navigation, and explicit page routing.
- `.streamlit/config.toml`: hides Streamlit's automatic pages navigation.
- `pages/`: waveform analysis, monitoring overview, monitoring trends,
  monitoring-event review, monitoring PPV compliance, monitoring PDF reporting,
  attenuation/safe-zone analysis, and waveform PDF reporting.

## Domain and Analysis
- `core/monitoring.py`: normalized bargraph channel semantics,
  full-resolution descriptive statistics, interval inference, and
  peak-preserving display downsampling, plus operational event grouping with
  minimum duration, hysteresis, and quiet-gap tolerance. It also filters
  PPV-eligible channels and maps every full-resolution interval into the shared
  compliance evaluator without estimating missing frequency. Time-bucket trend
  aggregation also lives here so UI charts and future reports can reuse the
  same full-resolution maximum/mean/median/P95/P99 definitions.
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
- `pages/monitoring_report.py` builds active-file bargraph PDFs with selectable
  overview, aggregated-trend, operational-event, and PPV-compliance sections.
  It calls the same full-resolution monitoring helpers and shared compliance
  engine as the interactive pages; only chart rendering is reduced for print.
- `assets/fonts/Inter-*.ttf`: embedded professional typeface assets.
- Data Overview and Print Report call the same compliance registry, evaluator, and chart code so limits and statuses remain consistent.

## UX Conventions
- Keep Streamlit first-class.
- Cache expensive parsing by file content.
- Use `st.form` for grouped calculations and `st.fragment` where isolated reruns materially help.
- Use `width="stretch"` instead of deprecated `use_container_width=True` in touched code.
- Measurement location is explanatory context, not a compliance selector.
- Bargraph charts may downsample for display, but statistics, alert counts,
  event detection, and compliance inputs must always use the original
  full-resolution intervals.
- Monitoring trends default to separated channel panels. Matching quantities
  and units may share a synchronized Y-axis or use a combined overlay with
  Plotly legend toggles; mixed-unit channels must remain separated.
- SIS bargraph channel metadata must distinguish instrument-reported interval
  peaks from RMS. Never derive or label RMS/VDV when the stored data does not
  support that metric.

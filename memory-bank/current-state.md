# Current State

Last updated: 2026-09-07.

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
- DIN compliance charts use linear 1-100 Hz frequency and 0-60 mm/s PPV axes, so each guideline segment is visually straight like the source figure. SNI and BS charts retain their logarithmic axes.
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
- `pytest -q` passes: **79 tests**.
- `git diff --check` passes.
- Browser-driven testing completed on 2026-08-31 using a synthetic waveform CSV: upload, Data Overview, all standard/duration selectors, measurement-basis explanations, Print Report selectors, and end-to-end PDF generation all worked.
- No browser console errors appeared in the tested workflow.
- Representative SNI, DIN Short-term/Long-term, and BS Short-term/Long-term PDFs were raster-rendered and checked for overlap, clipping, chart readability, and table alignment.
- Browser-driven testing on 2026-09-07 confirmed the DIN Short-term chart renders with linear frequency/PPV axes, straight guideline segments, correctly positioned labels, and no browser warnings or errors.

## Known Operational Notes
- Start locally from the repository root with `venv/bin/streamlit run app.py`.
- `main` contains the corrected linear DIN chart axes and regression coverage.
- `core/sni_chart.py` remains as a compatibility wrapper around the generic compliance chart implementation.

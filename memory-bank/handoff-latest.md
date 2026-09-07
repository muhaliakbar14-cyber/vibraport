# Latest Handoff (2026-09-07)

## Completed
- Vibraport remains a six-page Streamlit application with `.sis`/`.csv`, dual-block waveform, SHA, attenuation, monitoring, and PDF-report workflows.
- Data Overview and Print Report now share `core/compliance/`.
- Compliance choices:
  - SNI 7571:2023 — Short-term.
  - DIN 4150-3:2016 — Short-term and Long-term.
  - BS 7385-2:1993 — Short-term and Long-term.
- No measurement-location selector was added. The UI and PDF state the applied basis and explain alternate standard columns/checks.
- The report includes Notes 1-3 in the header, Inter fonts, shared waveform scales, Record Values/PVS, and the selected standard chart.
- CSV frequency fallback and bounded Kaleido chart export are active.
- DIN Short-term and Long-term compliance charts now use linear 1-100 Hz frequency and 0-60 mm/s PPV axes. DIN frequency-band and category-label annotations use linear coordinates and every guideline segment is visually straight; SNI and BS remain logarithmic.

## Verification
- `git diff --check`: passed.
- Python compilation: passed.
- `pytest -q`: **79 passed**.
- Live browser test: upload, standards/durations, Overview, Print Report, and PDF generation passed with no console errors.
- Five representative PDF variants were rendered and visually inspected successfully.
- Live DIN UI test passed with a synthetic waveform CSV: the frequency regions have linear widths, all guideline segments are straight, and no browser warnings/errors appeared.

## Change Scope
- Modified implementation/test files: `core/compliance/chart.py` and `tests/test_compliance.py`.
- Updated `current-state`, `handoff-latest`, `next-steps`, and `work-log` for this task.

## Immediate Next Task
1. Continue with the next user-selected main-branch improvement.
2. Keep the already validated Windows packaging/installer track separate.

## Guardrails for the Next Session
- Read `memory-bank/current-state.md`, `decisions.md`, `next-steps.md`, and this file first.
- Keep compliance logic shared; do not reintroduce page-specific copies.
- Treat standards output as engineering support, not certification, until domain-reviewed against worked examples.
- Re-check that every live `pages/*.py` module is explicitly wired in `app.py`.

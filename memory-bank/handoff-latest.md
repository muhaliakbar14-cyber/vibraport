# Latest Handoff (2026-08-31)

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

## Verification
- `git diff --check`: passed.
- Python compilation: passed.
- `pytest -q`: **78 passed**.
- Live browser test: upload, standards/durations, Overview, Print Report, and PDF generation passed with no console errors.
- Five representative PDF variants were rendered and visually inspected successfully.

## Working Tree
- Changes are intentionally uncommitted so the user can commit and push them.
- Includes modified application/report/overview files, the new `core/compliance/` package, compliance tests, Inter font assets, and this memory-bank update.

## Immediate Next Task
1. Review `git status`/`git diff --stat`.
2. Commit all intended files.
3. Push branch `main` to `origin`.
4. Then run a clean-machine or fresh-environment smoke test with real `.sis` and `.csv` data.

## Guardrails for the Next Session
- Read `memory-bank/current-state.md`, `decisions.md`, `next-steps.md`, and this file first.
- Keep compliance logic shared; do not reintroduce page-specific copies.
- Treat standards output as engineering support, not certification, until domain-reviewed against worked examples.
- Re-check that every live `pages/*.py` module is explicitly wired in `app.py`.

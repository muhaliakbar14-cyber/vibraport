# Next Steps

Last updated: 2026-08-31.

## Immediate
1. Run `packaging/build_windows.ps1` on a Windows 10/11 x64 machine with CPython 3.12 to produce the native portable bundle.
2. Test that bundle on a clean Windows machine or VM across all six pages using a real `.sis`, waveform `.csv`, and multi-file PDF report; visually inspect the generated PDFs.
3. Review the native bundle size and warnings, then optimize safe unused dependencies if needed without removing Streamlit, Plotly, Kaleido, SciPy, ReportLab, or the shared compliance engine.
4. Only after the portable build passes, add an Inno Setup installer with shortcuts, version metadata, and uninstall support.

## Product Hardening
1. Add fixture-locked tests sourced from worked examples for every implemented compliance curve and boundary, including DIN alternate sensor-location columns if those are later automated.
2. Add automated PDF smoke tests that assert page count and required headings/tables, while retaining visual inspection for layout changes.
3. Review remaining Streamlit deprecation warnings outside the files touched in the compliance work.
4. Revisit the previously reported displacement appearance only if it is reproducible with a specific file or screenshot; numerical drift was not reproduced in the available samples.

## Deployment Decision — Deferred
- Local/offline Streamlit remains the current path.
- If online accounts and save/resume become the next priority, re-evaluate the earlier Streamlit + Supabase plan against current hosting limits before implementation.
- Windows packaging is now an active, separate release track using a `onedir` bundle rather than a one-file executable.

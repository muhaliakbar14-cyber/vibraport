# Next Steps

Last updated: 2026-08-31.

## Immediate
1. Commit and push the completed multi-standard compliance/report work and memory-bank update.
2. Test the pushed checkout on a second machine or clean virtual environment using at least one real `.sis`, one waveform `.csv`, and one multi-file report.
3. Ask a vibration engineer to review the DIN/BS category wording, measurement-basis explanations, and the conservative BS Long-term screening policy before treating the output as certification-grade.

## Product Hardening
1. Add fixture-locked tests sourced from worked examples for every implemented compliance curve and boundary, including DIN alternate sensor-location columns if those are later automated.
2. Add automated PDF smoke tests that assert page count and required headings/tables, while retaining visual inspection for layout changes.
3. Review remaining Streamlit deprecation warnings outside the files touched in the compliance work.
4. Revisit the previously reported displacement appearance only if it is reproducible with a specific file or screenshot; numerical drift was not reproduced in the available samples.

## Deployment Decision — Deferred
- Local/offline Streamlit remains the current path.
- If online accounts and save/resume become the next priority, re-evaluate the earlier Streamlit + Supabase plan against current hosting limits before implementation.
- If a one-file Windows executable becomes the next priority, treat packaging as a separate release track and build/test it on Windows.

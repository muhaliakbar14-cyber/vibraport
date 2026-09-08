# Next Steps

Last updated: 2026-09-08.

## Immediate
1. Ask a vibration engineer to review the DIN/BS category wording,
   measurement-basis explanations, and the conservative BS Long-term screening
   policy before treating the output as certification-grade.
2. Validate the normalized monitoring and configurable report paths against
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
- The self-contained Windows portable bundle has been validated on the separate `windows-packaging` branch. Installer work remains optional and deferred while main-branch improvements continue.

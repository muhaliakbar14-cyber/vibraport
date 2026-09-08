# Next Steps

Last updated: 2026-09-07.

## Immediate
1. Confirm the revised linear DIN frequency/PPV axes and straight guideline segments in the usual `/home/bolay/vibraport` launch workflow.
2. Continue with the next user-selected main-application improvement.
3. When explicitly requested, place/commit the scoped DIN chart and regression-test changes on `main` without mixing in unrelated Windows packaging work.
4. Return later to the optional Inno Setup decision; the validated ZIP remains usable now.

## Product Hardening
1. Add fixture-locked tests sourced from worked examples for every implemented compliance curve and boundary, including DIN alternate sensor-location columns if those are later automated.
2. Add automated PDF smoke tests that assert page count and required headings/tables, while retaining visual inspection for layout changes.
3. Review remaining Streamlit deprecation warnings outside the files touched in the compliance work.
4. Revisit the previously reported displacement appearance only if it is reproducible with a specific file or screenshot; numerical drift was not reproduced in the available samples.

## Deployment Decision — Deferred
- Local/offline Streamlit remains the current path.
- If online accounts and save/resume become the next priority, re-evaluate the earlier Streamlit + Supabase plan against current hosting limits before implementation.
- Windows packaging is now an active, separate release track using a `onedir` bundle rather than a one-file executable.

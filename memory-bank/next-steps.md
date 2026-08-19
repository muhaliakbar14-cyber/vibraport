# Next Steps

## Completed 2026-08-18/19
- Rerun/blink fixes: `st.cache_data` on parsing, `st.fragment` on `make_chart()`, `st.form` on SHA Step 2.
- Fixed: CSV routing crash, `.sis` time-unit 1000x mismatch, `.sis` metadata key aliases, displacement detrending (+ Block 2 consistency), stale `.streamlit/config.toml` key (was letting the auto-nav show).
- Restored `ppv_analysis.py`, `monitoring.py`, `signal_analysis.py` into `app.py`'s navigation. Nav bar and welcome screen updated to describe all 7 pages.

## Open items
1. **Displacement "looks weird" (user-reported, unresolved)** — could not reproduce with test-set files; math checks out (no drift, physically plausible magnitudes). Needs a screenshot or more specific description to investigate further. May already be fixed by the detrend change if it was drift-related on a file outside the test set.
2. **Math Analysis vs Signal Analysis overlap** — both pages exist and cover similar ground. Signal Analysis is the more complete version (Block 2 support, device-reported frequency values). Consider retiring the inline Math Analysis page in favor of it, or clearly differentiating their purposes. Not done yet — needs a decision, not just a fix.
3. **Remaining rerun cost** — Data Overview's frequency-method selectbox and Math Analysis's FFT block still trigger full-script reruns on change. Smaller now that parsing is cached, but not fragmented yet.
4. **Browser-driven UI testing** — everything verified so far is either unit-level (pytest), function-level (calling render logic directly with real data), or a headless boot/HTTP-200 check. No actual click-through of the running UI has been done. Worth doing manually before the next major change.

## SaaS build plan (after the above; see decisions.md 2026-08-18 entry for full reasoning)
1. Create Supabase project; set up `.env`/`secrets.toml` for URL + anon key (keep out of git — confirm `.streamlit/secrets.toml` is in `.gitignore`).
2. Write a thin `auth.py` wrapper around `supabase-py` for sign-up/login/logout/session — avoid depending on third-party Streamlit auth UI components.
3. Design a minimal Postgres schema: users (handled by Supabase Auth), projects table (user_id, project_name, created_at, config/state as JSON), and Supabase Storage bucket for uploaded `.sis`/`.csv` files (Streamlit Cloud's filesystem is ephemeral — nothing local persists).
4. Add save/load project UI: on save, persist current analysis state + reference to uploaded file(s); on load, rehydrate session state.
5. Deploy to Streamlit Community Cloud; verify: (a) repo can be public or check current private-repo free-tier support, (b) app survives a sleep/wake cycle without losing user data (this tests the ephemeral-filesystem assumption for real).
6. Cross-check core formulas (PPV attenuation, scaled distance, SNI/USBM references) against a published worked example as a standing test, independent of the SaaS work.

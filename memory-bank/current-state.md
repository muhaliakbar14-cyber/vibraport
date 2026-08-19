# Current State

## Product Direction
- The app is Streamlit-first and stays that way — no framework rewrite planned.
- Target product: a simple SaaS for mining engineers/practitioners to analyze vibration data (PPV, VOD, waveform, attenuation, SHA), with sign-in and save/resume of user projects.
- Priorities per user: simple, reliable, and formula/factual correctness — not feature breadth.
- Planned SaaS layer: Supabase (Auth + Postgres + Storage) added on top of the existing Streamlit app; hosting via Streamlit Community Cloud. See decisions.md 2026-08-18 entry for full reasoning.
- `.sis` and `.csv` parsing is required and already part of the current app direction — verified working against real sample files this session (see Verification section below).
- The UX pain point to solve next is full-script reruns and blinking.

## What Works Now
- `app.py` runs the original Streamlit workflow, now with 7 pages: Data Overview, Math Analysis, Signal Analysis, Signature Hole Analysis, Attenuation & Safe Zone, Bargraph Monitoring, Print Report.
- `.sis` and `.csv` uploads are accepted; CSV file-selection crash and the `.sis` time-unit bug (both found 2026-08-18/19) are fixed.
- `Print Report`, `Attenuation & Safe Zone` (regression + safe zone calculator + SNI 7571 tables), and `Bargraph Monitoring` (for "M"-suffixed `.sis` files) are all available again in the Streamlit navigation.
- `Signal Analysis` is a newer, more complete alternative to `Math Analysis` (adds Block 2/dual-geophone support, uses device-reported frequency values) — both currently coexist, not yet consolidated.
- `core.waveform.parse_sis_file` is the parser path for `.sis` files; `.sis` metadata now exposes CSV-compatible key aliases (`Date & Time`, `Date of calibration`).
- Streamlit's auto-generated pages-nav (from files in `pages/`) is correctly hidden via `.streamlit/config.toml` (`[client] showSidebarNavigation = false`) — the old key was silently broken.
- Displacement integration uses `scipy.signal.detrend(type='linear')` (both Block 1 and Block 2, via shared logic) instead of mean-subtraction only.

## Current UX Problem
- Largely addressed 2026-08-18: `@st.cache_data` on file parsing, `@st.fragment` on the channel-visibility chart, `st.form` on SHA's 10 blast-parameter inputs.
- Not yet fragmented: Data Overview's frequency-method selectbox and Math Analysis's FFT block still trigger full-script reruns on change (smaller cost now that parsing is cached, but not eliminated).

## Known Operational Notes
- Run the app with `streamlit run app.py` from the repo root.
- Keep the repo centered on the Streamlit app unless a later decision explicitly reintroduces another stack.
- Only one venv now (`.venv` — the unused duplicate `venv/` was deleted 2026-08-18).
- `pages/*.py` files are NOT auto-wired by Streamlit's multipage feature (nav is hidden via config) — each must be explicitly imported and routed in `app.py`'s if/elif chain to actually be reachable. Check `app.py`'s imports and page list before assuming a `pages/` file is live.

## Independently Verified (Claude, 2026-08-18/19)
Actually executed against real repo code and sample files, not just read from docs:
- `python -m py_compile` on app.py, core/, pages/, regression/, optimizer/ — all compile clean.
- `pytest tests/` — 30/30 pass (still true after all fixes below).
- `core.waveform.parse_sis_file(bytes)` tested against 5 real `.sis` samples (Tellus, Gaia, DX hardware, plus a dual-block/virtual-channel file) — all parsed correctly with correct equipment detection and sample rates.
- `core.waveform.parse_file(bytes)` tested against 4 real `.csv` samples (waveform CSVs + the separate PPV-vs-scaled-distance summary CSV format) — all parsed correctly.
- CSV routing fix and `.sis` time-unit fix both verified by directly re-running the previously-broken code path with real file bytes, not just re-reading the code.
- Displacement drift tested numerically across 5 real files (3 `.sis`, 2 `.csv`) both before and after the detrend change — no measurable linear drift found in the test set either way (max ~0.002mm over the full record).
- `monitoring.py`'s `_get_bargraph_channels()` tested against a real bargraph file (`4018014D70916M.sis`) — correctly detected all 4 channels (3 velocity + pressure) with correct units.
- `ppv_analysis.py`'s registry-building and regression pipeline (`standard_scaled_distance` + `fit_power_law`) tested end-to-end against 3 real `.sis` files fed through the same logic `app.py` uses.
- `signal_analysis.py`'s channel-detection and `core.metrics` functions (`peak_displacement`, `acceleration_at_peak`, `acceleration_in_g`) tested against real data.
- `streamlit run app.py` boots and serves HTTP 200 in a headless smoke test after every round of changes; startup log confirmed clean (no config warnings) after the config.toml fix.
- Not yet verified: actual browser UI interactions (upload widget → navigation → report generation click-through) — needs a real browser session, can't be driven headlessly.

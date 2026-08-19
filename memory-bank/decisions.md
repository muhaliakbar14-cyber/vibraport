# Decisions Log

## 2026-05-18 — Web over desktop for primary path
- Decision: prioritize FastAPI + React migration over desktop-first (PySide/Electron).
- Why: keep SaaS model, preserve Supabase integration, improve UX versus Streamlit.

## 2026-05-18 — Core features before polish
- Decision: prioritize tool migration and core functional parity before visual refinement.
- Why: user value is in analysis/report outputs first.

## 2026-05-18 — Keep analysis logic consistent with original
- Decision: reuse existing Python domain/core functions where possible.
- Why: reduce regression risk and preserve trusted behavior.

## 2026-05-18 — Windows-familiar workbench UX direction
- Decision: adopt left-pane files + right-pane features/tabs interaction model.
- Why: familiarity for target users and better multi-task visibility.

## 2026-05-18 — Offline desktop-first execution path
- Decision: implement an offline-first desktop runtime (PySide6 + local SQLite/files) as v1 execution path.
- Why: reduce operational risk from SaaS env/auth/storage coupling and improve reliability for field use.

## 2026-05-18 — Lightweight autosave + manual regression saves
- Decision: keep lightweight autosave of UI/session/analysis state and add explicit manual save/load for attenuation regression sessions.
- Why: preserve reliability without heavy write amplification; ensure users can return to regression entry sets intentionally.

## 2026-08-18 — Return to Streamlit baseline
- Decision: remove the offline desktop and Supabase/web branches and restore the original Streamlit app as the active path.
- Why: the user wanted to restart from the earlier single-file Streamlit workflow.

## 2026-08-18 — Streamlit-first going forward
- Decision: keep Streamlit as the primary product path for now, accept `.sis`, and improve responsiveness with `st.form` and `st.fragment`.
- Why: the app should remain simple to run locally now, with server deployment left for later.

## 2026-08-18 — Simple SaaS direction: Streamlit + Supabase, no framework rewrite
- Decision: build the SaaS layer (sign-in, save/resume projects) by adding Supabase Auth + Postgres + Storage on top of the existing Streamlit app, deployed on Streamlit Community Cloud. Explicitly NOT repeating the FastAPI+React+Supabase rewrite from 2026-05-18.
- Why: the earlier SaaS attempt's complexity came from gluing three services together (Streamlit→React rewrite, FastAPI middle layer, Supabase). This time Streamlit stays as the whole app; only auth+DB+storage are added. Free hosting on Streamlit Community Cloud has an ephemeral filesystem, so an external DB/storage is required regardless of auth method chosen — this isn't optional if "save project, resume later" is a requirement.
- Auth implementation approach: thin custom wrapper around `supabase-py` auth calls (not a third-party Streamlit auth UI component), to avoid depending on small/niche packages for the login flow.
- Risk carried over from before: Supabase's operational rough edges (env vars, RLS policies, schema grants) that caused pain in the 2026-05-18 attempt are still a real risk here, just on a smaller surface area (auth+DB only, not a full backend rebuild).

## 2026-08-18/19 — Rerun/blink fixes + real bugs found and fixed during the pass
- Decision: before starting the SaaS layer, fix `app.py`'s rerun/blink problem as planned, and fix any real bugs found along the way rather than deferring them, since several were directly in the code being touched.
- Changes made: `@st.cache_data` on the file-parsing wrapper (previously re-parsed the whole file from raw bytes on every widget interaction, not just on file change — likely the single biggest cause of sluggishness); `@st.fragment` on `make_chart()` (channel visibility checkboxes no longer rerun the whole page); `st.form` around SHA Step 2's 10 blast-parameter inputs (no rerun until "Run Simulation" is pressed; tradeoff — the combo-count preview no longer updates live while typing, only on submit).
- Bugs found and fixed in the same pass (not requested, but blocking/adjacent to the code being touched):
  1. CSV file selection crashed the whole app (`AttributeError: 'bytes' object has no attribute 'read'`) — `_parse_uploaded_file` routed non-.sis files to a broken local `parse_file(uploaded_file)` expecting a file-like object, given raw bytes instead. Fixed by routing to the tested `core.waveform.parse_file(bytes)` and deleting the broken local duplicate.
  2. 1000x time-unit mismatch — `.sis` parsing returns `time_axis` in seconds, `.csv` in milliseconds (intentional convention; `pages/report.py` already compensates per call site). `app.py`'s own inline pages did not compensate, so any `.sis` file (the primary format) had a broken time axis on Overview/Math/SHA — e.g. SHA's manual truncation input only accepted 0–4 "ms" instead of 0–4000ms. Fixed by normalizing to milliseconds once, in the parse wrapper, so downstream pages can assume ms unconditionally.
  3. `.sis` metadata key mismatch — "Calibrated" and "Date & Time" showed N/A for `.sis` files even though the underlying binary parser extracts correct values. Root cause: `.sis` parsing produces `'Calibration date'` and separate `'Date'`/`'Time'` keys, while `app.py` looks for `'Date of calibration'` and a combined `'Date & Time'` key (the literal CSV header strings). Fixed by adding aliases in `core.waveform.parse_sis_file`'s metadata dict so both formats expose the same keys.
  4. Displacement integration used mean-subtraction only (removes a constant offset, not a linear trend/ramp from residual DC bias). Tested against 5 real files — no measurable drift was actually found on current test data, so this wasn't reproducing a live bug, but it's a real robustness gap for future files. Replaced with `scipy.signal.detrend(type='linear')` before and after integration. Also found and fixed: Block 2 (dual-geophone) had its own duplicated, less-robust inline copy of this logic that never got the same treatment — refactored `_compute_displacement`/`_compute_acceleration` to accept a `rename_map` parameter so Block 1 and Block 2 now share identical logic.
  5. `.streamlit/config.toml` had a stale/invalid key (`[ui] hideSidebarNav`) from an old Streamlit version — silently did nothing, so Streamlit's auto-generated multipage nav (populated from every file in `pages/`, regardless of whether `app.py` imports it) was showing in the sidebar. Fixed to the current correct key (`[client] showSidebarNavigation = false`); confirmed the startup warning is gone and the auto-nav no longer renders.
- User-reported displacement "looks weird" issue: could NOT reproduce with the files in `testfile-sis/`/`csv_test/` — math checks out (no drift, physically correct sub-mm magnitudes for the PPV/frequency ranges in these files). Still open — needs a screenshot or more specific description from the user to investigate further, or may already be resolved by the detrend fix above if it was drift-related on a file not in the test set.

## 2026-08-19 — Restore ppv_analysis.py, monitoring.py, and signal_analysis.py pages
- Decision: wire the three orphaned `pages/*.py` modules (present in the repo but never imported by `app.py` since the "Restore Streamlit baseline" revert) back into the app's navigation.
- Why: `ppv_analysis.py` (attenuation regression, safe zone calculator, SNI 7571 tables) and `monitoring.py` (bargraph "M" file viewer) were confirmed by the user as features that existed before and were lost in the revert. `signal_analysis.py` was found during this work (not explicitly requested at first, added in the same session on request) — it's a cleaner rewrite of "Math Analysis" that additionally supports Block 2 (dual-geophone) channels and uses device-reported frequency values instead of always recomputing via FFT.
- Integration details that required care (both verified against real files, not just imported):
  - `ppv_analysis.render(uploaded_files_dict, ppv_registry)` doesn't need the currently "active" file's parsed waveform — it works off the registry of ALL uploaded files' peak values. Routed before the per-file parse step so it doesn't depend on the active file's format.
  - `monitoring.render(df, time_axis, metadata, sampling_rate)` and `signal_analysis.render(df, time_axis, sampling_rate, make_chart_fn, metadata=None)` both expect `time_axis` in raw **seconds** (they do their own `* 1000` or `/ 60` internally) — but the parse wrapper now normalizes everything to **milliseconds** for the other pages (see the 1000x fix above). Both call sites convert back (`time_axis / 1000`) before handing off.
  - Bargraph ("M") files don't have velocity/accel/displacement waveform columns, only amplitude/frequency summaries per interval. Added a guard: selecting a bargraph file while on a waveform-only page now shows a redirect message instead of crashing with a KeyError.
- Known overlap not yet resolved: "📐 Math Analysis" (inline in `app.py`) and "📡 Signal Analysis" (`pages/signal_analysis.py`) now both exist and cover similar ground (frequency + acceleration + displacement). Kept both live for now rather than removing one unprompted; flagged in the welcome screen. Consolidating is an open next step — Signal Analysis is the more complete version (Block 2 support, device-reported frequency) and is the likely long-term keeper.

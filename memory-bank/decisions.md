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

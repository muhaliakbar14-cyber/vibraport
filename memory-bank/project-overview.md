# Project Overview

## Name
Vibraport

## Goal
Deliver a vibration-analysis app that stays Streamlit-first now, supports `.sis` and `.csv` parsing, and can later be deployed on a server if needed.

## Current Direction
Primary direction is the Streamlit app:
- entrypoint: `app.py`
- parser support: `.sis` and `.csv`
- UX work: reduce reruns and blinking with `st.form` and `st.fragment`

## Why this direction
- Keep the app easy to run locally right now.
- Preserve the original Vibraport analysis workflow.
- Improve responsiveness without abandoning Streamlit.
- Leave server deployment as a later step once the Streamlit experience is stable.

## Non-goals (current phase)
- Reintroducing the offline desktop branch.
- Rebuilding the Supabase/web stack as the primary path.
- Final visual polish before the rerun-smoothing refactor.

# Current State

## Product Direction
- The app is Streamlit-first and should stay that way for now.
- Future deployment can move to a server later, but the current working model is local Streamlit development.
- `.sis` parsing is required and already part of the current app direction.
- The UX pain point to solve next is full-script reruns and blinking.

## What Works Now
- `app.py` runs the original Streamlit workflow.
- `.sis` and `.csv` uploads are accepted again.
- `Print Report` is available again in the Streamlit navigation.
- `core.waveform.parse_sis_file` is the parser path for `.sis` files.

## Current UX Problem
- Inputs still trigger broad reruns in some places.
- The next refactor target is to reduce page-wide reruns with `st.form` and `st.fragment` where appropriate.
- Goal: smoother interaction without losing the simple Streamlit architecture.

## Known Operational Notes
- Run the app with `streamlit run app.py` from the repo root.
- Keep the repo centered on the Streamlit app unless a later decision explicitly reintroduces another stack.

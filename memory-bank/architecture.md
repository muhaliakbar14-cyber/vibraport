# Architecture

## Current Stack
- `app.py`: Streamlit entrypoint for file upload, parsing, page routing, and report access.
- `core/`: waveform parsing and numerical analysis helpers.
- `pages/`: Streamlit page modules for overview, signal analysis, SHA, PPV analysis, monitoring, and report.
- `regression/` and `optimizer/`: shared analysis logic for signal and delay calculations.
- `config.py`: shared constants and app configuration.
- `requirements.txt`: runtime dependencies for the Streamlit app.

## UX Direction
- Prefer `st.form` for grouped input collections.
- Prefer `st.fragment` for isolated expensive/flickery areas when it helps reduce full-page reruns.
- Keep Streamlit the first-class runtime; defer server deployment decisions to a later phase.

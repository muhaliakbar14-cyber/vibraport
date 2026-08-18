# Next Steps

## Active path
1. Keep the app Streamlit-first.
2. Smooth the UI with `st.form` for batched inputs.
3. Isolate expensive or flickery sections with `st.fragment` where suitable.
4. Preserve `.sis` parsing and the report page.
5. Keep server deployment as a later phase.

## Immediate next task
- Refactor the current Streamlit pages to reduce whole-page reruns, starting with the most input-heavy screens.

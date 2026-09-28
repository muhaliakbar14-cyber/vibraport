# METIS Analytics — AI/IDE Working Instructions

These instructions apply to the entire repository and are intentionally
tool-neutral. The canonical project context is the `memory-bank/` directory.

## Before Changing Anything

1. Read these files completely:
   - `memory-bank/README.md`
   - `memory-bank/handoff-latest.md`
   - `memory-bank/current-state.md`
   - `memory-bank/decisions.md`
   - `memory-bank/next-steps.md`
   - `memory-bank/architecture.md`
   - `memory-bank/work-log.md`
2. Inspect the current branch, `git status`, and recent commit history.
3. Confirm the current state and highest-priority task.
4. State the exact files expected to change before editing.

If an instruction file disagrees with the memory bank, use the newest dated
entry in `handoff-latest.md`, `current-state.md`, or `decisions.md` and resolve
the inconsistency as part of the task.

## Project Guardrails

- Keep the application Streamlit-first. Do not restart a FastAPI/React,
  desktop-shell, Supabase, or installer track unless explicitly requested.
- Preserve `.sis` and `.csv` parsing behavior, the shared compliance engine,
  monitoring semantics, METIS branding, and supplied production image assets.
- Every live `pages/*.py` module must be explicitly imported and routed by
  `app.py`; do not create an orphan page or duplicate inline implementation.
- Never compute engineering statistics, events, trends, or compliance from
  display-downsampled data.
- Do not label interval peaks as RMS/VDV or invent missing dominant frequency.
- PDF rendering uses pinned Plotly 6/Kaleido 1 with an installed browser. Do
  not reintroduce Kaleido private internals, bundle/download a browser, or
  remove the isolated renderer timeout/retry/process-tree cleanup.
- Browser discovery is: valid explicit `BROWSER_PATH`, then Chrome, then Edge.
  Firefox and the Windows default-browser setting are irrelevant to Kaleido.
- Do not delete user files, rewrite unrelated work, or use destructive Git
  commands. Commit or push only when explicitly requested.

## Verification

Use the repository virtual environment on Linux:

```bash
venv/bin/python -m pytest -q
venv/bin/python -m py_compile <modified Python files>
git diff --check
```

The standard interactive launch remains:

```bash
cd /home/bolay/vibraport
venv/bin/streamlit run app.py
```

Windows bundles must be built natively with `packaging\build_windows.ps1` and
validated using the checklist in `memory-bank/next-steps.md`.

## Finishing and Handoff

- Update `current-state.md`, `handoff-latest.md`, and `work-log.md` for every
  completed implementation task.
- Update `decisions.md` when behavior or architectural policy changes.
- Update `architecture.md` when ownership/data flow changes.
- Keep `next-steps.md` short, ordered, and accurate.
- Record exact verification commands/results and any platform limitation.
- Leave the repository understandable without relying on chat history.

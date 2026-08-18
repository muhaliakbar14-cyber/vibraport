# Conversation Carry Guide (Full)

Use this guide every time you continue this project in a new chat.

## 1) Before Ending A Conversation
1. Ensure these are updated:
   - `memory-bank/current-state.md`
   - `memory-bank/work-log.md`
   - `memory-bank/next-steps.md`
   - `memory-bank/decisions.md` (only if a decision changed)
2. Update `memory-bank/handoff-latest.md` with:
   - what was finished
   - what remains
   - exact next task
3. Include validation commands and results in `work-log.md`.

## 2) Start A New Conversation (Copy-Paste Prompt)
Use this prompt exactly:

```text
Before answering, read /home/bolay/vibraport/memory-bank first (README, handoff-latest, current-state, decisions, next-steps, work-log) and use it as source of truth.
Then:
1) summarize current status,
2) state the immediate next task,
3) list exact files you will edit,
4) execute only that agreed task and verify with tests/build.
```

## 3) Keep The Agent Focused (Copy-Paste Guardrail)

```text
Do not branch scope. Do not stop at partial fixes. Do end-to-end implementation + verification for the agreed task only.
If you hit a blocker, resolve it fully if possible; if not, report exact blocker, evidence, and smallest next action.
```

## 4) Standard “Done” Checklist
A task is only done when all are true:
1. Code implemented.
2. Relevant tests/build executed.
3. Runtime/manual validation done when applicable.
4. Memory-bank updated (`current-state`, `work-log`, `next-steps`, `handoff-latest`).
5. Final message includes:
   - what changed
   - file paths
   - validation commands/results
   - exact next step

## 5) If Context Seems Lost In A New Chat
Use this recovery prompt:

```text
Stop and re-read /home/bolay/vibraport/memory-bank/README.md, handoff-latest.md, current-state.md, decisions.md, next-steps.md, and work-log.md.
Return only:
1) confirmed project state,
2) next single task,
3) exact files to touch.
No implementation yet.
```

## 6) Scope Safety Rules
- Only execute the agreed step.
- No destructive git/file operations unless explicitly asked.
- Prefer permanent fixes over temporary workarounds.
- Verify all critical paths touched by the change.

## 7) Streamlit-First Quick Resume
When resuming the project, use this exact direction:

```text
Continue Streamlit-first only. Keep `.sis` support, use `st.form` and `st.fragment` to reduce reruns, and ignore offline desktop/Supabase unless explicitly requested.
```

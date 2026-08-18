# Memory Bank

Purpose: persistent project memory for session-to-session continuity.

## How to Use
At the start of each session, ask the assistant to:
1. Read this folder first.
2. Summarize `current-state.md` and `next-steps.md`.
3. Use `decisions.md` + `work-log.md` as historical context before proposing changes.

Recommended prompt:

```text
Before answering, read /memory-bank first (README, current-state, decisions, next-steps, work-log) and use it as project context.
```

## Files
- `project-overview.md`: stable context (what this project is, scope, goals).
- `architecture.md`: technical structure and component map.
- `current-state.md`: latest known implementation status.
- `decisions.md`: decision log (why choices were made).
- `work-log.md`: chronological actions/results.
- `next-steps.md`: active roadmap and immediate tasks.
- `session-template.md`: template to append a new session entry quickly.
- `handoff-latest.md`: latest implementation handoff snapshot for fast resume.
- `conversation-carry-guide.md`: full guide for continuing this project in a new chat.

## Update Rules
- Update `current-state.md` whenever behavior/status changes.
- Add every important decision to `decisions.md` with date and rationale.
- Append task execution details to `work-log.md`.
- Keep `next-steps.md` short and ordered by priority.
- Do not delete old entries; mark superseded items clearly.

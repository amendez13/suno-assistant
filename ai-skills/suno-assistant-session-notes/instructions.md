# suno-assistant Session Notes

Use this skill when creating or updating suno-assistant daily session notes.

Read first:
- `AGENTS.md`
- today's session note in `notes/YYYY/MM/YYYY-MM-DD.md`, if it already exists

Default behavior:
- update the daily session note
- create today's note if it does not exist yet

Optional behavior:
- update a secondary summary log only when the user explicitly asks for it
- if `notes/.notes-config.yaml` is absent, the secondary-log workflow is disabled

## Session Note Rules

- Path: `notes/YYYY/MM/YYYY-MM-DD.md`
- Content categories:
  - implementation work
  - validation and tests
  - pull request and merge results
  - operational follow-up and deployment notes
- Keep notes factual and useful for future engineering context.
- Direct pushes to `main` are acceptable for notes-only updates after merged work when the user explicitly requests them or when closing out an already authorized delivery cycle.

## Secondary Summary-Log Rules

- Do not update the secondary log unless the user explicitly requests it.
- Keep the entry plain-language, outcome-focused, and non-technical.
- Use today's session note as the source unless the user gives you other source notes.
- If there was no relevant work, say so plainly rather than inventing activity.
- The target path and repo-safety settings come from `notes/.notes-config.yaml`.

## Secondary-Log Workflow

1. Read today's session note.
2. Extract the real outcomes, not every small action.
3. Write a concise daily entry in the configured target file.
4. Keep the entry outcome-focused and non-technical.
5. Commit or push only when the user explicitly asks.
6. Before committing or pushing to a separate repo, verify that the target repo is on the configured branch and `git status --short` is clean. If not, stop and report the repo state.

## Preferred Execution Pattern

- For session notes, summarize what actually landed.
- For summary logs, act only on explicit request and compress the day into plain-language outcomes.
- Do not invent work that is not present in the source notes.
- If the user constrains which notes to use, obey that strictly.

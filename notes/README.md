# Session Notes

Session notes are short factual records of what was implemented, validated, merged, deployed, or deferred on a given day. They are part of the repository's engineering history and should be committed.

## When To Update Them

Update session notes at meaningful milestones during the day:

- when starting issue-driven work
- when implementation scope changes in a meaningful way
- when validation or testing completes
- when a pull request is opened or merged
- when CI passes or a release or deployment finishes
- when you create `[followup]` issues or record operational follow-up

## Path Conventions

- Daily note: `notes/YYYY/MM/YYYY-MM-DD.md`
- Topical companion note: `notes/YYYY/MM/YYYY-MM-DD-<slug>.md`
- Cross-cutting design note: `notes/<topic>-design.md`

Use one daily note per day. Add a topical companion only when a single topic needs extra depth that would make the daily note noisy.

## Style

- Keep notes factual and useful for future engineering context.
- Write what landed, what was validated, and what remains.
- Prefer short summaries over narrative diary entries.
- Treat the pull request as the changelog; session notes are the engineering context around it.

## Direct-Push Exception

Docs-only updates to session notes after work has already merged may be pushed directly to `main` when the user explicitly requests the notes update or when the agent is closing out a delivery cycle the user already authorized.

## Daily Note Template

```md
# YYYY-MM-DD Session Notes

## Scope
- Intended work for the day.

## Issue #X

### Implementation
- What changed.

### Validation
- Tests, manual checks, CI status, or review checkpoints.

### PR / Merge Log
- Branch, PR, merge, or release notes that matter later.

## Operational Follow-Up
- Deployments, hotfixes, backfills, or manual data operations.

## Follow-Up Issues Created
- [followup] #123 Short description of deferred work.
```

## What Does Not Go In Session Notes

- Long code snippets when a PR, commit, or file reference is clearer
- Secrets, tokens, passwords, or raw internal-only hostnames
- Personal reflections or private journaling
- File-by-file technical changelogs that duplicate the pull request description

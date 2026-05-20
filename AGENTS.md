# AGENTS.md

This file provides guidance to coding agents working in this repository.
`CLAUDE.md` is a compatibility symlink to this file so Claude Code, Codex, and
other harnesses consume the same source of truth.

## Required Workflow Rules

1. Never skip pre-commit hooks.
   - Do not use `--no-verify`.
   - If hooks fail, fix the issues and rerun them.

2. Functional changes should go through a pull request by default.
   - Use a feature or fix branch unless the user explicitly requests a direct push to `main`.

3. Direct pushes to `main` are acceptable only when the user explicitly requests them.
   - Treat an explicit direct-push request as an override to the default PR workflow.
   - Still run the required validation before pushing.

4. Never change the code coverage target unless the user explicitly asks for that in the current task.

## Standard Delivery Workflow

For issue-driven work, follow this default sequence:

1. Checkout `main` and pull `origin/main`.
2. Create a branch for the issue and implement the change.
3. Update architecture, diagrams, and setup documentation when behavior, configuration, schema, API surface, or data flow changes.
4. Run the relevant tests.
5. Run `pre-commit run --all-files`.
6. Commit with a conventional commit message and push the branch.
7. Open a pull request with a closing keyword such as `Closes #X`.
8. Wait for CI to pass and fix failures before merge.
9. Request external review with `@codex review` or the repository's equivalent trigger.
10. While waiting, review your own diff and leave a PR comment covering the main change, primary risks, and any remaining validation gaps.
11. Read review feedback carefully, reply inline, fix the full class of problems, and create `[followup]` issues for deferred work when needed.
12. Leave a decision comment describing what was fixed now, deferred, declined, or not done.
13. Merge the pull request.
14. Return to the primary checkout, pull `origin/main`, update today's session note, then start the next issue.

## Session Notes

- Session notes are factual engineering notes stored under `notes/YYYY/MM/YYYY-MM-DD.md`.
- Agents must update session notes at the end of issue-driven delivery work, after merge, after deployment or manual follow-up, and when creating `[followup]` issues.
- Additive updates to session notes may be pushed directly to `main` when:
  - the change is only a session-note update, and
  - the user explicitly requested the notes update or the agent just completed a delivery cycle the user authorized.
- Use `ai-skills/suno-assistant-session-notes/` as the canonical session-notes workflow.

## Project Overview

A private Suno assistant built on gentle-site-visitor. The application is
intended to help generate original songs through the operator's own Suno
account from explicit creative instructions.

**Core workflow**:

1. Load Suno Assistant configuration.
2. Build a bounded Suno-specific visit plan.
3. Execute the plan through `gentle-site-visitor` browser, pacing, session, and
   observability layers.
4. Persist generation evidence and session artifacts for review.

## Constraints And Best Practices

- This project is documentation-driven. Before starting work, read:
  - `README.md`
  - `docs/INDEX.md`
  - `docs/AGENT_CONTEXT.md` when present
- After finishing a task, update any documentation that changed with it.
- When changing schema, API surface, or data flow, update `docs/AGENT_CONTEXT.md` when that document exists in the project.
- When changing observability behavior, logging shape, health endpoint contracts, or service naming conventions, update `docs/OBSERVABILITY.md`.
- `pyproject.toml`, `.github/workflows/ci.yml`, and `.pre-commit-config.yaml` must stay aligned so local checks and CI behave the same way.
- Any code quality exception must be documented with an inline comment and a reason.
- Branch naming: `feature/description`, `fix/description`, `docs/description`
- Commit messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Architecture

### Technology Stack

- Python 3.10+
- `gentle-site-visitor` as the browser/session/pacing/observability framework
- PyYAML and python-dotenv for local configuration

### Key Components

1. **Suno Assistant app**
   - Site-specific Suno configuration, selectors, adapters, and visit plans.
   - Must not modify or vendor framework code.

2. **gentle-site-visitor dependency**
   - Reusable framework for browser lifecycle, session handling, pacing, visit steps, and observability.
   - Consumed as a Python package dependency, with local editable installs allowed for development.

### Processing Strategy

- Keep runs bounded, paced, and observable.
- Prefer explicit page limits and conservative rate limits.
- Do not add stealth, anti-detection, CAPTCHA-bypass, or terms-evasion behavior.
- Do not add platform-policy bypasses, safety-control bypasses, or automation
  whose purpose is to imitate restricted artists or copyrighted works.
- Treat credentials, cookies, traces, HARs, and storage state as sensitive local artifacts.

## Development Commands

### Initial Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
pre-commit install
cp config/config.example.yaml config/config.yaml
```

### Running Tests

```bash
source venv/bin/activate
pytest
pytest --cov=suno_assistant --cov-report=term-missing
pytest tests/test_main.py
```

### Common Commands

```bash
source venv/bin/activate
black suno_assistant/
isort suno_assistant/
flake8 suno_assistant/
mypy suno_assistant/
bandit -r suno_assistant/ -ll
deactivate
```

### Running The Application

```bash
source venv/bin/activate
python -m suno_assistant.main
```

## Notable Code Quality Exceptions

Document any non-default quality-rule exception in the file where it is used and keep the rationale brief and specific.

Examples:
- `# noqa: C901` because a route or parser is intentionally co-located and splitting it would reduce readability more than it helps.
- `# type: ignore[...]` because a third-party library ships incomplete typing.
- `# nosec` because the flagged pattern uses only trusted input.

## Review Guidelines

- Treat CI, workflow, release, deployment, and setup-documentation regressions as P1 severity.
- When a change updates documentation or developer workflow files, verify the instructions still match the implementation.
- Treat broken bootstrap or operator guidance as a blocking issue when it would cause repository setup or delivery workflow failures.

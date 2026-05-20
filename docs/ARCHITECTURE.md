# Architecture Documentation

This document describes the technical architecture of suno-assistant.

## Overview

Suno Assistant is a private site-specific application for generating original
songs through the operator's own Suno account at gentle, human cadence. It
depends on `gentle-site-visitor` as the framework layer and keeps Suno-specific
selectors, adapters, URL choices, plan factories, prompt schemas, and output
schemas in this repository.

The project is intentionally not a stealth/evasion toolkit or a platform-policy
bypass toolkit. Its operating model is low-impact, user-directed song creation
with explicit pacing, visible observability, and bounded runs.

## Delivery And Deployment Control Plane

The template now includes a deployment control plane alongside the application scaffold:

- `.github/workflows/release.yml` is the operator entry point for manual and release-driven deployments
- `scripts/github/resolve_release_context.py` converts trigger-specific GitHub metadata into stable deployment inputs
- `scripts/redeploy.sh` and `scripts/release_smoke_check.sh` define the handoff between GitHub Actions and the infrastructure playbooks
- `infra/hetzner/`, `infra/home-worker/`, and `infra/site/` provide the inventory, secrets, and orchestration skeletons that projects customize per environment

```mermaid
flowchart LR
    A["workflow_dispatch / release: published"] --> B["resolve_release_context.py"]
    B --> C["tag create or verify"]
    C --> D["GitHub Release status update"]
    D --> E["materialize SSH, inventory, secrets"]
    E --> F["scripts/redeploy.sh"]
    F --> G["Ansible playbooks under infra/"]
    G --> H["scripts/release_smoke_check.sh"]
    H --> I["success/failure status update on Release"]
```

## System Components

### Component Diagram

```
┌──────────────────────┐
│ suno_assistant app   │
│ config + plan entry  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐      ┌──────────────────────┐
│ Suno adapter         │─────▶│ Suno pages        │
│ selectors + extract  │      │ suno.com          │
└──────────┬───────────┘      └──────────────────────┘
           │
           ▼
┌──────────────────────┐
│ gentle-site-visitor  │
│ browser/session/run  │
└──────────────────────┘
```

### Suno Assistant App

**Purpose**: Assemble Suno-specific visit plans and configuration.

**Responsibilities**:
- Load project configuration.
- Validate operator song requests before browser startup.
- Build the Suno auth adapter and verify the operator's saved session before
  running create-page workflows.
- Centralize Suno create-page selectors and fixture-backed page-state extraction.
- Choose bounded Suno create-page workflows.
- Fill and submit one bounded generation request when a validated song request
  is supplied.
- Construct GSV `VisitPlan` instances.
- Emit Suno-specific generation evidence events.

**Key Files**:
- `suno_assistant/auth.py`
- `suno_assistant/selectors.py`
- `suno_assistant/extractors.py`
- `suno_assistant/steps.py`
- `suno_assistant/main.py`
- `suno_assistant/requests.py`
- `suno_assistant/visit.py`
- `tests/fixtures/suno/*.html`

### gentle-site-visitor Framework

**Purpose**: Provide the reusable browser, pacing, session, run, and
observability mechanics.

**Responsibilities**:
- Browser lifecycle and Playwright integration.
- Human-cadence pacing, rate limiting, dwell, and scrolling primitives.
- Visit runner step wrapping.
- Session artifacts and diagnostics.

**Key Files**:
- External dependency: `gentle-site-visitor @ git+https://github.com/amendez13/gentle-site-visitor.git@v2026.05.07.1`

## Data Flow

1. Operator supplies config and run target.
2. Suno Assistant optionally loads a YAML request or quick prompt and validates
   the bounded song request before browser startup.
3. GSV `Session` restores local Suno browser storage and verifies that the
   authenticated create page is reachable.
4. If auth is missing or expired, Suno Assistant returns a blocked auth result
   before building or executing any generation plan.
5. Suno Assistant classifies the loaded create-page state with centralized
   selectors and extraction helpers.
6. Known page blocks such as auth-required, quota unavailable, policy rejection,
   disabled controls, or missing prompt controls are surfaced as explicit states.
7. When a request is present, Suno Assistant fills supported create-page fields
   and submits one create/generate action.
8. Suno Assistant waits within a bounded timeout for result cards or known blocked states.
9. Suno Assistant builds a request-aware GSV `VisitPlan`.
10. GSV executes the plan through browser/session/pacing/observability layers.
11. Suno Assistant receives generation evidence rows and run artifacts for review.

## Design Decisions

### Decision 1: Consume GSV As A Library

**Context**: Suno Assistant is site-specific while `gentle-site-visitor` is a
reusable framework extracted for multiple visitor apps.

**Decision**: Depend on GSV as a Python package dependency instead of vendoring,
submodules, or subtree copies.

**Consequences**:
- Pro: Framework upgrades are explicit and reviewable.
- Pro: Suno-specific PRs do not mix with framework PRs.
- Pro: CI can test the application boundary exactly as deployed.
- Con: Production should pin a tag or commit SHA instead of tracking `main`.

### Decision 2: Keep Runs Bounded

**Context**: Suno pages should be visited gently and observably.

**Decision**: Default config includes a bounded page limit, conservative
rate-limit settings, and session artifacts.

**Consequences**:
- Pro: Headed demos and early smoke runs stay comprehensible.
- Pro: Run artifacts can be inspected before increasing scope.
- Con: Broad coverage requires explicit operator configuration.

### Decision 3: Validate Song Requests Before Browser Startup

**Context**: The app will eventually submit requests that can consume Suno
credits or quota.

**Decision**: The CLI normalizes `--prompt` and `--request` inputs into a typed
`SongRequest` before launching the browser.

**Consequences**:
- Pro: Invalid request files, empty prompts, broad counts, and unsupported
  combinations fail without touching the live Suno session.
- Pro: The visit-plan boundary can evolve toward generation steps without
  coupling request parsing to selectors.
- Con: New request fields need explicit parser and documentation updates.

### Decision 4: Use Manual Headed Session Bootstrap

**Context**: Suno may require third-party auth, MFA, CAPTCHA, or other
verification flows that should not be automated.

**Decision**: Use GSV's `Session` layer with a Suno auth adapter. The CLI
supports `--headed --login` for operator-completed login and verifies saved
storage state before any create-page workflow.

**Consequences**:
- Pro: The app uses the framework session boundary instead of parallel auth code.
- Pro: Headless runs fail with a clear blocked auth result when the saved
  session is missing or expired.
- Pro: Manual verification remains operator-controlled.
- Con: The operator must refresh local storage state when Suno expires the session.

### Decision 5: Keep Selectors And Extractors Fixture-Backed

**Context**: Suno's create page can change independently of this project, while
CI should not depend on live Suno access or consume account quota.

**Decision**: Keep selector fallback groups in `suno_assistant/selectors.py`,
HTML-to-state extraction in `suno_assistant/extractors.py`, and sanitized create
state fixtures under `tests/fixtures/suno/`.

**Consequences**:
- Pro: Selector and state-classification drift has focused regression tests.
- Pro: Generation-plan work can consume named page states instead of scattering
  raw selectors through visit steps.
- Pro: CI remains offline and does not need authenticated Suno access.
- Con: Fixture coverage must be refreshed when real UI states diverge from the
  sanitized snapshots.

### Decision 6: Keep The First Generation Plan Narrow

**Context**: The first prompt-to-song workflow can consume external account
quota and depends on a changing authenticated UI.

**Decision**: When a validated request is supplied, the plan verifies page
readiness, fills supported fields, submits once, and waits within a bounded
timeout for either visible result cards or known blocked states.

**Consequences**:
- Pro: One CLI invocation has an explicit submit boundary and bounded wait.
- Pro: Known platform blocks classify as `blocked` instead of false success.
- Pro: Step tests can use fake pages and offline fixtures before live smoke.
- Con: Batch submission, downloads, and durable evidence schema are deferred.

## Performance Considerations

- Favor slow, bounded, observable runs over throughput.
- Keep any concurrency disabled unless a future design justifies it.
- Pin framework versions before production runs to avoid unreviewed behavior changes.

## Security Considerations

- Do not commit Suno credentials, cookies, storage state, HARs, traces,
  or raw page artifacts.
- Keep `config/config.yaml` and `data/` untracked.
- Keep the pinned public `gentle-site-visitor` dependency explicit and reviewable in CI.
- Respect Suno terms, account constraints, applicable robots guidance, rights of
  third parties, and any artist/style/content restrictions.

## Future Enhancements

- [x] Expand the create-page smoke run into a richer Suno site adapter and selector module.
- [x] Add initial prompt-to-song generation steps beyond the create-page visit.
- [ ] Add durable Suno-specific evidence extraction and artifact review beyond the minimal submit event.
- [ ] Add headed smoke-run instructions using GSV observability.

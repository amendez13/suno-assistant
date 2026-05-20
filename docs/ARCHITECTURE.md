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
- Choose bounded Suno create-page workflows.
- Construct GSV `VisitPlan` instances.
- Emit Suno-specific generation evidence events.

**Key Files**:
- `suno_assistant/main.py`
- `suno_assistant/visit.py`

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
2. Suno Assistant resolves a bounded Suno create workflow from operator instructions.
3. Suno Assistant builds a GSV `VisitPlan`.
4. GSV executes the plan through browser/session/pacing/observability layers.
5. Suno Assistant receives generation evidence rows and run artifacts for review.

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
- Con: Private Git dependency access must be configured for CI.
- Con: Production should pin a tag or commit SHA instead of tracking `main`.

### Decision 2: Keep Runs Bounded

**Context**: Suno pages should be visited gently and observably.

**Decision**: Default config includes a bounded page limit, conservative
rate-limit settings, and session artifacts.

**Consequences**:
- Pro: Headed demos and early smoke runs stay comprehensible.
- Pro: Run artifacts can be inspected before increasing scope.
- Con: Broad coverage requires explicit operator configuration.

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

- [ ] Expand the create-page smoke run into a richer Suno site adapter and selector module.
- [ ] Add prompt-to-song generation steps and Suno-specific evidence extraction beyond the initial create-page visit.
- [ ] Add headed smoke-run instructions using GSV observability.

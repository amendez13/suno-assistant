# Task Management

This document tracks development phases, tasks, and progress for suno-assistant.

## Development Phases

### Phase 1: Foundation (Current)

**Goal**: Establish core infrastructure and dependency boundary.

**Tasks**:
- [x] Project setup
- [x] CI/CD pipeline
- [x] Documentation structure
- [x] `gentle-site-visitor` package dependency
- [x] Initial smoke tests
- [ ] Suno configuration model

**Status**: In Progress

### Phase 2: Core Features

**Goal**: Implement the first bounded Suno visit plan.

**Tasks**:
- [ ] Suno site adapter
- [ ] Selectors and offline HTML fixtures
- [ ] Visit plan and evidence schema
- [ ] Integration tests

**Status**: Planned

### Phase 3: Polish & Release

**Goal**: Prepare for release

**Tasks**:
- [ ] Performance optimization
- [ ] Documentation completion
- [ ] Release preparation
- [ ] User testing

**Status**: Planned

---

## Task Priority Matrix

| Priority | Impact | Effort | Tasks |
|----------|--------|--------|-------|
| P1 | High | Low | Quick wins, critical bugs |
| P2 | High | Medium | Core features |
| P3 | Medium | Low | Nice-to-haves |
| P4 | Low | High | Future considerations |

---

## Current Sprint

### In Progress
- [ ] Suno configuration model

### Up Next
- [ ] Suno site adapter
- [ ] First bounded visit plan

### Blocked
- None.

---

## Backlog

### High Priority
- [x] Pin `gentle-site-visitor` to a tag or commit SHA before production.
- [ ] Add headed smoke-run instructions and artifact review checklist.

### Medium Priority
- [ ] Define Suno evidence schema.
- [ ] Add fixture-backed extraction tests.

### Low Priority
- [ ] Select deployment target.
- [ ] Tune session retention after first real runs.

---

## Completed

### Phase 1
- [x] Initial project setup
- [x] CI pipeline configuration
- [x] Pre-commit hooks
- [x] Documentation structure
- [x] GSV dependency boundary documented

---

## Notes

- Suno Assistant consumes `gentle-site-visitor` as a package dependency rather than vendoring or using a submodule.

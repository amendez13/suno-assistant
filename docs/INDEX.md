# Documentation Index

Welcome to the suno-assistant documentation. This index provides easy access to all documentation in this repository.

## Quick Links

**For Users:**
- [Getting Started](#getting-started) - Start here if you're new
- [Setup Guide](#setup-guides) - Configure your environment
- [Release Workflow](#operations) - Run a release deployment
- [Session Notes](#project-history) - Learn the notes convention

**For Developers:**
- [Architecture](#architecture) - Technical design and implementation details
- [Developer Guide](#developer-resources) - Contributing and development workflow

---

## Getting Started

**[README.md](../README.md)**
- Project overview and features
- Quick start guide
- Installation instructions
- Basic configuration
- Usage examples
- Troubleshooting common issues

---

## Setup Guides

**[SETUP.md](SETUP.md)**
- Prerequisites and system requirements
- Step-by-step installation guide
- Configuration options
- Session-notes workflow setup
- Verification steps
- Troubleshooting

**[MANUAL_SMOKE.md](MANUAL_SMOKE.md)**
- Operator workflow for headed login bootstrap and bounded live smoke runs
- Prompt/request examples, evidence review, artifact retention, and safety boundaries

**[AI_SKILLS.md](AI_SKILLS.md)**
- Canonical AI skills source tree
- Dual deployment to Claude and Codex
- Starter skills and local deploy workflow

**[CI_RUNNER.md](CI_RUNNER.md)**
- Self-hosted runner setup and operations
- Docker CI image contract and runner-target guidance

**[OBSERVABILITY.md](OBSERVABILITY.md)**
- Structured logging and operator observability patterns
- systemd naming, Loki integration, and session-artifact guidance

**[SECURITY_BASELINE.md](SECURITY_BASELINE.md)**
- Baseline secret scanning and repository security guidance
- GitHub secret scanning, push protection, and CodeQL setup references

**[RELEASE_WORKFLOW.md](RELEASE_WORKFLOW.md)**
- Release automation trigger model
- Deployment status updates on GitHub Releases
- Required secrets and troubleshooting guidance

**[DEPLOYMENT.md](DEPLOYMENT.md)**
- Deployment conventions plus manual deployment and rollback runbook
- Cross-links for release metadata, observability, and target playbooks

---

## Architecture

**[ARCHITECTURE.md](ARCHITECTURE.md)**
- System architecture overview
- Component design
- Design decisions and trade-offs
- Performance considerations
- Security implications

---

## Developer Resources

**[AGENTS.md](../AGENTS.md)**
- Project overview for coding agents
- Technology stack details
- Core workflow and key components
- Development commands and setup
- Standard delivery workflow and session-notes rules

**[notes/README.md](../notes/README.md)**
- Session-notes conventions and path layout
- Daily-note structure and content rules
- Direct-push exception for notes-only updates

**[AI_SKILLS.md](AI_SKILLS.md)**
- Canonical `ai-skills/` structure and starter skills
- Local deploy workflow for Claude and Codex skill output
- Troubleshooting rendered skill output

**[CI.md](CI.md)**
- Continuous Integration (CI) pipeline documentation
- GitHub Actions workflow details
- Code quality and testing automation
- Local development workflow
- Running CI checks locally
- Troubleshooting CI failures

**[SECURITY_BASELINE.md](SECURITY_BASELINE.md)**
- Template-level secret scanning workflow and pre-commit baseline
- Post-creation GitHub security features to enable

**[CI_RUNNER.md](CI_RUNNER.md)**
- GitHub-hosted vs self-hosted runner guidance
- Docker CI image contract and local parity workflow
- Runner registration and label alignment notes

**[OBSERVABILITY.md](OBSERVABILITY.md)**
- Two-layer observability model and operator runbook
- Health endpoint patterns and useful LogQL queries

**[RELEASE_WORKFLOW.md](RELEASE_WORKFLOW.md)**
- Release deployment workflow structure
- Trigger normalization and release-body status updates
- Deployment troubleshooting checklist

**[DEPLOYMENT.md](DEPLOYMENT.md)**
- Deployment conventions, rollback path, and secrets-handling notes
- Target/playbook alignment plus service observability links

---

## Operations

**[MANUAL_SMOKE.md](MANUAL_SMOKE.md)**
- Headed Suno login bootstrap
- Bounded prompt-to-song smoke checklist
- Evidence inspection and local artifact cleanup

**[OBSERVABILITY.md](OBSERVABILITY.md)**
- Health endpoint, logging, and Loki query guidance
- systemd naming and session-artifact conventions

**[RELEASE_WORKFLOW.md](RELEASE_WORKFLOW.md)**
- Release workflow triggers and required GitHub Secrets
- Deployment status section written back to GitHub Releases
- Troubleshooting steps for failed or skipped deploys

**[DEPLOYMENT.md](DEPLOYMENT.md)**
- Manual deployment and rollback commands
- Inventory and secrets conventions
- Follow-up customization guidance for target playbooks

---

## Project Status

**Current Phase:** MVP prompt-to-song workflow
- Template instantiated
- `gentle-site-visitor` dependency wired
- Suno create-page visit plan wired
- Suno auth/session bootstrap wired
- Suno create-page selector and fixture-backed extractor layer wired
- Request-aware bounded generation plan wired
- Generation evidence and review artifacts wired

**Next Phase:** Live smoke and operations hardening
- Run the headed manual smoke checklist with the operator's own account
- Review artifact retention expectations after real runs

**Future:** Operations hardening
- Dependency upgrade and release pinning review
- Deployment target selection
- Session artifact retention review

---

## Project History

**[notes/README.md](../notes/README.md)**
- Committed engineering session notes
- Daily, topical, and design-note path conventions
- Guidance on what should and should not go into project notes

---

## Quick Reference

| Document | Purpose | Audience |
|----------|---------|----------|
| [README.md](../README.md) | Getting started, installation, usage | All users |
| [SETUP.md](SETUP.md) | Environment configuration | All users |
| [MANUAL_SMOKE.md](MANUAL_SMOKE.md) | Headed login, live smoke checks, artifact review | Operators, developers |
| [AI_SKILLS.md](AI_SKILLS.md) | AI skill source, deploy, and starter-skill guide | Developers |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Technical architecture and design | Developers |
| [CI.md](CI.md) | CI/CD pipeline and development workflow | Developers |
| [SECURITY_BASELINE.md](SECURITY_BASELINE.md) | Secret scanning baseline and GitHub security setup | Developers, operators |
| [CI_RUNNER.md](CI_RUNNER.md) | Self-hosted runner operations and CI image contract | Developers, operators |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Logging, health, Loki, and operator runbook patterns | Developers, operators |
| [RELEASE_WORKFLOW.md](RELEASE_WORKFLOW.md) | Release deployment automation guide | Developers, operators |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment conventions plus runbook and rollback notes | Developers, operators |
| [AGENTS.md](../AGENTS.md) | Coding-agent workflow and guardrails | Claude Code, Codex, other agents |
| [notes/README.md](../notes/README.md) | Session-notes convention and templates | Developers |

---

## Task Management

**[planning/TASK_MANAGEMENT.md](planning/TASK_MANAGEMENT.md)**
- Development phases and milestones
- Task tracking and prioritization
- Progress monitoring

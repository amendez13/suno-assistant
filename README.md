# Suno Assistant

![CI](https://github.com/amendez13/suno-assistant/workflows/CI/badge.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Coverage](https://img.shields.io/badge/coverage-95%25-green.svg)

A private Suno assistant built on `gentle-site-visitor`.

Suno Assistant is intended to help generate original songs through a user's own
Suno account from explicit creative instructions. It keeps the site-specific
Suno workflow in this repository while relying on `gentle-site-visitor` for
bounded browser execution, pacing, persisted session state, and run artifacts.

## Features

- Site-specific Suno visit plans kept outside the reusable framework.
- A bounded create-page smoke run that exercises the Suno-specific app through `gsv`.
- A future prompt-to-song workflow for original song instructions, generation requests, and evidence capture.
- Gentle human-cadence browsing through `gentle-site-visitor` primitives.
- Per-run observability through manifests, evidence JSONL, HAR, trace, and logs.
- Private-repository workflow with CI, pre-commit, branch protection docs, and session notes.

## Quick Start

### Prerequisites

- Python 3.10 or higher
- pip (Python package installer)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/amendez13/suno-assistant.git
cd suno-assistant
```

2. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate   # On Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

For local framework development, install the sibling checkout in editable mode
after the normal install:

```bash
pip install -e ../gentle-site-visitor
```

4. Configure the application:
```bash
cp config/config.example.yaml config/config.yaml
# Edit config/config.yaml with your settings
```

### Usage

```bash
python -m suno_assistant.main
```

Run the create-page smoke path with a quick, validated song request:

```bash
python -m suno_assistant.main --prompt "A bright original indie pop song about finishing a hard project."
```

Or use a structured YAML request:

```bash
python -m suno_assistant.main --request examples/song-request.yaml
```

The current request-aware path validates the song request before browser startup
and runs the bounded generation plan after the saved Suno session is verified.
The MVP generation path fills supported fields, submits once, waits within a
bounded timeout for visible results or known blocked states, and records a
Suno-specific evidence events in the active GSV evidence sink. It does not
download audio files or bypass Suno quotas, moderation, CAPTCHA, MFA, or other
platform controls.

To inspect the page manually in a visible browser and keep it open after the first navigation:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --keep-open
```

Bootstrap your own Suno account session in a headed browser before running
headless smoke or request-aware flows:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --login
```

Complete Suno login, MFA, CAPTCHA, or other manual verification yourself in the
browser. Suno Assistant does not automate credentials or bypass platform
controls. Browser storage state is persisted locally between launches under
`data/browser/suno/state.json`, so authenticated state, cookie consent, and
other session state can carry across runs. If a later run cannot reach
`https://suno.com/create` as an authenticated page, it exits with a blocked auth
result before running any generation plan.

The sample config also supports the framework CLI directly:

```bash
gsv --config config/config.yaml run suno --once
```

When observability is enabled, request-aware runs write reviewable evidence to
the active session bundle:

```text
data/sessions/suno/<session-id>/evidence.jsonl
```

Events include `request_loaded`, `generation_submitted`,
`generation_completed`, `generation_blocked`, and `generation_failed`. Evidence
contains the explicit prompt and visible result metadata, so treat session
artifacts as sensitive local files.

## Configuration

Configuration is stored in `config/config.yaml`. See `config/config.example.yaml` for all available options.

```yaml
visitor:
  headless: true

sites:
  suno:
    app_module: "suno_assistant.visit"
    allowed_host_globs:
      - "https://suno.com/**"
    auth:
      auth_marker_url: "https://suno.com/create"
```

`auth_marker_url` is the authenticated create-page marker used by the GSV
session layer. If Suno redirects that URL to a sign-in or verification page, run
the headed login bootstrap again.

## Song Request Files

Suno Assistant accepts YAML request files with the following fields:

```yaml
prompt: "A required original-song creative brief."
title: "Optional local title"
style: "Optional genre, mood, instrumentation, or arrangement guidance"
lyrics: "Optional user-provided lyrics"
instrumental: false
custom_mode: false
count: 1
tags:
  - demo
notes: "Optional local-only notes"
```

Validation rejects empty prompts, unknown fields, non-positive or overly broad
counts, lyrics on instrumental requests, and explicit requests to imitate a
specific artist or voice. The initial hard cap is `4` generations per request.

## Project Structure

```
suno-assistant/
├── .github/workflows/    # CI/CD configuration
├── .claude/              # Claude Code configuration
├── config/               # Configuration files
├── docs/                 # Documentation
├── suno_assistant/      # Source code
├── tests/                # Test files
├── AGENTS.md             # Source-of-truth agent guidance
├── CLAUDE.md             # Symlink to AGENTS.md for Claude compatibility
├── README.md             # This file
├── pyproject.toml        # Tool configuration
└── requirements.txt      # Dependencies
```

## Development

### Dependency Strategy

Suno Assistant should consume `gentle-site-visitor` as a Python package
dependency, not as a submodule/subtree. The Suno-specific repository owns
site adapters, selectors, configuration, and visit-plan assembly. The framework
repository owns browser/session/pacing/observability/run mechanics.

The framework dependency is a Git URL pinned to a release tag for repeatable installs:

```text
gentle-site-visitor @ git+https://github.com/amendez13/gentle-site-visitor.git@v2026.05.07.1
```

Use an adjacent editable checkout when developing framework and app changes together.

### Setup Development Environment

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=suno_assistant --cov-report=term-missing
```

### Code Quality

This project uses:
- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking
- **bandit** for security scanning
- **pip-audit** for dependency vulnerability checking
- **gitleaks** for secret detection in commits and repository history

Baseline checks run automatically via pre-commit hooks and GitHub Actions.

## CI/CD

GitHub Actions runs the following checks on every push and PR:

1. **Lint**: Black, isort, flake8, mypy
2. **Test**: pytest across Python 3.10, 3.11, 3.12
3. **Coverage**: 95% minimum coverage
4. **Security**: bandit and pip-audit
5. **Secret scanning**: gitleaks against repository history with redacted reporting

See [docs/CI.md](docs/CI.md) for details.

## Documentation

- [Documentation Index](docs/INDEX.md) - All documentation
- [Setup Guide](docs/SETUP.md) - Installation and configuration
- [CI Documentation](docs/CI.md) - CI/CD pipeline details
- [Security Baseline](docs/SECURITY_BASELINE.md) - Secret scanning and recommended GitHub security features
- [AI Skills](docs/AI_SKILLS.md) - Canonical AI-skill source and deploy workflow

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit your changes (`git commit -m 'feat: add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Operating Boundary

This project is for low-impact, user-directed song creation in the operator's
own Suno account. It is not a stealth, evasion, scraping, CAPTCHA-bypass, or
platform-policy bypass toolkit. Prompts and automation should respect Suno
terms, rate limits, account constraints, rights of third parties, and any
applicable artist/style/content restrictions.

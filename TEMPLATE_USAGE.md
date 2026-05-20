# Python Project Template Usage Guide

This template provides a complete Python project setup with CI/CD, quality tools, documentation, shared Claude/Codex AI-skill configuration, committed session notes, and coding-agent configuration.

## Quick Start

### Option 1: Interactive Setup (Recommended)

```bash
# Copy template to your new project location
cp -r /path/to/python-project-template ~/projects/my-new-project

# Navigate to the new project
cd ~/projects/my-new-project

# Run the interactive setup script
python setup_template.py
```

The script will prompt you for:
- Project name and description
- GitHub owner/organization
- Python version requirements
- Code quality settings (line length, complexity, coverage)
- Directory names

### Option 2: Manual Setup

If you prefer to configure manually:

1. Copy the template directory
2. Find and replace all `{{VARIABLE_NAME}}` placeholders in the files
3. Rename `suno_assistant/` and `tests/` directories if needed
4. Initialize git and install pre-commit hooks

## Template Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `suno-assistant` | Project name (repository and package) | `my-python-project` |
| `A private Suno assistant built on gentle-site-visitor` | Short one-line description | `A Python project` |
| `amendez13` | GitHub username or organization | `your-username` |
| `3.10` | Minimum Python version | `3.10` |
| `3.10, 3.11, 3.12` | CI matrix versions (comma-separated) | `3.10, 3.11, 3.12` |
| `127` | Maximum code line length | `127` |
| `10` | Maximum cyclomatic complexity | `10` |
| `95` | Minimum test coverage percentage | `95` |
| `suno_assistant` | Source code directory name | `src` |
| `tests` | Test directory name | `tests` |
| `main` | Main branch name | `main` |
| `develop` | Development branch name | `develop` |
| `github_hosted` | Default CI runner target | `github_hosted` |

`127` defaults to `127` because it aligns with the template's Black-based formatting and reduces unnecessary wrapping noise in pull requests on modern editor widths.

## Template Structure

```
python-project-template/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml                 # Main CI pipeline
│   │   ├── ci-image.yml           # Shared CI image build/publish workflow
│   │   ├── gitleaks.yml           # Repository secret-scanning workflow
│   │   ├── release.yml            # Manual + release-event deployment workflow
│   │   ├── claude.yml             # Claude Code automation
│   │   └── claude-code-review.yml # AI code review
│   └── dependabot.yml             # Dependency updates
├── .claude/
│   └── settings.local.json        # Claude Code permissions
├── .mcp.json.example              # MCP configuration starting point
├── .env.example                   # Environment-variable configuration example
├── ai-skills/
│   ├── suno-assistant-example-skill/    # Minimal scaffold for new project skills
│   ├── suno-assistant-feature-delivery/ # Project-specific issue-delivery skill
│   ├── suno-assistant-feature-design/   # Project-specific issue-design skill + helper assets
│   └── suno-assistant-session-notes/
│       ├── skill.yaml                     # Canonical manifest for the project session-notes skill
│       └── instructions.md                # Shared skill instructions for agent harnesses
├── config/
│   └── config.example.yaml        # Configuration template
├── docs/
│   ├── INDEX.md                   # Documentation hub
│   ├── AI_SKILLS.md               # AI skills source/deploy documentation
│   ├── SETUP.md                   # Installation guide
│   ├── ARCHITECTURE.md            # Technical design
│   ├── CI.md                      # CI/CD documentation
│   ├── CI_RUNNER.md               # Self-hosted runner and CI image guide
│   ├── SECURITY_BASELINE.md       # Secret scanning and GitHub security baseline
│   ├── RELEASE_WORKFLOW.md        # Release deployment workflow guide
│   ├── DEPLOYMENT.md              # Manual deployment runbook
│   ├── BRANCH_PROTECTION.md       # Branch protection documentation
│   └── planning/
│       └── TASK_MANAGEMENT.md     # Task tracking
├── infra/
│   ├── ai-skills/
│   │   ├── deploy_ai_skills.yml   # Dual-deploy playbook for AI skills
│   │   └── templates/             # Jinja templates for Claude/Codex rendering
│   ├── ci/
│   │   ├── Dockerfile             # Shared Ubuntu CI image
│   │   ├── docker-compose.ci.yml  # Local CI container shell
│   │   └── build-and-push.sh      # Manual multi-arch CI image helper
│   ├── hetzner/
│   │   ├── inventory.local.ini.example # Example VPS inventory
│   │   ├── secrets.yml.example    # Example deploy vars
│   │   └── provision_vps.yml      # VPS bootstrap skeleton
│   ├── home-worker/
│   │   ├── ci_runner_setup.yml    # Self-hosted runner bootstrap skeleton
│   │   ├── inventory.local.ini.example # Example worker inventory
│   │   ├── secrets.yml.example    # Example worker vars
│   │   ├── deploy_target_setup.yml # Worker/bootstrap skeleton
│   │   └── redeploy.yml           # Home-worker redeploy skeleton
│   └── site/
│       └── redeploy.yml           # Site deployment orchestration skeleton
├── scripts/
│   ├── deploy_ai_skills.sh        # Local AI skills deploy wrapper
│   ├── redeploy.sh                # Ansible redeploy wrapper
│   ├── release_smoke_check.sh     # Post-deployment smoke checks
│   └── github/
│       ├── branch-protection-config.json  # Protection rules config
│       ├── resolve_release_context.py     # Release-trigger normalization helper
│       └── setup-branch-protection.sh     # Setup script
├── notes/
│   ├── .gitkeep                   # Keeps the committed notes directory in the template
│   ├── .notes-config.yaml.example # Optional secondary summary-log configuration template
│   └── README.md                  # Session-notes convention and daily-note template
├── suno_assistant/                           # Source code
│   ├── __init__.py
│   └── main.py
├── tests/                         # Test files
│   ├── __init__.py
│   ├── conftest.py
│   └── test_main.py
├── AGENTS.md                      # Source-of-truth agent workflow and project guidance
├── CLAUDE.md                      # Symlink to AGENTS.md for Claude compatibility
├── README.md                      # Project overview
├── TEMPLATE_USAGE.md              # This file
├── pyproject.toml                 # Tool configuration
├── .pre-commit-config.yaml        # Pre-commit hooks
├── .flake8                        # Flake8 config
├── .pylintrc                      # Pylint config
├── .gitignore                     # Git exclusions
├── requirements.txt               # Production dependencies
├── requirements-dev.txt           # Development dependencies
└── setup_template.py              # Interactive setup script
```

## What's Included

### CI/CD Pipeline (`.github/workflows/ci.yml`)

- **Resolve-runner job**: Selects GitHub-hosted vs self-hosted labels and skip mode
- **Lint job**: Black, isort, flake8, mypy in the shared CI image
- **Test job**: pytest across Python 3.10, 3.11, 3.12 after coverage passes
- **Coverage job**: Enforces coverage threshold with HTML reports
- **Security job**: bandit and pip-audit scanning
- **Secret-scanning workflow**: gitleaks on pushes, PRs, and manual dispatch
- **Config validation**: YAML and Python syntax checks
- **Smart skip logic**: docs-only diffs and merged-PR pushes to `main` skip heavy jobs but still report `CI Status Check`

### Docker CI Environment (`infra/ci/`)

- **Dockerfile**: Ubuntu 24.04 CI image with Python 3.10, 3.11, and 3.12 plus preinstalled CI tooling
- **docker-compose.ci.yml**: Local shell into the same environment GitHub Actions uses
- **build-and-push.sh**: Manual multi-platform build helper for GHCR

### Self-Hosted Runner Support

- **resolve-runner** output drives `runs-on: ${{ fromJSON(...) }}` in CI
- **CI_RUNNER** template variable sets the default runner target
- **infra/home-worker/ci_runner_setup.yml** provides a Linux runner bootstrap skeleton
- **docs/CI_RUNNER.md** explains GitHub-hosted vs self-hosted usage and runner-as-contract guidance

### Release Workflow Skeleton

- **release.yml** supports `workflow_dispatch` and `release: published` triggers
- **resolve_release_context.py** normalizes trigger-specific metadata into stable outputs
- **scripts/redeploy.sh** selects the appropriate Ansible playbook for `hetzner` or `home_worker`
- **scripts/release_smoke_check.sh** performs generic HTTP checks with an optional version/ref assertion
- **docs/RELEASE_WORKFLOW.md** documents operator usage, required secrets, and the release-body deployment status section
- **docs/DEPLOYMENT.md** documents manual deploy and rollback commands

Recommended GitHub Secrets for the release pipeline:

- `DEPLOY_SSH_PRIVATE_KEY`
- `DEPLOY_KNOWN_HOSTS`
- `HETZNER_INVENTORY`
- `HETZNER_SECRETS_YAML`
- `HETZNER_BASE_URL`
- `CREATE_WORKER_INVENTORY`
- `CREATE_WORKER_SECRETS_YAML`
- `CREATE_WORKER_BASE_URL`

### Agent Guidance And Session Notes

- **AGENTS.md**: Shared workflow rules and project context for coding agents
- **CLAUDE.md -> AGENTS.md**: Compatibility symlink so Claude and other agents read the same guidance
- **.mcp.json.example**: Copyable MCP server configuration starter for local setup
- **notes/**: Committed engineering session notes with daily-note path conventions
- **ai-skills/suno-assistant-session-notes/**: Canonical skill for creating and updating session notes

### AI Agent Workflows (Optional)

- **claude.yml**: Automation triggered by `@claude` mentions in issues/PRs
- **claude-code-review.yml**: Code review via `/claude-review` comment
- **ai-skills/**: Canonical AI skills source rendered to both Claude and Codex

> **Note**: These require a `CLAUDE_CODE_OAUTH_TOKEN` secret in your repository.

### Pre-commit Hooks

The template includes formatting, linting, typing, dependency, secret-scanning, and generic hygiene hooks.

Security-focused hooks include:
- `bandit`
- `pip-audit`
- `gitleaks`
- `detect-private-key`

### Branch Protection (`scripts/github/`)

Automated branch protection configuration:

- **Required status checks**: All CI jobs must pass
- **Security gate**: `Secret Scanning` can be required alongside the CI aggregate checks
- **Linear history**: No merge commits (squash or rebase only)
- **Conversation resolution**: All review comments must be resolved
- **Force push protection**: Prevents accidental history overwrites
- **Deletion protection**: Prevents accidental branch deletion

Setup via `setup_template.py` or manually:
```bash
./scripts/github/setup-branch-protection.sh
```

See `docs/BRANCH_PROTECTION.md` for full documentation.

### Documentation Structure

- `AGENTS.md` - Shared coding-agent guidance and workflow rules
- `CLAUDE.md` - Symlink to `AGENTS.md`
- `README.md` - User-facing project documentation
- `docs/INDEX.md` - Central documentation hub
- `docs/AI_SKILLS.md` - Canonical AI skills structure and deploy workflow
- `docs/CI.md` - CI/CD pipeline documentation
- `docs/CI_RUNNER.md` - Self-hosted runner operations and CI image contract
- `docs/SECURITY_BASELINE.md` - Secret scanning baseline and GitHub security setup
- `docs/RELEASE_WORKFLOW.md` - Release deployment workflow documentation
- `docs/DEPLOYMENT.md` - Manual deployment and rollback runbook
- `docs/SETUP.md` - Installation and configuration guide
- `docs/ARCHITECTURE.md` - Technical architecture (placeholder)
- `docs/BRANCH_PROTECTION.md` - Branch protection rules documentation
- `docs/planning/TASK_MANAGEMENT.md` - Development task tracking
- `notes/README.md` - Session-notes convention and example structure

### AI Skills

The template now ships a minimal example scaffold plus starter AI skills:
- `suno-assistant-example-skill` for copying into new project-specific skills
- `suno-assistant-feature-delivery` for end-to-end issue implementation workflow
- `suno-assistant-feature-design` for turning rough requests into implementation-ready GitHub issues
- `suno-assistant-session-notes` for committed project session notes

Deploy both to Claude and Codex with:

```bash
./scripts/deploy_ai_skills.sh
```

See `docs/AI_SKILLS.md` for the canonical layout, rendering model, and troubleshooting guidance.

### MCP Configuration

Copy the example file when you want local MCP server configuration:

```bash
cp .mcp.json.example .mcp.json
```

Then customize `.mcp.json` for your own servers and credentials. The real `.mcp.json` stays ignored by git.

### CI Image Bootstrap

Before requiring the new containerized CI contexts in branch protection, publish the shared CI image at least once:

```bash
./infra/ci/build-and-push.sh
```

Or trigger `.github/workflows/ci-image.yml` manually from GitHub Actions.

## Post-Setup Steps

After running `setup_template.py`:

1. **Install dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements-dev.txt
   ```

2. **Verify setup**:
   ```bash
   # Run tests
   pytest

   # Run pre-commit hooks
   pre-commit run --all-files
   ```

3. **Configure GitHub** (if using Claude workflows):
   - Add `CLAUDE_CODE_OAUTH_TOKEN` secret to repository
   - Enable GitHub Actions
   - Review `docs/SECURITY_BASELINE.md` and enable GitHub secret scanning, push protection, and CodeQL where available

4. **Start developing**:
   - Add your code to `suno_assistant/`
   - Add tests to `tests/`
   - Update documentation as needed

## Customization

### Removing Claude Workflows

If you don't use Claude Code, delete:
- `.github/workflows/claude.yml`
- `.github/workflows/claude-code-review.yml`
- `.claude/` directory

Update `.github/dependabot.yml` to remove the Claude-specific reviewer.

### Adjusting Quality Settings

Edit these files to customize quality rules:
- `pyproject.toml` - Black, isort, pytest, mypy, coverage
- `.flake8` - Flake8 rules
- `.pylintrc` - Pylint rules
- `.pre-commit-config.yaml` - Hook versions and arguments

### Adding Dependencies

1. Add to `requirements.txt` (production)
2. Add to `requirements-dev.txt` (development only)
3. Update `pyproject.toml` if adding type stubs

### Configuration Style

The template includes both `config/config.example.yaml` and `.env.example`.

- Prefer YAML when your application needs grouped or nested configuration.
- Prefer `.env` when your local workflow, deployment target, or process manager is already environment-variable driven.
- `python-dotenv` is included in the base template so projects can load `.env` during development without extra setup.

### Session Notes Workflow

- Keep project-history notes in `notes/YYYY/MM/YYYY-MM-DD.md`.
- Use `notes/README.md` as the style guide and starter template.
- If you want the optional secondary summary-log workflow, copy `notes/.notes-config.yaml.example` to `notes/.notes-config.yaml` and update the paths.
- If you use shared AI-skill deployment, treat `ai-skills/suno-assistant-session-notes/` as the canonical source.

### CI Runner Target

- `github_hosted` controls the default runner target used by `.github/workflows/ci.yml`.
- Supported values are `github_hosted`, `self_hosted_linux`, and `self_hosted_linux_arm64`.
- Keep the workflow, `docs/CI_RUNNER.md`, and any self-hosted runner bootstrap playbooks aligned if you change the labels or targets.

## Troubleshooting

### Pre-commit hooks fail

```bash
# Update hooks to latest versions
pre-commit autoupdate

# Clear cache and retry
pre-commit clean
pre-commit run --all-files
```

### CI fails on coverage

- Check `htmlcov/index.html` for uncovered lines
- Add tests or use `# pragma: no cover` sparingly
- Adjust `95` if needed

### Type checking errors

- Add type hints to function signatures
- Install type stubs: `pip install types-<package>`
- Use `# type: ignore` with explanation for edge cases

## License

This template is provided as-is. Choose an appropriate license for your project.

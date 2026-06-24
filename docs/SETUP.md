# Setup Guide

This guide walks you through setting up suno-assistant for development or usage.

## Prerequisites

- Python 3.12 or higher
- pip (Python package installer)
- git

### Optional

- [List optional dependencies]

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/amendez13/suno-assistant.git
cd suno-assistant
```

### 2. Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate   # On Windows
```

### 3. Install Dependencies

```bash
# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt
```

### 4. Configure the Application

```bash
# Copy example configuration
cp config/config.example.yaml config/config.yaml

# Edit configuration with your settings
# On macOS/Linux:
nano config/config.yaml
# Or use your preferred editor
```

You can also start from environment variables instead:

```bash
cp .env.example .env
# Edit .env with your local values
```

### 5. Verify Installation

```bash
# Run tests to verify setup
pytest

# Or inspect the local smoke-run CLI
python -m suno_assistant.main --help

# Or run the create-page smoke visit
python -m suno_assistant.main

# Or validate a quick song request before the create-page smoke visit
python -m suno_assistant.main --prompt "A warm original synth pop song about planning a careful launch."

# Or validate a structured song request before the create-page smoke visit
python -m suno_assistant.main --request examples/song-request.yaml

# Or fill the create box without submitting generation
python -m suno_assistant.main --config config/config.yaml --headed --keep-open --fill-only \
  --prompt "A warm original acoustic pop song about planning a careful launch."

# Or fill Advanced mode controls without submitting generation
python -m suno_assistant.main --config config/config.yaml --headed --keep-open --fill-only \
  --request examples/advanced-song-request.yaml

# Or keep a headed browser open for manual inspection
python -m suno_assistant.main --config config/config.yaml --headed --keep-open

# Or bootstrap your own Suno login session in a headed browser
python -m suno_assistant.main --config config/config.yaml --headed --login
```

The browser storage state is saved locally under `data/browser/suno/state.json`
after authenticated runs, so login state, cookie consent, and other local
session state can be reused on the next launch.

Before running a live prompt-to-song smoke request, review the operator checklist
in [MANUAL_SMOKE.md](MANUAL_SMOKE.md). Live request-aware runs can consume Suno
account quota or credits and write prompt/result metadata into local session
artifacts.

## Configuration

### config/config.yaml

The main configuration file. See `config/config.example.yaml` for all available options.

```yaml
visitor:
  headless: true

sites:
  suno:
    app_module: suno_assistant.visit
    allowed_host_globs:
      - https://suno.com/**
    auth:
      auth_marker_url: https://suno.com/create
```

`auth_marker_url` is the authenticated marker checked before any create-page
workflow runs. If Suno redirects that URL to login, auth, verification, or a
third-party provider, the run returns an auth-required blocked result before
building a generation plan.

### Suno Login Bootstrap

Run the login bootstrap when setting up the project on a new machine or when
Suno expires the saved browser state:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --login
```

Complete the login, MFA, CAPTCHA, or other manual verification in the visible
browser. Suno Assistant does not type credentials, solve challenges, or bypass
platform controls. A successful bootstrap persists local storage state under
`data/browser/suno/state.json`.

Headless login bootstrap is intentionally rejected:

```bash
python -m suno_assistant.main --login
# Invalid login request: use --headed --login for manual Suno login bootstrap.
```

For normal runs, missing or expired auth returns a blocked result and tells the
operator to rerun the headed login bootstrap.

### Environment Variables

You can also configure the application using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_DEBUG` | Enable debug mode | `false` |
| `APP_LOG_LEVEL` | Logging level | `INFO` |

### YAML vs `.env`

Both configuration styles are included so a new project can choose the lighter-weight approach that fits its runtime model.

- Use `config/config.yaml` when your project naturally groups structured or nested settings.
- Use `.env` when deployment platforms, process managers, or local tooling already revolve around environment variables.
- `python-dotenv` is included so projects can load a local `.env` file during development without exporting each variable manually.
- It is reasonable to ship both examples and let the application define precedence between YAML and environment variables.

## Song Request YAML

Structured song requests are separate from runtime configuration and can be
stored anywhere outside sensitive artifact directories. See
`examples/song-request.yaml` for a safe example.

Supported fields:

```yaml
prompt: "Required original-song creative brief."
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

The CLI validates requests before starting the browser. Invalid request files,
empty prompts, unknown fields, unsupported count values, lyrics on instrumental
requests, or explicit requests to imitate a specific artist or voice return an
error without launching a Suno browser session.

When a request is supplied and the saved Suno session is authenticated, Suno
Assistant runs the bounded MVP generation plan:

1. Navigate to `https://suno.com/create`.
2. Verify the create page is ready and not blocked by auth, quota, or policy states.
3. Fill the prompt and supported optional fields from the validated request.
4. Submit one create/generate action.
5. Wait within a bounded timeout for visible result cards or known blocked states.

The MVP path does not download generated audio, retry around platform blocks, or
automate CAPTCHA/MFA. Live generation can consume account quota or credits, so
use low-impact original prompts for manual smoke runs.

Use `--fill-only` with `--prompt` or `--request` to populate supported create
fields without clicking create/generate. This is useful for headed inspection
and can still fill the prompt box when the page is authenticated and the prompt
input is visible but generation submission is blocked by quota.

Set `advanced_mode: true` in a request file to switch to Suno Advanced mode and
fill deterministic Advanced controls: lyrics, style, exclude styles,
instrumental, vocal gender, style mode, Weirdness, and Style Influence. The app
does not operate account asset pickers or generative helper buttons such as
Audio, Voice, Inspo, saved styles, random prompts, lyrics generation, or
workspace selection. See [CREATE_BOX.md](CREATE_BOX.md) for the full
create-page UI contract, including visible-field selection, More Options
expansion, title filling, and slider setting.

There is no standalone dry-run flag in the MVP CLI. Request validation happens
before browser startup, and invalid prompt or YAML inputs exit without opening
Suno.

## Session Notes

This template treats session notes as committed project history, not private scratch files.

- Read [AGENTS.md](../AGENTS.md) for the delivery workflow rules that govern when notes should be updated.
- Read [notes/README.md](../notes/README.md) for the directory layout, note style, and the daily-note template.
- Daily notes live at `notes/YYYY/MM/YYYY-MM-DD.md`.
- If you want the optional secondary summary-log workflow, copy `notes/.notes-config.yaml.example` to `notes/.notes-config.yaml` and customize the paths for your environment.
- The canonical skill source for note automation lives at `ai-skills/suno-assistant-session-notes/`. If you use the shared AI-skills deployment pattern, deploy that skill to your local agent harnesses after editing it.

## MCP Configuration

The template ships `.mcp.json.example` as a generic starting point for local MCP server configuration.

```bash
cp .mcp.json.example .mcp.json
```

Then customize the server list for your project and local tools.

- `.mcp.json` is intentionally ignored by git because each developer's MCP setup is local.
- Keep `.mcp.json.example` generic and safe to commit.
- If your project depends on a required MCP server, document that requirement here or in a project-specific operations guide.

## Development Setup

### Install Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Verify hooks work
pre-commit run --all-files
```

Because this template includes the official `gitleaks` hook, the `pre-commit>=3.6.0` requirement in `requirements-dev.txt` matters: modern `pre-commit` can bootstrap the hook's Go toolchain automatically.

### Enable Repository Security Features

After the repository exists on GitHub, review and enable the baseline security features described in [SECURITY_BASELINE.md](SECURITY_BASELINE.md):

- secret scanning
- push protection
- CodeQL default setup

These features are configured in GitHub, not in the local bootstrap commands above.

### Deploy AI Skills

The template ships canonical AI skill sources under `ai-skills/` and a deploy flow that renders them to both Claude and Codex:

```bash
./scripts/deploy_ai_skills.sh
```

Requirements:
- `ansible-playbook` installed locally
- write access to `~/.claude/skills/` and `~/.codex/skills/`

The deploy script renders:
- Claude skills to `~/.claude/skills/<name>/skill.md`
- Codex skills to `~/.codex/skills/<name>/SKILL.md`
- Codex interface metadata to `~/.codex/skills/<name>/agents/openai.yaml`

The shipped skill names are project-specific after setup, for example
`suno-assistant-feature-delivery`, so this project does not overwrite another
project's installed `feature-delivery` skill.

See [AI_SKILLS.md](AI_SKILLS.md) for the canonical source layout, starter skills, and troubleshooting guidance.

### Claude Permissions And Fewer Prompts

`.claude/settings.local.json` is the committed baseline allowlist for Claude Code in this template.

- Expand it when the project consistently uses the same safe local commands.
- Keep the list narrow enough that new or risky commands still require a prompt.
- Treat it as an audit trail for the "fewer permission prompts" workflow rather than a place to allow everything.

Typical additions in this template include:
- `git` and `gh` commands used during issue delivery
- `pre-commit`, `pytest`, and static-analysis commands
- `gitleaks` when you run manual repository scans outside pre-commit
- `ansible-playbook` and the local AI-skills deploy wrapper
- common filesystem inspection commands needed during template setup work

### Line Length Recommendation

The template defaults `127` to `127`.

- It aligns with Black and the rest of the code-quality configuration in this template.
- It fits modern editor widths better than older narrow defaults.
- It reduces avoidable line-break noise in pull requests while remaining readable in split views.

### IDE Setup

#### VS Code

Recommended extensions:
- Python
- Pylance
- Black Formatter
- isort

Settings (`.vscode/settings.json`):
```json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "[python]": {
        "editor.codeActionsOnSave": {
            "source.organizeImports": true
        }
    }
}
```

#### PyCharm

1. Set Python interpreter to `./venv/bin/python`
2. Enable Black formatter
3. Enable isort for imports

## Troubleshooting

### Common Issues

**Virtual environment not activated**
```bash
source venv/bin/activate
```

**Dependencies not installed**
```bash
pip install -r requirements.txt
```

**Pre-commit hooks not running**
```bash
pre-commit install
```

**Configuration file not found**
```bash
cp config/config.example.yaml config/config.yaml
```

### Getting Help

- Check the [Documentation Index](INDEX.md)
- Review [notes/README.md](../notes/README.md) for note conventions
- Review [CI documentation](CI.md) for testing issues
- Review [SECURITY_BASELINE.md](SECURITY_BASELINE.md) for secret-scanning setup and GitHub security features
- Open an issue on GitHub

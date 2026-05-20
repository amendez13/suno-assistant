# CI Runner Operations

This guide documents how the template chooses between GitHub-hosted and self-hosted runners, how the shared CI image acts as the execution contract, and what you need to provision if you want to run CI on your own hardware.

## When To Use Which Runner

### GitHub-hosted

Use `github_hosted` when:

- you want the lowest-setup path
- your project does not need persistent self-hosted infrastructure
- you want GitHub to manage runner lifecycle and OS patching

### Self-hosted

Use `self_hosted_linux` or `self_hosted_linux_arm64` when:

- you need a fixed machine, architecture, or private network access
- you want to reuse a local Docker cache or pre-pulled CI image
- you need parity with deployment hardware or ARM-specific behavior

## Runner-As-Contract Guidance

The Docker CI image is the contract. The runner should be treated as a thin host that only needs to:

- run GitHub Actions jobs
- run Linux containers
- pull `ghcr.io/amendez13/suno-assistant-ci:latest`

That means:

- GitHub-hosted CI, self-hosted CI, and local `docker compose` runs all execute the same toolchain
- "works on my machine" should map to "works in CI" when you validate inside `infra/ci/docker-compose.ci.yml`
- host-specific setup belongs in runner bootstrap playbooks, not in individual CI jobs

## Workflow Surface

`ci.yml` resolves runner selection centrally:

- default target: `github_hosted`
- manual override via `workflow_dispatch` input `runner_target`
- supported values:
  - `github_hosted`
  - `self_hosted_linux`
  - `self_hosted_linux_arm64`

Downstream jobs consume:

- `runs-on: ${{ fromJSON(needs.resolve-runner.outputs.runner) }}`
- `container.options` from `resolve-runner`

For self-hosted runners, the template assumes the runner workspace should remain writable by a non-root user and therefore runs CI containers with an explicit UID:GID mapping.

## Register A Self-Hosted Runner

1. Create a Linux host that can run Docker containers.
2. Create a GitHub runner registration token for the repository.
3. Copy and adapt `infra/home-worker/ci_runner_setup.yml` for your environment.
4. Keep the runner labels aligned with `.github/workflows/ci.yml`.
5. Optionally pre-pull `ghcr.io/amendez13/suno-assistant-ci:latest` after provisioning.

Suggested baseline labels:

- `self-hosted`
- `linux`

Add `arm64` if the host should satisfy the ARM-specific target.

## Use The Docker CI Image Locally

```bash
docker build -t suno-assistant-ci:test -f infra/ci/Dockerfile .
docker compose -f infra/ci/docker-compose.ci.yml run --rm ci bash
```

Inside the container, run the same commands CI uses:

```bash
python3.12 -m pytest tests/ -v --cov=suno_assistant
bandit -r suno_assistant/ -ll
pip-audit --requirement requirements.txt
```

## Bootstrap Checklist For Self-Hosted Linux

- install Docker Engine and confirm the runner user can access it
- install the GitHub Actions runner binary for the host architecture
- register the runner for `https://github.com/amendez13/suno-assistant`
- configure the runner as a persistent service
- verify the runner can pull `ghcr.io/amendez13/suno-assistant-ci:latest`
- run a manual `workflow_dispatch` CI job against the self-hosted target

## Operational Notes

- If you rename CI jobs, update the required status contexts in `scripts/github/branch-protection-config.json`.
- If you change runner labels, keep `docs/CI_RUNNER.md`, `infra/home-worker/ci_runner_setup.yml`, and `.github/workflows/ci.yml` aligned.
- If you change the shared toolchain, rebuild the CI image before expecting CI to pick it up.

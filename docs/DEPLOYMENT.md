# Deployment
This repository includes deployment-facing skeletons rather than a project-specific deploy implementation. Use this document for both deployment conventions and the manual runbook that matches the release automation skeleton.

## Service Naming

When deploying with `systemd`, keep unit names aligned with the observability conventions described in [OBSERVABILITY.md](OBSERVABILITY.md):

- `suno-assistant.service`
- `suno-assistant-<job>.service`
- `suno-assistant-<job>.timer`

Matching unit names, Syslog identifiers, and Loki labels makes operator workflows simpler.

## Release Metadata

Expose release metadata through `suno_assistant/release_info.py` so health endpoints and startup logs can report the running tag and commit.

## Loki Integration

If your deployment ships journald logs into Loki, prefer the `component="suno-assistant"` label described in [OBSERVABILITY.md](OBSERVABILITY.md). That keeps project queries stable across environments.

## Graceful Shutdown

Long-running tasks should use a longer `TimeoutStopSec=` than the systemd default so in-flight work can finalize and write any session artifacts before forceful termination.

## Manual Deployment Runbook

## Files And Directories

- `.github/workflows/release.yml`: orchestration entry point
- `scripts/github/resolve_release_context.py`: trigger normalization helper
- `scripts/redeploy.sh`: wrapper around the target-specific Ansible playbook
- `scripts/release_smoke_check.sh`: post-deploy HTTP smoke checks
- `infra/hetzner/`: VPS provisioning skeleton and example inventory/secrets
- `infra/home-worker/`: worker/runner deployment skeleton and example inventory/secrets
- `infra/site/`: site deployment orchestration playbooks

## Manual Deployment

### 1. Prepare local files from the examples

```bash
cp infra/hetzner/inventory.local.ini.example infra/hetzner/inventory.local.ini
cp infra/hetzner/secrets.yml.example infra/hetzner/secrets.yml
```

Or for the home-worker target:

```bash
cp infra/home-worker/inventory.local.ini.example infra/home-worker/inventory.local.ini
cp infra/home-worker/secrets.yml.example infra/home-worker/secrets.yml
```

### 2. Run the redeploy wrapper

Hetzner / site target:

```bash
./scripts/redeploy.sh --target hetzner --deploy-ref <tag-or-commit>
```

Home-worker target:

```bash
./scripts/redeploy.sh --target home_worker --deploy-ref <tag-or-commit>
```

### 3. Run smoke checks

```bash
./scripts/release_smoke_check.sh --base-url https://example.com --smoke-level basic
./scripts/release_smoke_check.sh --base-url https://example.com --smoke-level extended --expected-ref <tag-or-commit>
```

## Rollback

The skeleton rollback path is "redeploy the previous known-good ref":

```bash
./scripts/redeploy.sh --target hetzner --deploy-ref <previous-tag>
./scripts/release_smoke_check.sh --base-url https://example.com --smoke-level basic --expected-ref <previous-tag>
```

If your real deployment process includes migrations, data backfills, or asset versioning, document the rollback-specific steps inside the target playbooks before relying on this runbook operationally.

## Secrets Management

Do not commit live inventory or secrets files.

- committed examples end in `.example`
- live files are ignored in `.gitignore`
- release automation expects the live file contents to arrive from GitHub Secrets

Suggested GitHub Secrets:

- `DEPLOY_SSH_PRIVATE_KEY`
- `DEPLOY_KNOWN_HOSTS`
- `HETZNER_INVENTORY`
- `HETZNER_SECRETS_YAML`
- `HETZNER_BASE_URL`
- `CREATE_WORKER_INVENTORY`
- `CREATE_WORKER_SECRETS_YAML`
- `CREATE_WORKER_BASE_URL`

## Operator Notes

- Keep `.github/workflows/release.yml`, the example inventory files, and the real playbooks aligned when you rename groups or paths.
- `scripts/redeploy.sh` currently assumes `hetzner` maps to `infra/site/redeploy.yml` and `home_worker` maps to `infra/home-worker/redeploy.yml`.
- `scripts/release_smoke_check.sh` only performs generic HTTP checks; most real projects should customize the extended check to hit an application-specific version or build endpoint.

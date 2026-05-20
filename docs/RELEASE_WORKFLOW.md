# Release Workflow

This guide documents the template release automation in `.github/workflows/release.yml`.

## What It Does

The release workflow provides a deployment-oriented automation path that:

- accepts manual `workflow_dispatch` runs for controlled deployments
- reacts to `release: published` events for release-driven rollouts
- authorizes the repository owner for user-owned repos and admin collaborators for organization-owned repos
- serializes deployments with a global concurrency lock
- verifies or creates the requested release tag before deployment
- records deployment state back onto the GitHub Release body
- materializes inventories and secrets from GitHub Secrets instead of tracking live credentials in git

## Triggers

### Manual dispatch

Use `Actions -> Release Deployment -> Run workflow` when you want to choose:

- `ref`: branch, tag, or commit to deploy
- `release_tag`: tag to create or verify
- `target`: `hetzner` or `home_worker`
- `smoke_level`: `basic` or `extended`

### Published release

Publishing a GitHub Release also triggers the workflow. In this path:

- `release.tag_name` becomes the deployment tag
- the published tag itself becomes the deployment ref
- target defaults to `hetzner`
- smoke level defaults to `basic`

## Re-Entry Protection

Manual workflow runs can create or update a GitHub Release. To avoid double deployment, the release body includes this marker:

```html
<!-- suno-assistant-release-origin: workflow_dispatch -->
```

When the later `release: published` event sees that marker, the workflow exits without running the deploy a second time.

## Required GitHub Secrets

Common secrets:

- `DEPLOY_SSH_PRIVATE_KEY`
- `DEPLOY_KNOWN_HOSTS`

Target-specific secrets:

| Target | Required secrets |
|--------|------------------|
| `hetzner` | `HETZNER_INVENTORY`, `HETZNER_SECRETS_YAML`, `HETZNER_BASE_URL` |
| `home_worker` | `CREATE_WORKER_INVENTORY`, `CREATE_WORKER_SECRETS_YAML`, `CREATE_WORKER_BASE_URL` |

Recommended contents:

- `*_INVENTORY`: the literal contents of `inventory.local.ini`
- `*_SECRETS_YAML`: the literal YAML contents of `secrets.yml`
- `*_BASE_URL`: the externally reachable URL used by `scripts/release_smoke_check.sh`

## Execution Flow

1. Repair the self-hosted runner workspace before checkout with a regex guard.
2. Check out the repository into `repo/`.
3. Resolve a stable release context via `scripts/github/resolve_release_context.py`.
4. Verify an existing release tag or create and push it when missing.
5. Upsert the GitHub Release body with an in-progress deployment status block.
6. Fail fast when the target's required secrets are not configured.
7. Install `ansible-core` via `apt` when available or `pip --user` as a fallback.
8. Write SSH material, inventory, and `secrets.yml` onto disk.
9. Validate secrets parsing with a local Ansible command before deployment.
10. Run `scripts/redeploy.sh`.
11. Run `scripts/release_smoke_check.sh`.
12. Update the GitHub Release body with `success` or `failure`.

## Troubleshooting

- If the workflow refuses to clean the workspace, inspect the self-hosted runner's `GITHUB_WORKSPACE` path and adjust the regex guard deliberately.
- If Ansible installation falls back to `pip --user`, ensure `$CREATE/.local/bin` is available to later steps.
- If the workflow fails in the secrets pre-flight step, add the missing GitHub Secrets before retrying.
- If `extended` smoke checks fail, confirm your application exposes a version endpoint and that the response contains the deployed ref or version string.

## Follow-Up Customization

The template ships only a skeleton. Before first production use:

- replace the placeholder tasks in `infra/hetzner/`, `infra/home-worker/`, and `infra/site/`
- align inventory host groups with your actual playbooks
- adapt `scripts/release_smoke_check.sh` to your service's health and version endpoints
- tighten or expand the target list if your project has more deployment environments

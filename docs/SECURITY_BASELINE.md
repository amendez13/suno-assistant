# Repository Security Baseline

This template includes a baseline repository-security setup so new projects get secret detection and security guidance immediately after creation.

## Included In The Template

- `.github/workflows/gitleaks.yml` scans the full git history on `push`, `pull_request`, and `workflow_dispatch`.
- `.pre-commit-config.yaml` includes an official `gitleaks` hook so obvious leaks are caught before they are pushed.
- `.github/workflows/ci.yml` continues to run `bandit` and `pip-audit` for application-level and dependency-level checks.

The `gitleaks` workflow installs a pinned upstream binary, verifies its SHA-256 checksum, redacts findings in logs, and writes a redacted SARIF report. The workflow always uploads the SARIF file as an artifact and attempts a best-effort upload to GitHub code scanning where that feature is available for the repository.

## Recommended GitHub Features To Enable

After creating a repository from this template, enable the following GitHub-native features where your repository plan supports them:

1. Secret scanning
2. Push protection
3. CodeQL default setup

These features are distinct:

- `gitleaks` is repository-local scanning that runs in your workflow and pre-commit hooks.
- GitHub secret scanning and push protection detect supported secret types in GitHub-hosted pushes and repository history.
- CodeQL default setup is for code scanning, not secret detection.

GitHub availability changes by repository type and plan, so verify current support in the official docs linked below before relying on a specific feature for a new private or organization-owned repository.

## Local Secret Scanning

Install hooks during bootstrap:

```bash
pre-commit install --install-hooks
```

For direct repository or history scans, install the `gitleaks` CLI separately. On macOS, one common option is:

```bash
brew install gitleaks
```

Scan the current working tree directly with `gitleaks`:

```bash
gitleaks dir . --no-banner --redact=100
```

Scan the full git history:

```bash
gitleaks git . --no-banner --redact=100
```

Generate a local redacted SARIF report:

```bash
gitleaks git . \
  --no-banner \
  --redact=100 \
  --report-format sarif \
  --report-path gitleaks.sarif
```

## Operational Notes

- The pre-commit hook scans staged changes before commit.
- Use the standalone `gitleaks` CLI, not `pre-commit run gitleaks --all-files`, when you want a full working-tree or full-history scan.
- The GitHub Actions workflow scans repository history because leaked secrets often remain reachable in older commits even after a later cleanup.
- If `gitleaks` reports a real secret, treat it as compromised: rotate it, remove it from code, and consider rewriting git history if exposure persisted in committed history.
- If GitHub code scanning is unavailable for the repository, the workflow still preserves the redacted SARIF artifact in the Actions run.

## References

- [Gitleaks repository](https://github.com/gitleaks/gitleaks)
- [GitHub: Enabling secret scanning for your repository](https://docs.github.com/en/code-security/secret-scanning/enabling-secret-scanning-features/enabling-secret-scanning-for-your-repository)
- [GitHub: About push protection](https://docs.github.com/en/code-security/secret-scanning/introduction/about-push-protection)
- [GitHub: About setup types for code scanning](https://docs.github.com/en/code-security/concepts/code-scanning/setup-types)
- [GitHub: Uploading a SARIF file to GitHub](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/integrate-with-existing-tools/uploading-a-sarif-file-to-github)

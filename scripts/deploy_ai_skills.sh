#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
playbook="$repo_root/infra/ai-skills/deploy_ai_skills.yml"

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "ansible-playbook is required to deploy AI skills." >&2
  exit 1
fi

exec ansible-playbook "$playbook" "$@"

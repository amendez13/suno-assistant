#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/redeploy.sh --target <hetzner|home_worker> --deploy-ref <ref> [--inventory <path>] [--secrets-file <path>]
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target=""
deploy_ref=""
inventory_path=""
secrets_path=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      target="${2:-}"
      shift 2
      ;;
    --deploy-ref)
      deploy_ref="${2:-}"
      shift 2
      ;;
    --inventory)
      inventory_path="${2:-}"
      shift 2
      ;;
    --secrets-file)
      secrets_path="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${target}" || -z "${deploy_ref}" ]]; then
  usage >&2
  exit 1
fi

case "${target}" in
  hetzner)
    playbook_path="${repo_root}/infra/site/redeploy.yml"
    default_inventory="${repo_root}/infra/hetzner/inventory.local.ini"
    default_secrets="${repo_root}/infra/hetzner/secrets.yml"
    ;;
  home_worker)
    playbook_path="${repo_root}/infra/home-worker/redeploy.yml"
    default_inventory="${repo_root}/infra/home-worker/inventory.local.ini"
    default_secrets="${repo_root}/infra/home-worker/secrets.yml"
    ;;
  *)
    echo "Unsupported target: ${target}" >&2
    exit 1
    ;;
esac

inventory_path="${inventory_path:-${default_inventory}}"
secrets_path="${secrets_path:-${default_secrets}}"

if [[ ! -f "${playbook_path}" ]]; then
  echo "Missing playbook: ${playbook_path}" >&2
  exit 1
fi

if [[ ! -f "${inventory_path}" ]]; then
  echo "Missing inventory file: ${inventory_path}" >&2
  exit 1
fi

if [[ ! -f "${secrets_path}" ]]; then
  echo "Missing secrets file: ${secrets_path}" >&2
  exit 1
fi

ansible-playbook \
  -i "${inventory_path}" \
  "${playbook_path}" \
  --extra-vars "@${secrets_path}" \
  --extra-vars "deploy_target=${target} deploy_ref=${deploy_ref}"

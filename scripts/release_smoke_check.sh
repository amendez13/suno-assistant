#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/release_smoke_check.sh --base-url <url> --smoke-level <basic|extended> [--expected-ref <ref>]
EOF
}

base_url=""
smoke_level=""
expected_ref=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      base_url="${2:-}"
      shift 2
      ;;
    --smoke-level)
      smoke_level="${2:-}"
      shift 2
      ;;
    --expected-ref)
      expected_ref="${2:-}"
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

if [[ -z "${base_url}" || -z "${smoke_level}" ]]; then
  usage >&2
  exit 1
fi

case "${smoke_level}" in
  basic|extended)
    ;;
  *)
    echo "Unsupported smoke level: ${smoke_level}" >&2
    exit 1
    ;;
esac

curl --fail --silent --show-error --location --max-time 20 "${base_url}" >/dev/null

if [[ "${smoke_level}" == "extended" ]]; then
  version_endpoint="${VERSION_ENDPOINT_PATH:-/version}"
  version_body="$(curl --fail --silent --show-error --location --max-time 20 "${base_url%/}${version_endpoint}")"

  if [[ -n "${expected_ref}" && "${version_body}" != *"${expected_ref}"* ]]; then
    echo "Version endpoint did not include expected ref ${expected_ref}." >&2
    exit 1
  fi
fi

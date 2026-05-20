#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-ghcr.io/amendez13/suno-assistant-ci}"
SHA="$(git rev-parse --short HEAD)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Authenticate first:
#   echo "$GHCR_TOKEN" | docker login ghcr.io -u "amendez13" --password-stdin

BUILDER_NAME="${BUILDER_NAME:-suno-assistant-ci-multiarch}"
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

if ! docker buildx inspect "$BUILDER_NAME" >/dev/null 2>&1; then
  docker buildx create --name "$BUILDER_NAME" --use
else
  docker buildx use "$BUILDER_NAME"
fi

docker buildx inspect --bootstrap >/dev/null

docker buildx build \
  --platform "$PLATFORMS" \
  -f "$SCRIPT_DIR/Dockerfile" \
  -t "$REPO:$SHA" \
  -t "$REPO:latest" \
  --push \
  "$REPO_ROOT"

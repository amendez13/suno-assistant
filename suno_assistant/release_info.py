"""Helpers for surfacing release metadata."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _REPO_ROOT / "VERSION"


def _git_output(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    value = str(result.stdout or "").strip()
    return value or None


def _version_file_value() -> str | None:
    try:
        value = _VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def get_release_info() -> dict[str, Any]:
    """Return release metadata for logs and health endpoints."""
    env_tag = str(os.environ.get("RELEASE_TAG", "")).strip() or None
    env_commit = str(os.environ.get("RELEASE_COMMIT", "")).strip() or None
    env_short_commit = env_commit[:7] if env_commit else None
    if env_tag or env_commit:
        return {
            "tag": env_tag,
            "commit": env_commit,
            "short_commit": env_short_commit,
            "source": "env",
        }

    git_commit = _git_output("rev-parse", "HEAD")
    git_short_commit = _git_output("rev-parse", "--short", "HEAD")
    git_tag = _git_output("describe", "--tags", "--exact-match")
    if git_commit or git_tag:
        return {
            "tag": git_tag,
            "commit": git_commit,
            "short_commit": git_short_commit,
            "source": "git",
        }

    version_tag = _version_file_value()
    if version_tag:
        return {
            "tag": version_tag,
            "commit": None,
            "short_commit": None,
            "source": "version_file",
        }

    return {
        "tag": None,
        "commit": None,
        "short_commit": None,
        "source": "unknown",
    }

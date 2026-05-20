#!/usr/bin/env python3
"""Normalize GitHub release trigger context into stable workflow outputs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

DEFAULT_TARGET = "hetzner"
DEFAULT_SMOKE_LEVEL = "basic"


@dataclass(frozen=True)
class ReleaseContext:
    """Stable deployment inputs shared by manual and release-driven workflows."""

    trigger: str
    release_tag: str
    deploy_ref: str
    target: str
    smoke_level: str
    release_name: str
    release_id: str

    def as_outputs(self) -> dict[str, str]:
        """Render context values for GitHub Actions outputs."""
        return {
            "trigger": self.trigger,
            "release_tag": self.release_tag,
            "deploy_ref": self.deploy_ref,
            "target": self.target,
            "smoke_level": self.smoke_level,
            "release_name": self.release_name,
            "release_id": self.release_id,
        }


def _normalize_text(value: Any) -> str:
    """Trim arbitrary values to a usable string."""
    if value is None:
        return ""
    return str(value).strip()


def _manual_input(name: str, explicit_value: str | None, payload: Mapping[str, Any]) -> str:
    """Read workflow-dispatch inputs from env overrides or the event payload."""
    if explicit_value and explicit_value.strip():
        return explicit_value.strip()
    inputs = payload.get("inputs")
    if isinstance(inputs, Mapping):
        return _normalize_text(inputs.get(name))
    return ""


def load_event_payload(event_path: str | None) -> dict[str, Any]:
    """Load the GitHub Actions event payload when available."""
    if not event_path:
        return {}
    path = Path(event_path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return payload
    raise ValueError("GitHub event payload must be a JSON object.")


def resolve_context(
    *,
    event_name: str,
    payload: Mapping[str, Any],
    github_ref_name: str = "",
    github_sha: str = "",
    manual_ref: str | None = None,
    manual_release_tag: str | None = None,
    manual_target: str | None = None,
    manual_smoke_level: str | None = None,
) -> ReleaseContext:
    """Resolve the deployment context for the supported GitHub trigger types."""
    if event_name == "workflow_dispatch":
        release_tag = _manual_input("release_tag", manual_release_tag, payload)
        if not release_tag:
            raise ValueError("workflow_dispatch requires a release_tag input.")

        deploy_ref = (
            _manual_input("ref", manual_ref, payload) or _normalize_text(github_ref_name) or _normalize_text(github_sha)
        )
        if not deploy_ref:
            raise ValueError("workflow_dispatch requires a deploy ref or GitHub ref context.")

        target = _manual_input("target", manual_target, payload) or DEFAULT_TARGET
        smoke_level = _manual_input("smoke_level", manual_smoke_level, payload) or DEFAULT_SMOKE_LEVEL
        return ReleaseContext(
            trigger="workflow_dispatch",
            release_tag=release_tag,
            deploy_ref=deploy_ref,
            target=target,
            smoke_level=smoke_level,
            release_name=release_tag,
            release_id="",
        )

    if event_name == "release":
        action = _normalize_text(payload.get("action"))
        if action and action != "published":
            raise ValueError(f"Unsupported release action: {action}")

        release_payload = payload.get("release")
        if not isinstance(release_payload, Mapping):
            raise ValueError("release event payload is missing the release object.")

        release_tag = _normalize_text(release_payload.get("tag_name"))
        if not release_tag:
            raise ValueError("release event payload is missing release.tag_name.")

        deploy_ref = release_tag
        release_name = _normalize_text(release_payload.get("name")) or release_tag
        return ReleaseContext(
            trigger="release",
            release_tag=release_tag,
            deploy_ref=deploy_ref,
            target=DEFAULT_TARGET,
            smoke_level=DEFAULT_SMOKE_LEVEL,
            release_name=release_name,
            release_id=_normalize_text(release_payload.get("id")),
        )

    raise ValueError(f"Unsupported GitHub event: {event_name}")


def write_outputs(outputs: Mapping[str, str], output_path: str | None) -> None:
    """Write key-value outputs in the format GitHub Actions expects."""
    lines = [f"{key}={value}" for key, value in outputs.items()]
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return
    print("\n".join(lines))


def main() -> int:
    """Entry point for GitHub Actions."""
    payload = load_event_payload(os.environ.get("GITHUB_EVENT_PATH"))
    context = resolve_context(
        event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
        payload=payload,
        github_ref_name=os.environ.get("GITHUB_REF_NAME", ""),
        github_sha=os.environ.get("GITHUB_SHA", ""),
        manual_ref=os.environ.get("INPUT_REF"),
        manual_release_tag=os.environ.get("INPUT_RELEASE_TAG"),
        manual_target=os.environ.get("INPUT_TARGET"),
        manual_smoke_level=os.environ.get("INPUT_SMOKE_LEVEL"),
    )
    write_outputs(context.as_outputs(), os.environ.get("GITHUB_OUTPUT"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

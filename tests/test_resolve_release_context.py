"""Tests for the release context resolver helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "github" / "resolve_release_context.py"
MODULE_SPEC = importlib.util.spec_from_file_location("resolve_release_context", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
resolve_release_context = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = resolve_release_context
MODULE_SPEC.loader.exec_module(resolve_release_context)


def test_resolve_context_for_manual_dispatch_uses_inputs() -> None:
    """Manual workflow inputs should drive the normalized outputs."""
    context = resolve_release_context.resolve_context(
        event_name="workflow_dispatch",
        payload={
            "inputs": {
                "ref": "release/next",
                "release_tag": "v1.2.3",
                "target": "home_worker",
                "smoke_level": "extended",
            }
        },
        github_ref_name="main",
        github_sha="abc123",
    )

    assert context.trigger == "workflow_dispatch"
    assert context.release_tag == "v1.2.3"
    assert context.deploy_ref == "release/next"
    assert context.target == "home_worker"
    assert context.smoke_level == "extended"


def test_resolve_context_for_manual_dispatch_falls_back_to_defaults() -> None:
    """Manual dispatch should fill in target/smoke defaults when omitted."""
    context = resolve_release_context.resolve_context(
        event_name="workflow_dispatch",
        payload={"inputs": {"release_tag": "v2.0.0"}},
        github_ref_name="main",
    )

    assert context.deploy_ref == "main"
    assert context.target == resolve_release_context.DEFAULT_TARGET
    assert context.smoke_level == resolve_release_context.DEFAULT_SMOKE_LEVEL


def test_resolve_context_for_published_release_uses_release_tag_as_deploy_ref() -> None:
    """Published releases should deploy the published tag, not target_commitish."""
    context = resolve_release_context.resolve_context(
        event_name="release",
        payload={
            "action": "published",
            "release": {
                "id": 123,
                "tag_name": "v3.4.5",
                "target_commitish": "deadbeef",
                "name": "Version 3.4.5",
            },
        },
    )

    assert context.trigger == "release"
    assert context.release_tag == "v3.4.5"
    assert context.deploy_ref == "v3.4.5"
    assert context.release_name == "Version 3.4.5"
    assert context.release_id == "123"
    assert context.target == resolve_release_context.DEFAULT_TARGET
    assert context.smoke_level == resolve_release_context.DEFAULT_SMOKE_LEVEL

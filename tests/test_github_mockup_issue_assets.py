"""Tests for the GitHub mockup asset helper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "ai-skills"
    / "suno-assistant-feature-design"
    / "scripts"
    / "github_mockup_issue_assets.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("github_mockup_issue_assets", MODULE_PATH)
assert MODULE_SPEC is not None
assert MODULE_SPEC.loader is not None
github_mockup_issue_assets = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = github_mockup_issue_assets
MODULE_SPEC.loader.exec_module(github_mockup_issue_assets)


def test_build_target_url_for_issue() -> None:
    """Issue URLs should use the issues path."""
    assert (
        github_mockup_issue_assets.build_target_url("openai/example", 42, None)
        == "https://github.com/openai/example/issues/42"
    )


def test_build_target_url_for_pr() -> None:
    """PR URLs should use the pull path."""
    assert github_mockup_issue_assets.build_target_url("openai/example", None, 7) == "https://github.com/openai/example/pull/7"


def test_parse_selector_line_supports_explicit_slug() -> None:
    """Selector files can provide a stable output slug explicitly."""
    spec = github_mockup_issue_assets.parse_selector_line("hero-card=.hero-card", 1)
    assert spec is not None
    assert spec.slug == "hero-card"
    assert spec.selector == ".hero-card"


def test_parse_selector_line_ignores_comments() -> None:
    """Comment lines should be ignored."""
    assert github_mockup_issue_assets.parse_selector_line("# note", 1) is None


def test_parse_selector_line_derives_slug_when_missing() -> None:
    """Selectors without a slug should still get a stable filename."""
    spec = github_mockup_issue_assets.parse_selector_line('[data-view="main"] .hero-card', 3)
    assert spec is not None
    assert spec.slug == "03-data-view-main-hero"
    assert spec.selector == '[data-view="main"] .hero-card'


def test_render_snippet_includes_selector_metadata() -> None:
    """The generated snippet should map each image to its selector."""
    image = github_mockup_issue_assets.CapturedImage(
        slug="hero-card",
        selector=".hero-card",
        path=Path("artifacts/hero-card.png"),
    )
    rendered = github_mockup_issue_assets.render_snippet(
        [image],
        ["https://github.com/user-attachments/assets/12345678-1234-1234-1234-1234567890ab"],
    )
    assert "## Visual Guide" in rendered
    assert "### `hero-card`" in rendered
    assert "Selector: `.hero-card`" in rendered

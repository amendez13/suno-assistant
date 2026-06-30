"""Tests for Suno create-page fixture extractors."""

import asyncio
from pathlib import Path

import pytest

from suno_assistant.extractors import classify_create_page_html, extract_create_page_state
from suno_assistant.selectors import CREATE_WORKFLOW_SELECTOR_GROUPS

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "suno"


def load_fixture(name: str) -> str:
    """Load one sanitized Suno fixture."""
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_selector_groups_are_named_and_non_empty() -> None:
    """Every selector group should expose named fallback selectors."""
    assert CREATE_WORKFLOW_SELECTOR_GROUPS
    for group in CREATE_WORKFLOW_SELECTOR_GROUPS:
        assert group.name
        assert group.selectors
        assert all(selector for selector in group.selectors)


def test_classifies_unauthenticated_create_page() -> None:
    """Sign-in pages should be blocked before selector-dependent generation work."""
    state = classify_create_page_html(load_fixture("unauthenticated.html"))

    assert state.authenticated is False
    assert state.blocked_reason == "auth_required"
    assert state.ready_for_prompt is False


def test_classifies_ready_create_page_controls() -> None:
    """The ready fixture should expose prompt, mode, and create controls."""
    state = classify_create_page_html(load_fixture("create_ready.html"))

    assert state.authenticated is True
    assert state.prompt_input_visible is True
    assert state.style_input_visible is True
    assert state.lyrics_input_visible is True
    assert state.custom_mode_available is True
    assert state.create_button_visible is True
    assert state.create_button_enabled is True
    assert state.ready_for_prompt is True


def test_classifies_disabled_create_button() -> None:
    """Disabled create controls should not be treated as ready to submit."""
    state = classify_create_page_html(load_fixture("create_disabled.html"))

    assert state.create_button_visible is True
    assert state.create_button_enabled is False
    assert state.ready_for_prompt is False


def test_classifies_generation_in_progress() -> None:
    """In-progress generation state should be explicit."""
    state = classify_create_page_html(load_fixture("generation_in_progress.html"))

    assert state.generation_in_progress is True
    assert state.create_button_enabled is False


def test_extracts_completed_result_cards() -> None:
    """Completed generation fixtures should return visible result metadata."""
    state = classify_create_page_html(load_fixture("generation_completed.html"))

    assert state.authenticated is True
    assert state.diagnostics["results_seen"] == 2
    assert [result.title for result in state.results] == ["Orbit Morning", "Launch Window"]
    assert [result.result_id for result in state.results] == ["song_001", "song_002"]
    assert state.results[0].url == "/song/song_001"


def test_extracts_results_from_bare_song_anchors() -> None:
    """Current Suno markup lists songs as bare /song/<id> anchors; ids/urls are extracted."""
    state = classify_create_page_html(load_fixture("create_with_new_song.html"))

    ids = [result.result_id for result in state.results]
    assert ids == [
        "cccccccc-1111-2222-3333-444444444444",
        "aaaaaaaa-1111-2222-3333-444444444444",
        "bbbbbbbb-1111-2222-3333-444444444444",
    ]
    assert state.results[0].url == "/song/cccccccc-1111-2222-3333-444444444444"
    assert state.diagnostics["results_seen"] == 3


@pytest.mark.parametrize(
    ("fixture_name", "reason"),
    [
        ("quota_unavailable.html", "quota_unavailable"),
        ("policy_rejected.html", "policy_rejected"),
        ("manual_verification.html", "manual_verification_required"),
    ],
)
def test_classifies_blocked_states(fixture_name: str, reason: str) -> None:
    """Known platform blocks should be classified separately from generic failure."""
    state = classify_create_page_html(load_fixture(fixture_name))

    assert state.blocked_reason == reason
    assert state.blocked_message
    assert state.ready_for_prompt is False


def test_ignores_sidebar_upgrade_copy_when_create_is_enabled() -> None:
    """Upgrade marketing copy should not become a quota block by itself."""
    state = classify_create_page_html(load_fixture("create_ready_with_upgrade_copy.html"))

    assert state.authenticated is True
    assert state.blocked_reason is None
    assert state.create_button_enabled is True
    assert state.ready_for_prompt is True


def test_ignores_benign_challenge_scripts_when_no_challenge_frame() -> None:
    """Preloaded turnstile scripts / CDN references must not be a manual-verification block."""
    state = classify_create_page_html(load_fixture("create_ready_with_challenge_scripts.html"))

    assert state.authenticated is True
    assert state.blocked_reason is None
    assert state.create_button_enabled is True
    assert state.ready_for_prompt is True
    assert state.diagnostics["manual_verification_visible"] is False
    assert state.diagnostics["challenge_frame_count"] == 0


def test_ignores_policy_footer_links_when_create_is_enabled() -> None:
    """Footer Privacy/Content/Moderation links must not become a policy block."""
    state = classify_create_page_html(load_fixture("create_ready_with_policy_links.html"))

    assert state.authenticated is True
    assert state.blocked_reason is None
    assert state.create_button_enabled is True
    assert state.ready_for_prompt is True


def test_policy_rejection_requires_an_alert_element() -> None:
    """A real rejection message inside an alert element is classified as policy_rejected."""
    state = classify_create_page_html(load_fixture("policy_rejected.html"))

    assert state.blocked_reason == "policy_rejected"
    assert state.blocked_message


def test_manual_verification_requires_a_real_challenge_frame() -> None:
    """A genuine challenge fixture exposes a counted challenge frame and blocks."""
    state = classify_create_page_html(load_fixture("manual_verification.html"))

    assert state.blocked_reason == "manual_verification_required"
    assert state.diagnostics["manual_verification_visible"] is True
    assert state.diagnostics["challenge_frame_count"] == 1


def test_manual_verification_detects_full_page_interstitial_text() -> None:
    """A frameless full-page interstitial is detected via specific visible text only."""
    html = (
        "<!doctype html><html><body><main>"
        "<h1>Verify you are human</h1>"
        "<p>Please complete the captcha to continue.</p>"
        "</main></body></html>"
    )

    state = classify_create_page_html(html)

    assert state.blocked_reason == "manual_verification_required"
    assert state.diagnostics["challenge_frame_count"] == 0


def test_async_page_extractor_reads_loaded_page_content() -> None:
    """The Playwright-facing extractor should only read the already-loaded page."""

    class FakePage:
        async def content(self) -> str:
            return load_fixture("create_ready.html")

    state = asyncio.run(extract_create_page_state(FakePage()))

    assert state.ready_for_prompt is True

"""Tests for Suno auth adapter helpers."""

from gsv.config import SiteAuthConfig, SiteConfig

from suno_assistant.auth import build_suno_auth_adapter, is_authenticated_create_url, is_manual_auth_url


def test_authenticated_create_url_classifier_accepts_create_surface() -> None:
    """The create page and nested create routes should count as authenticated markers."""
    assert is_authenticated_create_url("https://suno.com/create")
    assert is_authenticated_create_url("https://www.suno.com/create/custom")


def test_authenticated_create_url_classifier_rejects_auth_pages() -> None:
    """Login, auth provider, and unrelated URLs should not count as authenticated."""
    assert not is_authenticated_create_url("https://suno.com/sign-in")
    assert not is_authenticated_create_url("https://accounts.google.com/o/oauth2/v2/auth")
    assert not is_authenticated_create_url("https://example.com/create")


def test_manual_auth_url_classifier_detects_login_and_challenges() -> None:
    """Manual login and verification URLs should be handled by headed challenge policy."""
    assert is_manual_auth_url("https://suno.com/sign-in")
    assert is_manual_auth_url("https://suno.com/checkpoint")
    assert is_manual_auth_url("https://accounts.google.com/o/oauth2/v2/auth")
    assert is_manual_auth_url("https://clerk.suno.com/v1/client")


def test_manual_auth_url_classifier_rejects_authenticated_create_page() -> None:
    """Already-authenticated create pages should not be treated as challenges."""
    assert not is_manual_auth_url("https://suno.com/create")


def test_build_suno_auth_adapter_uses_config_and_suno_predicates() -> None:
    """The adapter should preserve config while using Suno-specific URL classification."""
    site = SiteConfig(
        name="suno",
        allowed_host_globs=["https://suno.com/**"],
        auth=SiteAuthConfig(
            auth_marker_url="https://suno.com/create",
            login_url="https://suno.com/sign-in",
            cookie_consent_selectors=["button:has-text('Accept')"],
        ),
    )

    adapter = build_suno_auth_adapter(site)

    assert adapter.auth_marker_url == "https://suno.com/create"
    assert adapter.login_target_url == "https://suno.com/sign-in"
    assert adapter.cookie_consent_selectors == ("button:has-text('Accept')",)
    assert adapter.allowed_host_globs == ("https://suno.com/**",)
    assert adapter.is_authenticated_url("https://suno.com/create")
    assert adapter.is_challenge_url("https://suno.com/sign-in")

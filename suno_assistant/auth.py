"""Suno authentication adapter helpers."""

from __future__ import annotations

from urllib.parse import urlparse

from gsv.config import SiteConfig
from gsv.session import SiteAuthAdapter

SUNO_CREATE_URL = "https://suno.com/create"
SUNO_HOSTS = frozenset({"suno.com", "www.suno.com"})
AUTH_REQUIRED_MESSAGE = "Suno authentication required; run `python -m suno_assistant.main --headed --login`."

_AUTH_PATH_MARKERS = (
    "auth",
    "login",
    "sign-in",
    "signin",
    "signup",
    "sign-up",
)
_CHALLENGE_MARKERS = (
    "captcha",
    "challenge",
    "checkpoint",
    "mfa",
    "verify",
    "verification",
)
_KNOWN_AUTH_PROVIDER_HOST_PARTS = (
    "accounts.google.",
    "clerk.",
)


def build_suno_auth_adapter(site: SiteConfig) -> SiteAuthAdapter:
    """Build the Suno auth adapter from config plus Suno URL classification."""
    base = SiteAuthAdapter.from_config(site.auth, allowed_host_globs=site.allowed_host_globs)
    return SiteAuthAdapter(
        auth_marker_url=base.auth_marker_url or SUNO_CREATE_URL,
        login_url=base.login_url or base.auth_marker_url or SUNO_CREATE_URL,
        cookie_consent_selectors=base.cookie_consent_selectors,
        variant_trigger_selectors=base.variant_trigger_selectors,
        username_selectors=base.username_selectors,
        password_selectors=base.password_selectors,
        submit_selectors=base.submit_selectors,
        warmup_url=base.warmup_url,
        extra_init_scripts=base.extra_init_scripts,
        allowed_host_globs=base.allowed_host_globs,
        auth_marker_predicate=is_authenticated_create_url,
        challenge_url_predicate=is_manual_auth_url,
    )


def is_authenticated_create_url(url: str) -> bool:
    """Return whether a URL represents the authenticated Suno create surface."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return host in SUNO_HOSTS and (path == "/create" or path.startswith("/create/"))


def is_manual_auth_url(url: str) -> bool:
    """Return whether a URL requires headed manual login or verification."""
    if is_authenticated_create_url(url):
        return False

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    lowered = f"{host}{parsed.path}".casefold()
    if any(marker in lowered for marker in _CHALLENGE_MARKERS):
        return True
    if host in SUNO_HOSTS and any(marker in lowered for marker in _AUTH_PATH_MARKERS):
        return True
    return any(part in host for part in _KNOWN_AUTH_PROVIDER_HOST_PARTS)

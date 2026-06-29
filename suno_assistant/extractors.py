"""Suno create-page extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Literal

BlockedReason = Literal["auth_required", "manual_verification_required", "quota_unavailable", "policy_rejected"]

_PROMPT_MARKERS = ("prompt", "describe", "song")
_STYLE_MARKERS = ("style", "genre", "vibe")
_LYRICS_MARKERS = ("lyrics", "words")
_CREATE_BUTTON_MARKERS = ("create", "generate")
_AUTH_TEXT_MARKERS = ("sign in", "log in", "login")
_CHALLENGE_TEXT_MARKERS = (
    "captcha",
    "verify you are human",
    "verification",
    "manual verification",
    "security check",
    "challenge",
    "turnstile",
    "cf-turnstile",
    "hcaptcha",
    "recaptcha",
    "cloudflare",
)
_QUOTA_TEXT_MARKERS = (
    "not enough credits",
    "not have enough credits",
    "out of credits",
    "quota",
    "subscription required",
    "upgrade to continue",
)
_POLICY_TEXT_MARKERS = ("policy", "moderation", "rejected", "not allowed")
_PROGRESS_TEXT_MARKERS = ("generating", "creating your song", "in progress")


@dataclass(frozen=True)
class SongResultSummary:
    """Visible generated-song metadata from the create page."""

    title: str | None = None
    url: str | None = None
    result_id: str | None = None


@dataclass(frozen=True)
class CreatePageState:
    """Classified Suno create-page state."""

    authenticated: bool
    prompt_input_visible: bool = False
    style_input_visible: bool = False
    lyrics_input_visible: bool = False
    custom_mode_available: bool = False
    create_button_visible: bool = False
    create_button_enabled: bool = False
    generation_in_progress: bool = False
    blocked_reason: BlockedReason | None = None
    blocked_message: str | None = None
    results: list[SongResultSummary] = field(default_factory=list)
    diagnostics: dict[str, str | int | bool] = field(default_factory=dict)

    @property
    def ready_for_prompt(self) -> bool:
        """Return whether the page can accept a prompt and submit."""
        return bool(
            self.authenticated
            and self.prompt_input_visible
            and self.create_button_visible
            and self.create_button_enabled
            and self.blocked_reason is None
        )


@dataclass(frozen=True)
class _Element:
    tag: str
    attrs: dict[str, str]
    text: str

    @property
    def haystack(self) -> str:
        """Return searchable text and attribute values for fixture classification."""
        return " ".join([self.tag, self.text, *self.attrs.values()]).casefold()


class _ElementCollector(HTMLParser):
    """Collect a shallow element list with accumulated visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[_Element] = []
        self._stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack.append({"tag": tag, "attrs": {key: value or "" for key, value in attrs}, "text": []})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append(_Element(tag=tag, attrs={key: value or "" for key, value in attrs}, text=""))

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        current = self._stack.pop()
        if current["tag"] != tag:
            return
        text = " ".join(part.strip() for part in current["text"] if part.strip())
        element = _Element(tag=current["tag"], attrs=current["attrs"], text=text)
        self.elements.append(element)
        if self._stack and text:
            self._stack[-1]["text"].append(text)


async def extract_create_page_state(page: Any) -> CreatePageState:
    """Extract the Suno create-page state from a loaded Playwright page."""
    return classify_create_page_html(await page.content())


def classify_create_page_html(html: str) -> CreatePageState:
    """Classify a Suno create-page HTML snapshot."""
    elements = _parse_elements(html)
    document_text = " ".join(element.text for element in elements).casefold()
    document_haystack = " ".join(element.haystack for element in elements).casefold()
    results = _extract_results(elements)
    prompt_visible = _has_input(elements, _PROMPT_MARKERS)
    style_visible = _has_input(elements, _STYLE_MARKERS)
    lyrics_visible = _has_input(elements, _LYRICS_MARKERS)
    create_button = _find_create_button(elements)
    create_button_visible = create_button is not None
    create_button_enabled = bool(create_button is not None and not _is_disabled(create_button))
    blocked_reason = _blocked_reason(
        document_text=document_text,
        document_haystack=document_haystack,
        prompt_visible=prompt_visible,
        create_button_visible=create_button_visible,
        create_button_enabled=create_button_enabled,
    )
    authenticated = blocked_reason != "auth_required" and bool(
        prompt_visible or style_visible or lyrics_visible or create_button is not None
    )

    return CreatePageState(
        authenticated=authenticated,
        prompt_input_visible=prompt_visible,
        style_input_visible=style_visible,
        lyrics_input_visible=lyrics_visible,
        custom_mode_available=_has_custom_mode(elements),
        create_button_visible=create_button_visible,
        create_button_enabled=create_button_enabled,
        generation_in_progress=any(marker in document_text for marker in _PROGRESS_TEXT_MARKERS),
        blocked_reason=blocked_reason,
        blocked_message=_blocked_message(document_text, blocked_reason),
        results=results,
        diagnostics={
            "elements_seen": len(elements),
            "results_seen": len(results),
            "prompt_input_visible": prompt_visible,
            "create_button_visible": create_button_visible,
            "create_button_enabled": create_button_enabled,
            "manual_verification_visible": _has_challenge_marker(document_haystack),
        },
    )


def _parse_elements(html: str) -> list[_Element]:
    parser = _ElementCollector()
    parser.feed(html)
    return parser.elements


def _has_input(elements: list[_Element], markers: tuple[str, ...]) -> bool:
    input_tags = {"input", "textarea"}
    for element in elements:
        if element.tag not in input_tags and element.attrs.get("contenteditable") != "true":
            continue
        if any(marker in element.haystack for marker in markers):
            return True
    return False


def _has_custom_mode(elements: list[_Element]) -> bool:
    for element in elements:
        if element.tag not in {"button", "input"} and element.attrs.get("role") != "switch":
            continue
        if "custom" in element.haystack:
            return True
    return False


def _find_create_button(elements: list[_Element]) -> _Element | None:
    for element in elements:
        if element.tag != "button" and element.attrs.get("role") != "button":
            continue
        if any(marker in element.haystack for marker in _CREATE_BUTTON_MARKERS):
            return element
    return None


def _is_disabled(element: _Element) -> bool:
    disabled_value = element.attrs.get("disabled")
    aria_disabled = element.attrs.get("aria-disabled", "").casefold()
    return disabled_value is not None or aria_disabled == "true"


def _blocked_reason(
    *,
    document_text: str,
    document_haystack: str,
    prompt_visible: bool,
    create_button_visible: bool,
    create_button_enabled: bool,
) -> BlockedReason | None:
    if _has_challenge_marker(document_haystack):
        return "manual_verification_required"
    if any(marker in document_text for marker in _AUTH_TEXT_MARKERS):
        return "auth_required"
    if _has_quota_marker(document_text) and (not prompt_visible or not create_button_visible or not create_button_enabled):
        return "quota_unavailable"
    if any(marker in document_text for marker in _POLICY_TEXT_MARKERS):
        return "policy_rejected"
    return None


def _has_challenge_marker(document_haystack: str) -> bool:
    return any(marker in document_haystack for marker in _CHALLENGE_TEXT_MARKERS)


def _has_quota_marker(document_text: str) -> bool:
    return any(marker in document_text for marker in _QUOTA_TEXT_MARKERS)


def _blocked_message(document_text: str, reason: BlockedReason | None) -> str | None:
    if reason is None:
        return None
    return {
        "auth_required": "Sign-in or login required.",
        "manual_verification_required": "Manual verification or CAPTCHA challenge detected.",
        "quota_unavailable": "Quota, credits, subscription, or upgrade block detected.",
        "policy_rejected": "Policy, moderation, or prompt rejection block detected.",
    }[reason]


def _extract_results(elements: list[_Element]) -> list[SongResultSummary]:
    results: list[SongResultSummary] = []
    for element in elements:
        test_id = element.attrs.get("data-testid", "").casefold()
        class_name = element.attrs.get("class", "").casefold()
        if "song-card" not in test_id and "result" not in test_id and "song-card" not in class_name:
            continue
        results.append(
            SongResultSummary(
                title=element.attrs.get("data-title") or element.attrs.get("aria-label") or element.text or None,
                url=element.attrs.get("href"),
                result_id=element.attrs.get("data-song-id") or element.attrs.get("data-result-id"),
            )
        )
    return results

"""Centralized Suno create-page selectors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SelectorGroup:
    """Named fallback selectors for one Suno UI concept."""

    name: str
    selectors: tuple[str, ...]


AUTH_REQUIRED_SELECTORS = SelectorGroup(
    name="auth_required",
    selectors=(
        "a[href*='sign-in']",
        "a[href*='login']",
        "button:has-text('Sign in')",
        "button:has-text('Log in')",
    ),
)
PROMPT_INPUT_SELECTORS = SelectorGroup(
    name="prompt_input",
    selectors=(
        "textarea[placeholder*='song' i]",
        "textarea[aria-label*='prompt' i]",
        "textarea[name*='prompt' i]",
        "[contenteditable='true'][aria-label*='song' i]",
    ),
)
STYLE_INPUT_SELECTORS = SelectorGroup(
    name="style_input",
    selectors=(
        "input[placeholder*='style' i]",
        "textarea[placeholder*='style' i]",
        "input[aria-label*='style' i]",
    ),
)
LYRICS_INPUT_SELECTORS = SelectorGroup(
    name="lyrics_input",
    selectors=(
        "textarea[placeholder*='lyrics' i]",
        "textarea[aria-label*='lyrics' i]",
        "textarea[name*='lyrics' i]",
    ),
)
CUSTOM_MODE_SELECTORS = SelectorGroup(
    name="custom_mode",
    selectors=(
        "button[aria-label*='custom' i]",
        "input[type='checkbox'][name*='custom' i]",
        "[role='switch'][aria-label*='custom' i]",
    ),
)
CREATE_BUTTON_SELECTORS = SelectorGroup(
    name="create_button",
    selectors=(
        "button:has-text('Create')",
        "button:has-text('Generate')",
        "button[aria-label*='create' i]",
        "button[aria-label*='generate' i]",
    ),
)
GENERATION_PROGRESS_SELECTORS = SelectorGroup(
    name="generation_progress",
    selectors=(
        "[aria-label*='generating' i]",
        "[data-testid*='generating' i]",
        "text=/generating|creating/i",
    ),
)
RESULT_CARD_SELECTORS = SelectorGroup(
    name="result_card",
    selectors=(
        "[data-testid='song-card']",
        "[data-testid*='result' i]",
        "[class*='song-card' i]",
        "[class*='track-card' i]",
    ),
)
BLOCKED_STATE_SELECTORS = SelectorGroup(
    name="blocked_state",
    selectors=(
        "text=/credits|quota|subscription|upgrade/i",
        "text=/policy|moderation|rejected|not allowed/i",
    ),
)

CREATE_WORKFLOW_SELECTOR_GROUPS = (
    AUTH_REQUIRED_SELECTORS,
    PROMPT_INPUT_SELECTORS,
    STYLE_INPUT_SELECTORS,
    LYRICS_INPUT_SELECTORS,
    CUSTOM_MODE_SELECTORS,
    CREATE_BUTTON_SELECTORS,
    GENERATION_PROGRESS_SELECTORS,
    RESULT_CARD_SELECTORS,
    BLOCKED_STATE_SELECTORS,
)

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
ADVANCED_TAB_SELECTORS = SelectorGroup(
    name="advanced_tab",
    selectors=(
        "button[role='tab'][aria-label='Advanced']",
        "[role='tab']:has-text('Advanced')",
        "button:has-text('Advanced')",
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
        "div[role='button']:has-text('Styles') >> xpath=following::textarea[1]",
        # The Styles control is a textarea labelled by a sibling "Styles" element;
        # its placeholder rotates through genre examples, so match by the label.
        "text=Styles >> xpath=following::textarea[1]",
        "input[placeholder*='style' i]",
        "textarea[placeholder*='style' i]",
        "input[aria-label*='style' i]",
    ),
)
LYRICS_INPUT_SELECTORS = SelectorGroup(
    name="lyrics_input",
    selectors=(
        "textarea[data-testid='lyrics-textarea']",
        "textarea[placeholder='Start writing lyrics...']",
        "textarea[placeholder*='Start writing lyrics' i]",
        "textarea[aria-label='Lyrics']",
        "textarea[placeholder*='lyrics' i]",
        "textarea[aria-label*='lyrics' i]",
        "textarea[name*='lyrics' i]",
        "[contenteditable='true'][aria-label*='lyrics' i]",
        "[contenteditable='true'][data-placeholder*='lyrics' i]",
        "div[role='button']:has-text('Lyrics') >> xpath=following::textarea[1]",
    ),
)
TITLE_INPUT_SELECTORS = SelectorGroup(
    name="title_input",
    selectors=(
        "input[placeholder*='Song Title' i]",
        "input[placeholder*='title' i]",
        "input[aria-label*='title' i]",
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
INSTRUMENTAL_SELECTORS = SelectorGroup(
    name="instrumental",
    selectors=(
        "button[aria-label*='instrumental' i]",
        "button:has-text('Instrumental')",
    ),
)
EXCLUDE_STYLES_INPUT_SELECTORS = SelectorGroup(
    name="exclude_styles_input",
    selectors=(
        "input[placeholder='Exclude styles']",
        "input[placeholder*='exclude' i]",
    ),
)
MORE_OPTIONS_SELECTORS = SelectorGroup(
    name="more_options",
    selectors=(
        "div[role='button']:has-text('More Options')",
        "button:has-text('More Options')",
    ),
)
MALE_VOCAL_SELECTORS = SelectorGroup(
    name="male_vocal",
    selectors=("button:has-text('Male')",),
)
FEMALE_VOCAL_SELECTORS = SelectorGroup(
    name="female_vocal",
    selectors=("button:has-text('Female')",),
)
MANUAL_STYLE_MODE_SELECTORS = SelectorGroup(
    name="manual_style_mode",
    selectors=("button:has-text('Manual')",),
)
AUTO_STYLE_MODE_SELECTORS = SelectorGroup(
    name="auto_style_mode",
    selectors=("button:has-text('Auto')",),
)
WEIRDNESS_SLIDER_SELECTORS = SelectorGroup(
    name="weirdness_slider",
    selectors=("[role='slider'][aria-label='Weirdness']",),
)
STYLE_INFLUENCE_SLIDER_SELECTORS = SelectorGroup(
    name="style_influence_slider",
    selectors=("[role='slider'][aria-label='Style Influence']",),
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
SONG_MORE_MENU_SELECTORS = SelectorGroup(
    name="song_more_menu",
    selectors=(
        "button[aria-label*='more' i]",
        "button[aria-label*='menu' i]",
        "button[title*='more' i]",
        "button:has-text('...')",
        "button:has-text('⋯')",
    ),
)
SONG_DOWNLOAD_ACTION_SELECTORS = SelectorGroup(
    name="song_download_action",
    selectors=(
        "button[aria-label='Download']",
        "[role='menuitem'][aria-label='Download']",
        "button:has-text('Download')",
        "[role='menuitem']:has-text('Download')",
    ),
)
SONG_DOWNLOAD_MP3_SELECTORS = SelectorGroup(
    name="song_download_mp3",
    selectors=(
        "button[aria-label='MP3 Audio']",
        "[role='menuitem'][aria-label='MP3 Audio']",
        "button:has-text('MP3 Audio')",
        "[role='menuitem']:has-text('MP3 Audio')",
    ),
)
SONG_DOWNLOAD_WAV_SELECTORS = SelectorGroup(
    name="song_download_wav",
    selectors=(
        "button[aria-label='WAV Audio']",
        "[role='menuitem'][aria-label='WAV Audio']",
        "button:has-text('WAV Audio')",
        "[role='menuitem']:has-text('WAV Audio')",
    ),
)
SONG_TITLE_EDIT_SELECTORS = SelectorGroup(
    name="song_title_edit",
    selectors=(
        "button[aria-label*='edit' i]",
        "button[title*='edit' i]",
        "button:has-text('Edit')",
        "[role='menuitem']:has-text('Edit')",
        "[role='menuitem']:has-text('Rename')",
        "button:has-text('Rename')",
        "button:has-text('Edit details')",
    ),
)
SONG_TITLE_INPUT_SELECTORS = SelectorGroup(
    name="song_title_input",
    selectors=(
        "input[placeholder*='title' i]",
        "input[aria-label*='title' i]",
        "textarea[placeholder*='title' i]",
        "textarea[aria-label*='title' i]",
        "[contenteditable='true'][aria-label*='title' i]",
        "[contenteditable='true'][data-placeholder*='title' i]",
    ),
)
SONG_TITLE_SAVE_SELECTORS = SelectorGroup(
    name="song_title_save",
    selectors=(
        "button:has-text('Save')",
        "button:has-text('Done')",
        "button:has-text('Update')",
        "button[aria-label*='save' i]",
        "button[aria-label*='done' i]",
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
    ADVANCED_TAB_SELECTORS,
    PROMPT_INPUT_SELECTORS,
    STYLE_INPUT_SELECTORS,
    LYRICS_INPUT_SELECTORS,
    TITLE_INPUT_SELECTORS,
    CUSTOM_MODE_SELECTORS,
    INSTRUMENTAL_SELECTORS,
    EXCLUDE_STYLES_INPUT_SELECTORS,
    MORE_OPTIONS_SELECTORS,
    MALE_VOCAL_SELECTORS,
    FEMALE_VOCAL_SELECTORS,
    MANUAL_STYLE_MODE_SELECTORS,
    AUTO_STYLE_MODE_SELECTORS,
    WEIRDNESS_SLIDER_SELECTORS,
    STYLE_INFLUENCE_SLIDER_SELECTORS,
    CREATE_BUTTON_SELECTORS,
    SONG_MORE_MENU_SELECTORS,
    SONG_DOWNLOAD_ACTION_SELECTORS,
    SONG_DOWNLOAD_MP3_SELECTORS,
    SONG_DOWNLOAD_WAV_SELECTORS,
    SONG_TITLE_EDIT_SELECTORS,
    SONG_TITLE_INPUT_SELECTORS,
    SONG_TITLE_SAVE_SELECTORS,
    GENERATION_PROGRESS_SELECTORS,
    RESULT_CARD_SELECTORS,
    BLOCKED_STATE_SELECTORS,
)

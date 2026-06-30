"""Song request parsing and validation for Suno Assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

MAX_REQUEST_COUNT = 4
SliderValue = int
VocalGender = Literal["male", "female"]
StyleMode = Literal["manual", "auto"]

_KNOWN_FIELDS = frozenset(
    {
        "prompt",
        "title",
        "style",
        "lyrics",
        "instrumental",
        "custom_mode",
        "advanced_mode",
        "exclude_styles",
        "vocal_gender",
        "style_mode",
        "weirdness",
        "style_influence",
        "count",
        "tags",
        "notes",
    }
)
_RESTRICTED_IMITATION_PHRASES = (
    "in the style of ",
    "sounds like ",
    "sound like ",
    "voice of ",
    "vocals like ",
    "sung by ",
)


class SongRequestError(ValueError):
    """Raised when a song request cannot be parsed or validated."""


@dataclass(frozen=True)
class SongRequest:
    """Validated operator instructions for one bounded Suno generation request."""

    prompt: str
    title: str | None = None
    style: str | None = None
    lyrics: str | None = None
    instrumental: bool = False
    custom_mode: bool = False
    advanced_mode: bool = False
    exclude_styles: str | None = None
    vocal_gender: VocalGender | None = None
    style_mode: StyleMode | None = None
    weirdness: SliderValue | None = None
    style_influence: SliderValue | None = None
    count: int = 1
    tags: list[str] = field(default_factory=list)
    notes: str | None = None

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "SongRequest":
        """Build and validate a song request from parsed YAML data."""
        unknown_fields = sorted(set(raw) - _KNOWN_FIELDS)
        if unknown_fields:
            raise SongRequestError(f"Unknown request field(s): {', '.join(unknown_fields)}")

        request = cls(
            prompt=_required_string(raw.get("prompt"), "prompt"),
            title=_optional_string(raw.get("title"), "title"),
            style=_optional_string(raw.get("style"), "style"),
            lyrics=_optional_string(raw.get("lyrics"), "lyrics"),
            instrumental=_optional_bool(raw.get("instrumental"), "instrumental", default=False),
            custom_mode=_optional_bool(raw.get("custom_mode"), "custom_mode", default=False),
            advanced_mode=_optional_bool(raw.get("advanced_mode"), "advanced_mode", default=False),
            exclude_styles=_optional_string(raw.get("exclude_styles"), "exclude_styles"),
            vocal_gender=_optional_choice(raw.get("vocal_gender"), "vocal_gender", ("male", "female")),
            style_mode=_optional_choice(raw.get("style_mode"), "style_mode", ("manual", "auto")),
            weirdness=_optional_slider(raw.get("weirdness"), "weirdness"),
            style_influence=_optional_slider(raw.get("style_influence"), "style_influence"),
            count=_optional_int(raw.get("count"), "count", default=1),
            tags=_optional_string_list(raw.get("tags"), "tags"),
            notes=_optional_string(raw.get("notes"), "notes"),
        )
        request.validate()
        return request

    @classmethod
    def from_prompt(cls, prompt: str) -> "SongRequest":
        """Build a request from a quick one-line CLI prompt."""
        request = cls(prompt=prompt)
        request.validate()
        return request

    def validate(self) -> None:
        """Validate cross-field invariants."""
        if not self.prompt.strip():
            raise SongRequestError("prompt must not be empty")
        if not 1 <= self.count <= MAX_REQUEST_COUNT:
            raise SongRequestError(f"count must be between 1 and {MAX_REQUEST_COUNT}")
        if self.instrumental and self.lyrics:
            raise SongRequestError("lyrics cannot be provided for an instrumental request")
        _reject_restricted_imitation(self.prompt, "prompt")
        if self.style is not None:
            _reject_restricted_imitation(self.style, "style")

    @property
    def uses_advanced_controls(self) -> bool:
        """Return whether this request needs the Suno Advanced tab.

        Suno's current create UI exposes the Styles and Lyrics fields only in the
        Advanced layout (the mode toggle is Simple/Advanced; there is no separate
        "Custom" toggle). Any request that sets a style, lyrics, or custom_mode
        therefore needs the Advanced tab so those controls exist before fill.
        """
        return bool(
            self.advanced_mode
            or self.custom_mode
            or self.style is not None
            or self.lyrics is not None
            or self.exclude_styles is not None
            or self.vocal_gender is not None
            or self.style_mode is not None
            or self.weirdness is not None
            or self.style_influence is not None
        )


def load_song_request(path: str | Path) -> SongRequest:
    """Load and validate a song request YAML file."""
    request_path = Path(path).expanduser()
    try:
        with request_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:
        raise SongRequestError(f"Request file not found: {request_path}") from exc
    except OSError as exc:
        raise SongRequestError(f"Could not read request file {request_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise SongRequestError(f"Could not parse request file {request_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SongRequestError("request file must contain a YAML mapping")
    return SongRequest.from_mapping(raw)


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise SongRequestError(f"{field_name} must be a string")
    if not value.strip():
        raise SongRequestError(f"{field_name} must not be empty")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SongRequestError(f"{field_name} must be a string")
    return value if value.strip() else None


def _optional_bool(value: Any, field_name: str, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SongRequestError(f"{field_name} must be a boolean")
    return value


def _optional_int(value: Any, field_name: str, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise SongRequestError(f"{field_name} must be an integer")
    return int(value)


def _optional_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise SongRequestError(f"{field_name} must be a list of non-empty strings")
    return list(value)


def _optional_choice(value: Any, field_name: str, choices: tuple[str, ...]) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SongRequestError(f"{field_name} must be a string")
    normalized = value.strip().casefold()
    if normalized not in choices:
        raise SongRequestError(f"{field_name} must be one of: {', '.join(choices)}")
    return normalized


def _optional_slider(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SongRequestError(f"{field_name} must be an integer between 0 and 100")
    if not 0 <= value <= 100:
        raise SongRequestError(f"{field_name} must be between 0 and 100")
    return int(value)


def _reject_restricted_imitation(value: str, field_name: str) -> None:
    lowered = value.casefold()
    if any(phrase in lowered for phrase in _RESTRICTED_IMITATION_PHRASES):
        raise SongRequestError(
            f"{field_name} must describe original music without asking to imitate a specific artist or voice"
        )

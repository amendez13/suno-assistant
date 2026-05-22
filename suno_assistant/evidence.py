"""Suno generation evidence payload builders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .extractors import CreatePageState, SongResultSummary
from .requests import SongRequest
from .song_links import GeneratedSongLink
from .song_renames import SongRenameResult


@dataclass(frozen=True)
class RequestIdentity:
    """Stable local identity for one validated song request."""

    request_id: str
    prompt_hash: str


def build_request_identity(request: SongRequest) -> RequestIdentity:
    """Build a stable local request id from normalized request content."""
    payload = {
        "prompt": request.prompt,
        "title": request.title,
        "style": request.style,
        "lyrics": request.lyrics,
        "instrumental": request.instrumental,
        "custom_mode": request.custom_mode,
        "advanced_mode": request.advanced_mode,
        "exclude_styles": request.exclude_styles,
        "vocal_gender": request.vocal_gender,
        "style_mode": request.style_mode,
        "weirdness": request.weirdness,
        "style_influence": request.style_influence,
        "count": request.count,
        "tags": request.tags,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    prompt_hash = hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()
    return RequestIdentity(request_id=digest[:16], prompt_hash=prompt_hash)


def request_loaded_payload(request: SongRequest) -> dict[str, Any]:
    """Build the request_loaded evidence payload."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "title": request.title,
        "prompt": request.prompt,
        "prompt_hash": identity.prompt_hash,
        "prompt_length": len(request.prompt),
        "style": request.style,
        "has_lyrics": request.lyrics is not None,
        "instrumental": request.instrumental,
        "custom_mode": request.custom_mode,
        "advanced_mode": request.advanced_mode,
        "exclude_styles": request.exclude_styles,
        "vocal_gender": request.vocal_gender,
        "style_mode": request.style_mode,
        "weirdness": request.weirdness,
        "style_influence": request.style_influence,
        "count": request.count,
        "tags": list(request.tags),
        "recorded_at": _now_iso(),
    }


def generation_submitted_payload(request: SongRequest, *, attempt: int) -> dict[str, Any]:
    """Build the generation_submitted evidence payload."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "attempt": attempt,
        "submitted_at": _now_iso(),
        "field_summary": {
            "prompt_length": len(request.prompt),
            "has_title": request.title is not None,
            "has_style": request.style is not None,
            "has_lyrics": request.lyrics is not None,
            "instrumental": request.instrumental,
            "custom_mode": request.custom_mode,
            "advanced_mode": request.advanced_mode,
            "has_exclude_styles": request.exclude_styles is not None,
            "vocal_gender": request.vocal_gender,
            "style_mode": request.style_mode,
            "weirdness": request.weirdness,
            "style_influence": request.style_influence,
            "count": request.count,
        },
    }


def generation_blocked_payload(request: SongRequest, *, phase: str, state: CreatePageState) -> dict[str, Any]:
    """Build the generation_blocked evidence payload."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "phase": phase,
        "reason": state.blocked_reason,
        "visible_message": state.blocked_message,
        "page_state": page_state_payload(state),
        "recorded_at": _now_iso(),
    }


def generation_completed_payload(request: SongRequest, *, state: CreatePageState) -> dict[str, Any]:
    """Build the generation_completed evidence payload."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "result_count": len(state.results),
        "results": [song_result_payload(result) for result in state.results],
        "page_state": page_state_payload(state),
        "completed_at": _now_iso(),
    }


def generation_failed_payload(
    request: SongRequest,
    *,
    phase: str,
    error: str,
    state: CreatePageState | None = None,
) -> dict[str, Any]:
    """Build the generation_failed evidence payload."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "phase": phase,
        "error": error,
        "page_state": page_state_payload(state) if state is not None else None,
        "recorded_at": _now_iso(),
    }


def song_links_collected_payload(
    *,
    songs: list[GeneratedSongLink],
    output_path: str,
    source_url: str,
) -> dict[str, Any]:
    """Build the song_links_collected evidence payload."""

    return {
        "source_url": source_url,
        "output_path": output_path,
        "result_count": len(songs),
        "results": [asdict(song) for song in songs],
        "recorded_at": _now_iso(),
    }


def song_links_failed_payload(*, phase: str, error: str, source_url: str) -> dict[str, Any]:
    """Build the song_links_failed evidence payload."""

    return {
        "source_url": source_url,
        "phase": phase,
        "error": error,
        "recorded_at": _now_iso(),
    }


def song_renames_completed_payload(*, results: list[SongRenameResult], output_path: str) -> dict[str, Any]:
    """Build the song_renames_completed evidence payload."""

    return {
        "output_path": output_path,
        "result_count": len(results),
        "results": [asdict(result) for result in results],
        "recorded_at": _now_iso(),
    }


def song_renames_failed_payload(*, phase: str, error: str, results: list[SongRenameResult]) -> dict[str, Any]:
    """Build the song_renames_failed evidence payload."""

    return {
        "phase": phase,
        "error": error,
        "result_count": len(results),
        "results": [asdict(result) for result in results],
        "recorded_at": _now_iso(),
    }


def page_state_payload(state: CreatePageState) -> dict[str, Any]:
    """Build a compact, safe page-state payload."""
    return {
        "authenticated": state.authenticated,
        "prompt_input_visible": state.prompt_input_visible,
        "create_button_visible": state.create_button_visible,
        "create_button_enabled": state.create_button_enabled,
        "generation_in_progress": state.generation_in_progress,
        "blocked_reason": state.blocked_reason,
        "blocked_message": state.blocked_message,
        "result_count": len(state.results),
        "diagnostics": dict(state.diagnostics),
    }


def song_result_payload(result: SongResultSummary) -> dict[str, Any]:
    """Build a result metadata payload without downloading media."""
    return asdict(result)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

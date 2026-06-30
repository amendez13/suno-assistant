"""Suno generation evidence payload builders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .extractors import CreatePageState, SongResultSummary
from .requests import SongRequest
from .song_downloads import SongDownloadFormat, SongDownloadResult
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


def generation_pre_submit_payload(
    request: SongRequest,
    *,
    state: CreatePageState,
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    """Build the generation_pre_submit evidence payload."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "recorded_at": _now_iso(),
        "field_summary": field_summary_payload(request),
        "page_state": page_state_payload(state),
        "diagnostics": dict(diagnostics),
    }


def generation_submitted_payload(
    request: SongRequest,
    *,
    attempt: int,
    pre_submit_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the generation_submitted evidence payload."""
    identity = build_request_identity(request)
    payload = {
        "request_id": identity.request_id,
        "attempt": attempt,
        "submitted_at": _now_iso(),
        "field_summary": field_summary_payload(request),
    }
    if pre_submit_diagnostics is not None:
        payload["pre_submit_diagnostics"] = dict(pre_submit_diagnostics)
    return payload


def create_click_attempted_payload(
    request: SongRequest,
    *,
    phase: str,
    source: str,
    click: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build evidence for a Create click that the automation attempted."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "phase": phase,
        "source": source,
        "click": dict(click or {}),
        "diagnostics": dict(diagnostics or {}),
        "recorded_at": _now_iso(),
    }


def create_click_skipped_payload(
    request: SongRequest,
    *,
    phase: str,
    reason: str,
    state: CreatePageState | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build evidence for a Create click that was intentionally skipped."""
    identity = build_request_identity(request)
    return {
        "request_id": identity.request_id,
        "phase": phase,
        "reason": reason,
        "page_state": page_state_payload(state) if state is not None else None,
        "diagnostics": dict(diagnostics or {}),
        "recorded_at": _now_iso(),
    }


def visit_step_started_payload(*, step_name: str, page: dict[str, Any]) -> dict[str, Any]:
    """Build evidence for the start of a visit-plan step."""
    return {
        "step": step_name,
        "page": dict(page),
        "recorded_at": _now_iso(),
    }


def visit_step_finished_payload(
    *,
    step_name: str,
    outcome: str,
    error: str | None,
    duration_seconds: float,
    page: dict[str, Any],
) -> dict[str, Any]:
    """Build evidence for the end of a visit-plan step."""
    return {
        "step": step_name,
        "outcome": outcome,
        "error": error,
        "duration_seconds": round(max(0.0, duration_seconds), 3),
        "page": dict(page),
        "recorded_at": _now_iso(),
    }


def ui_click_payload(
    *,
    phase: str,
    source: str,
    selector_group: str,
    selector: str | None,
    selector_index: int | None,
    outcome: str,
    click: dict[str, Any] | None,
    page: dict[str, Any],
    error: str | None = None,
) -> dict[str, Any]:
    """Build safe evidence for a semantic UI click target."""
    return {
        "phase": phase,
        "source": source,
        "selector_group": selector_group,
        "selector": selector,
        "selector_index": selector_index,
        "outcome": outcome,
        "error": error,
        "click": dict(click or {}),
        "page": dict(page),
        "recorded_at": _now_iso(),
    }


def field_summary_payload(request: SongRequest) -> dict[str, Any]:
    """Build a compact request-shape payload without full lyrics or media."""
    return {
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


def song_downloads_completed_payload(
    *,
    source_url: str,
    output_dir: str,
    output_path: str,
    requested_formats: list[SongDownloadFormat],
    results: list[SongDownloadResult],
) -> dict[str, Any]:
    """Build the song_downloads_completed evidence payload."""

    return {
        "source_url": source_url,
        "output_dir": output_dir,
        "output_path": output_path,
        "requested_formats": list(requested_formats),
        "result_count": len(results),
        "results": [asdict(result) for result in results],
        "recorded_at": _now_iso(),
    }


def song_downloads_failed_payload(
    *,
    phase: str,
    error: str,
    source_url: str,
    output_dir: str,
    output_path: str,
    requested_formats: list[SongDownloadFormat],
    results: list[SongDownloadResult],
) -> dict[str, Any]:
    """Build the song_downloads_failed evidence payload."""

    return {
        "phase": phase,
        "error": error,
        "source_url": source_url,
        "output_dir": output_dir,
        "output_path": output_path,
        "requested_formats": list(requested_formats),
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

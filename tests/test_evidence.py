"""Tests for Suno evidence payload builders."""

from suno_assistant.evidence import (
    build_request_identity,
    generation_completed_payload,
    generation_submitted_payload,
    request_loaded_payload,
)
from suno_assistant.extractors import CreatePageState, SongResultSummary
from suno_assistant.requests import SongRequest


def test_request_identity_is_stable_for_same_request() -> None:
    """The local request id should be stable for normalized request content."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original synth song about evidence.",
            "style": "bright synth",
            "count": 2,
            "tags": ["test"],
        }
    )

    first = build_request_identity(request)
    second = build_request_identity(request)

    assert first == second
    assert len(first.request_id) == 16
    assert len(first.prompt_hash) == 64


def test_request_loaded_payload_includes_reviewable_request_fields() -> None:
    """Request evidence should be useful without browser replay."""
    request = SongRequest.from_prompt("An original song about local artifacts.")

    payload = request_loaded_payload(request)

    assert payload["request_id"]
    assert payload["prompt"] == "An original song about local artifacts."
    assert payload["prompt_hash"]
    assert payload["count"] == 1
    assert payload["recorded_at"]


def test_generation_submitted_payload_summarizes_fields_without_media() -> None:
    """Submit evidence should identify the request and field shape."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about submit evidence.",
            "style": "folk",
            "lyrics": "Evidence in the chorus",
            "custom_mode": True,
        }
    )

    payload = generation_submitted_payload(request, attempt=3)

    assert payload["attempt"] == 3
    assert payload["request_id"] == build_request_identity(request).request_id
    assert payload["field_summary"]["has_style"] is True
    assert payload["field_summary"]["has_lyrics"] is True
    assert payload["field_summary"]["custom_mode"] is True


def test_generation_completed_payload_keeps_visible_metadata_only() -> None:
    """Completed evidence should store result metadata without downloading files."""
    request = SongRequest.from_prompt("An original song about completed evidence.")
    state = CreatePageState(
        authenticated=True,
        results=[
            SongResultSummary(title="Evidence Song", url="/song/abc", result_id="abc"),
            SongResultSummary(title="No URL Yet", url=None, result_id="def"),
        ],
    )

    payload = generation_completed_payload(request, state=state)

    assert payload["result_count"] == 2
    assert payload["results"][0] == {"title": "Evidence Song", "url": "/song/abc", "result_id": "abc"}
    assert payload["results"][1] == {"title": "No URL Yet", "url": None, "result_id": "def"}
    assert payload["page_state"]["result_count"] == 2

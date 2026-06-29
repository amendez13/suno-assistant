"""Tests for Suno evidence payload builders."""

from suno_assistant.evidence import (
    build_request_identity,
    generation_completed_payload,
    generation_pre_submit_payload,
    generation_submitted_payload,
    request_loaded_payload,
    song_downloads_completed_payload,
)
from suno_assistant.extractors import CreatePageState, SongResultSummary
from suno_assistant.requests import SongRequest
from suno_assistant.song_downloads import SongDownloadResult


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


def test_generation_pre_submit_payload_records_safe_diagnostics() -> None:
    """Pre-submit evidence should capture readiness without storing full lyrics."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about submit diagnostics.",
            "lyrics": "A private verse should not be copied into diagnostics",
            "advanced_mode": True,
        }
    )
    state = CreatePageState(
        authenticated=True, prompt_input_visible=True, create_button_visible=True, create_button_enabled=True
    )

    payload = generation_pre_submit_payload(
        request,
        state=state,
        diagnostics={"seconds_since_request_loaded": 3.2, "url_path": "/create"},
    )

    assert payload["request_id"] == build_request_identity(request).request_id
    assert payload["field_summary"]["has_lyrics"] is True
    assert "lyrics" not in payload["field_summary"]
    assert payload["diagnostics"]["url_path"] == "/create"
    assert payload["page_state"]["create_button_enabled"] is True


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


def test_song_downloads_completed_payload_keeps_result_metadata() -> None:
    """Download evidence should summarize requested formats and local output paths."""

    payload = song_downloads_completed_payload(
        source_url="https://suno.com/playlist/example",
        output_dir="/tmp/audio",
        output_path="/tmp/audio/song-downloads.json",
        requested_formats=["mp3", "wav"],
        results=[
            SongDownloadResult(
                url="https://suno.com/song/song_abc",
                title="Camden, 1892 -v1",
                song_id="song_abc",
                download_format="mp3",
                outcome="downloaded",
                output_path="/tmp/audio/Camden, 1892 -v1.mp3",
                suggested_filename="Camden, 1892 -v1.mp3",
            )
        ],
    )

    assert payload["source_url"] == "https://suno.com/playlist/example"
    assert payload["requested_formats"] == ["mp3", "wav"]
    assert payload["results"][0]["download_format"] == "mp3"
    assert payload["results"][0]["output_path"] == "/tmp/audio/Camden, 1892 -v1.mp3"

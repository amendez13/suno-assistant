"""Tests for generated-song rename plan helpers."""

import json

import pytest

from suno_assistant.song_renames import (
    SongRenameResult,
    load_song_rename_requests,
    parse_song_rename_requests,
    write_song_rename_results_file,
)


def test_parse_song_rename_requests_accepts_object_with_renames() -> None:
    """Rename plans can use the explicit object format."""

    renames = parse_song_rename_requests(
        {
            "renames": [
                {
                    "url": "https://suno.com/song/abc",
                    "title": "Jonathan Edwards -v1-b",
                }
            ]
        }
    )

    assert renames[0].url == "https://suno.com/song/abc"
    assert renames[0].title == "Jonathan Edwards -v1-b"


def test_parse_song_rename_requests_accepts_url_mapping() -> None:
    """Rename plans can use a compact URL-to-title mapping."""

    renames = parse_song_rename_requests({"https://suno.com/song/abc": "Song v1-b"})

    assert renames[0].url == "https://suno.com/song/abc"
    assert renames[0].title == "Song v1-b"


def test_load_song_rename_requests_rejects_empty_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Empty rename plans should fail before opening the browser."""

    path = tmp_path / "renames.json"
    path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least one rename"):
        load_song_rename_requests(path)


def test_write_song_rename_results_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Rename result exports should be reviewable JSON."""

    path = tmp_path / "results.json"
    write_song_rename_results_file(
        path,
        [
            SongRenameResult(
                url="https://suno.com/song/abc",
                requested_title="Song v1-b",
                outcome="renamed",
            )
        ],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["results"][0]["requested_title"] == "Song v1-b"

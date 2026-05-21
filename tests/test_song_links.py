"""Tests for generated-song link extraction and export."""

import json
from pathlib import Path

from suno_assistant.song_links import classify_song_links_html, infer_song_link_format, write_song_links_file

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "suno"


def load_fixture(name: str) -> str:
    """Load one sanitized Suno fixture."""

    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_extracts_song_links_without_treating_upgrade_text_as_blocked() -> None:
    """Collection should ignore generic sidebar upgrade text and keep song links."""

    state = classify_song_links_html(load_fixture("library_with_songs.html"), base_url="https://suno.com")

    assert state.authenticated is True
    assert state.blocked_reason is None
    assert state.diagnostics["songs_seen"] == 3
    assert [song.title for song in state.songs] == [
        "Closet Full of Sunshine",
        "Secondhand Stars",
        "Velvet Market",
    ]
    assert [song.url for song in state.songs] == [
        "https://suno.com/song/song_abc",
        "https://suno.com/song/song_def",
        "https://suno.com/song/song_xyz",
    ]


def test_classifies_unauthenticated_song_links_page() -> None:
    """Sign-in pages should block collection before writing an empty result."""

    state = classify_song_links_html(load_fixture("library_unauthenticated.html"), base_url="https://suno.com")

    assert state.authenticated is False
    assert state.blocked_reason == "auth_required"
    assert state.songs == []


def test_write_song_links_file_defaults_to_json(tmp_path: Path) -> None:
    """JSON exports should include source metadata and generated links."""

    state = classify_song_links_html(load_fixture("library_with_songs.html"), base_url="https://suno.com")
    output_path = tmp_path / "songs.json"

    export = write_song_links_file(output_path, state.songs, source_url="https://suno.com/library")

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert export.count == 3
    assert payload["source_url"] == "https://suno.com/library"
    assert payload["count"] == 3
    assert payload["songs"][0]["title"] == "Closet Full of Sunshine"


def test_write_song_links_file_supports_jsonl_and_markdown(tmp_path: Path) -> None:
    """Operators can choose line-oriented or human-readable output files."""

    state = classify_song_links_html(load_fixture("library_with_songs.html"), base_url="https://suno.com")
    jsonl_path = tmp_path / "songs.jsonl"
    markdown_path = tmp_path / "songs.md"

    write_song_links_file(jsonl_path, state.songs, source_url="https://suno.com/library")
    write_song_links_file(markdown_path, state.songs, source_url="https://suno.com/library")

    assert len(jsonl_path.read_text(encoding="utf-8").strip().splitlines()) == 3
    assert "| Closet Full of Sunshine | https://suno.com/song/song_abc | song_abc |" in markdown_path.read_text(
        encoding="utf-8"
    )


def test_infers_output_format_from_extension() -> None:
    """The CLI can omit --songs-format for common file suffixes."""

    assert infer_song_link_format(Path("songs.json")) == "json"
    assert infer_song_link_format(Path("songs.jsonl")) == "jsonl"
    assert infer_song_link_format(Path("songs.md")) == "markdown"

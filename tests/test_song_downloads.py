"""Tests for generated-song audio download helpers."""

import json
from pathlib import Path

from suno_assistant.song_downloads import (
    SongDownloadResult,
    extract_downloaded_song_id,
    normalize_downloaded_song_results,
    resolve_song_download_formats,
    validate_downloaded_song_file,
    write_song_download_results_file,
)


def test_resolve_song_download_formats_supports_single_and_both() -> None:
    """CLI selections should map to one or more concrete formats."""

    assert resolve_song_download_formats("mp3") == ("mp3",)
    assert resolve_song_download_formats("wav") == ("wav",)
    assert resolve_song_download_formats("both") == ("mp3", "wav")


def test_write_song_download_results_file_serializes_downloads(tmp_path: Path) -> None:
    """Download results should persist output directory, formats, and per-file outcomes."""

    output_path = tmp_path / "downloads.json"
    export = write_song_download_results_file(
        output_path,
        [
            SongDownloadResult(
                url="https://suno.com/song/song_abc",
                title="Camden, 1892 -v1",
                song_id="song_abc",
                download_format="mp3",
                outcome="downloaded",
                output_path=str(tmp_path / "Camden, 1892 -v1.mp3"),
                suggested_filename="Camden, 1892 -v1.mp3",
            )
        ],
        source_url="https://suno.com/playlist/example",
        output_dir=tmp_path / "audio",
        requested_formats=("mp3",),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert export.count == 1
    assert payload["source_url"] == "https://suno.com/playlist/example"
    assert payload["requested_formats"] == ["mp3"]
    assert payload["results"][0]["download_format"] == "mp3"
    assert payload["results"][0]["outcome"] == "downloaded"


def test_normalize_downloaded_song_results_renames_to_title(  # type: ignore[no-untyped-def]
    monkeypatch, tmp_path: Path
) -> None:
    """Successful downloads should be renamed to the visible song title."""

    file_path = tmp_path / "El 3.mp3"
    file_path.write_bytes(b"mp3")
    synced: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "suno_assistant.song_downloads._sync_mp3_title_tag",
        lambda path, title: synced.append((path.name, title)),
    )

    results = normalize_downloaded_song_results(
        [
            SongDownloadResult(
                url="https://suno.com/song/song_abc",
                title="El 4",
                song_id="song_abc",
                download_format="mp3",
                outcome="downloaded",
                output_path=str(file_path),
                suggested_filename="El 3.mp3",
            )
        ]
    )

    assert not file_path.exists()
    assert (tmp_path / "El 4.mp3").exists()
    assert results[0].output_path == str(tmp_path / "El 4.mp3")
    assert synced == [("El 4.mp3", "El 4")]


def test_normalize_downloaded_song_results_adds_song_id_suffix_on_title_collision(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Distinct songs with the same visible title should not overwrite each other."""

    first = tmp_path / "Alpha.mp3"
    second = tmp_path / "Beta.mp3"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    monkeypatch.setattr("suno_assistant.song_downloads._sync_mp3_title_tag", lambda *_args, **_kwargs: None)

    results = normalize_downloaded_song_results(
        [
            SongDownloadResult(
                url="https://suno.com/song/song_one",
                title="Shared Title",
                song_id="song_one",
                download_format="mp3",
                outcome="downloaded",
                output_path=str(first),
                suggested_filename="Alpha.mp3",
            ),
            SongDownloadResult(
                url="https://suno.com/song/song_two",
                title="Shared Title",
                song_id="song_two",
                download_format="mp3",
                outcome="downloaded",
                output_path=str(second),
                suggested_filename="Beta.mp3",
            ),
        ]
    )

    assert (tmp_path / "Shared Title.mp3").exists()
    assert (tmp_path / "Shared Title [song_two].mp3").exists()
    assert results[0].output_path == str(tmp_path / "Shared Title.mp3")
    assert results[1].output_path == str(tmp_path / "Shared Title [song_two].mp3")


def test_extract_downloaded_song_id_reads_embedded_comment(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Embedded Suno ids should be parsed from ffprobe comment metadata."""

    class _Completed:
        def __init__(self, stdout: str) -> None:
            self.stdout = stdout

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"mp3")

    monkeypatch.setattr("suno_assistant.song_downloads.shutil.which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(
        "suno_assistant.song_downloads.subprocess.run",
        lambda *args, **kwargs: _Completed(
            "made with suno; created=2025-10-08T16:20:02.314Z; id=116d34f4-b3d5-48b8-9334-011b1dd1df00\n"
        ),
    )

    assert extract_downloaded_song_id(song_path) == "116d34f4-b3d5-48b8-9334-011b1dd1df00"


def test_validate_downloaded_song_file_reports_id_mismatch(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Downloads should fail validation when the embedded id is not the requested song."""

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"mp3")

    monkeypatch.setattr(
        "suno_assistant.song_downloads.extract_downloaded_song_id",
        lambda path: "3d6790d7-7248-4d7c-91a9-ae649cebcb57",
    )

    valid, actual_id, error = validate_downloaded_song_file(song_path, "116d34f4-b3d5-48b8-9334-011b1dd1df00")

    assert not valid
    assert actual_id == "3d6790d7-7248-4d7c-91a9-ae649cebcb57"
    assert error == (
        "Downloaded file song id mismatch: expected 116d34f4-b3d5-48b8-9334-011b1dd1df00, "
        "got 3d6790d7-7248-4d7c-91a9-ae649cebcb57"
    )

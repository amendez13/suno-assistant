"""Tests for generated-song audio download helpers."""

import json
from pathlib import Path

from suno_assistant.song_downloads import (
    SongDownloadResult,
    _normalize_downloaded_song_result,
    _sanitize_filename_stem,
    _sync_mp3_title_tag,
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


def test_resolve_song_download_formats_rejects_unknown_selection() -> None:
    """Invalid CLI format selections should fail clearly."""

    try:
        resolve_song_download_formats("aac")
    except ValueError as exc:
        assert str(exc) == "download format must be one of: mp3, wav, both"
    else:  # pragma: no cover - defensive assertion branch
        raise AssertionError("expected ValueError")


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


def test_normalize_downloaded_song_result_leaves_non_downloads_and_missing_files(tmp_path: Path) -> None:
    """Normalization should not rewrite failed results or missing files."""

    failed = SongDownloadResult(
        url="https://suno.com/song/song_one",
        download_format="mp3",
        outcome="failed",
        output_path=str(tmp_path / "missing.mp3"),
    )
    missing = SongDownloadResult(
        url="https://suno.com/song/song_two",
        download_format="mp3",
        outcome="downloaded",
        output_path=str(tmp_path / "missing.mp3"),
    )
    nameless = SongDownloadResult(
        url="https://suno.com/song/song_three",
        download_format="wav",
        outcome="downloaded",
    )

    assert _normalize_downloaded_song_result(failed) is failed
    assert _normalize_downloaded_song_result(missing) is missing
    assert _normalize_downloaded_song_result(nameless) is nameless
    assert _sanitize_filename_stem('bad<>:"/\\|?*\x00 name...') == "bad name"
    assert _sanitize_filename_stem("...") == "song"


def test_normalize_downloaded_song_result_keeps_existing_target_and_increments_collision(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Normalization should keep matching names and increment repeated collision suffixes."""

    monkeypatch.setattr("suno_assistant.song_downloads._sync_mp3_title_tag", lambda *_args, **_kwargs: None)

    existing_target = tmp_path / "Same Title.wav"
    existing_target.write_bytes(b"wav")
    kept = _normalize_downloaded_song_result(
        SongDownloadResult(
            url="https://suno.com/song/song_one",
            title="Same Title",
            song_id="song_one",
            download_format="wav",
            outcome="downloaded",
            output_path=str(existing_target),
        )
    )

    current = tmp_path / "Original.mp3"
    current.write_bytes(b"mp3")
    (tmp_path / "Shared Title.mp3").write_bytes(b"first")
    (tmp_path / "Shared Title [song_two].mp3").write_bytes(b"second")
    renamed = _normalize_downloaded_song_result(
        SongDownloadResult(
            url="https://suno.com/song/song_two",
            title="Shared Title",
            song_id="song_two",
            download_format="mp3",
            outcome="downloaded",
            output_path=str(current),
        )
    )

    assert kept.output_path == str(existing_target)
    assert renamed.output_path == str(tmp_path / "Shared Title [song_two-2].mp3")


def test_sync_mp3_title_tag_returns_when_ffmpeg_missing(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Missing ffmpeg should leave the file untouched."""

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"old")
    monkeypatch.setattr("suno_assistant.song_downloads.shutil.which", lambda binary: None)

    _sync_mp3_title_tag(song_path, "New Title")

    assert song_path.read_bytes() == b"old"


def test_sync_mp3_title_tag_updates_file_when_ffmpeg_succeeds(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """MP3 title sync should replace the source file with ffmpeg output."""

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"old")

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        Path(args[-1]).write_bytes(b"new")
        return object()

    monkeypatch.setattr("suno_assistant.song_downloads.shutil.which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr("suno_assistant.song_downloads.subprocess.run", fake_run)

    _sync_mp3_title_tag(song_path, "New Title")

    assert song_path.read_bytes() == b"new"


def test_sync_mp3_title_tag_cleans_temp_file_on_failure(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """ffmpeg failures should leave the original file in place and remove temp output."""

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"old")

    def fake_run(args, **kwargs):  # type: ignore[no-untyped-def]
        Path(args[-1]).write_bytes(b"partial")
        raise OSError("ffmpeg failed")

    monkeypatch.setattr("suno_assistant.song_downloads.shutil.which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr("suno_assistant.song_downloads.subprocess.run", fake_run)

    _sync_mp3_title_tag(song_path, "New Title")

    assert song_path.read_bytes() == b"old"
    assert not list(tmp_path.glob(".title-sync-*"))


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


def test_extract_downloaded_song_id_handles_missing_probe_errors_and_no_match(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Song id extraction should fail closed for missing tools and invalid metadata."""

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"mp3")

    monkeypatch.setattr("suno_assistant.song_downloads.shutil.which", lambda binary: None)
    assert extract_downloaded_song_id(song_path) is None

    monkeypatch.setattr("suno_assistant.song_downloads.shutil.which", lambda binary: f"/usr/bin/{binary}")
    monkeypatch.setattr(
        "suno_assistant.song_downloads.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError())
    )
    assert extract_downloaded_song_id(song_path) is None

    class _Completed:
        stdout = "no embedded id here"

    monkeypatch.setattr("suno_assistant.song_downloads.subprocess.run", lambda *args, **kwargs: _Completed())
    assert extract_downloaded_song_id(song_path) is None


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


def test_validate_downloaded_song_file_reports_missing_and_success(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Validation should handle missing expected ids, missing actual ids, and matches."""

    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"mp3")

    assert validate_downloaded_song_file(song_path, None) == (False, None, "Expected Suno song id missing for validation")

    monkeypatch.setattr("suno_assistant.song_downloads.extract_downloaded_song_id", lambda path: None)
    assert validate_downloaded_song_file(song_path, "song_abc") == (
        False,
        None,
        "Downloaded file is missing an embedded Suno song id",
    )

    monkeypatch.setattr("suno_assistant.song_downloads.extract_downloaded_song_id", lambda path: "song_abc")
    assert validate_downloaded_song_file(song_path, "SONG_ABC") == (True, "song_abc", None)

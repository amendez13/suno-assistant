"""Generated-song audio download helpers and result export."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from dataclasses import replace as dataclass_replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, cast

SongDownloadFormat = Literal["mp3", "wav"]
SongDownloadOutcome = Literal["downloaded", "blocked", "failed"]
_SONG_ID_PATTERN = re.compile(r"\bid=([0-9a-fA-F-]{36})\b")


@dataclass(frozen=True)
class SongDownloadResult:
    """Outcome for one generated-song audio download attempt."""

    url: str
    download_format: SongDownloadFormat
    outcome: SongDownloadOutcome
    title: str | None = None
    song_id: str | None = None
    output_path: str | None = None
    suggested_filename: str | None = None
    verified_song_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class SongDownloadExport:
    """Persisted summary of generated-song audio download attempts."""

    downloaded_at: str
    source_url: str
    output_dir: str
    requested_formats: list[SongDownloadFormat]
    count: int
    results: list[SongDownloadResult]


def resolve_song_download_formats(selection: str) -> tuple[SongDownloadFormat, ...]:
    """Resolve a CLI download-format selection into one or more concrete formats."""

    normalized = selection.strip().casefold()
    if normalized == "both":
        return ("mp3", "wav")
    if normalized in {"mp3", "wav"}:
        return (cast(SongDownloadFormat, normalized),)
    raise ValueError("download format must be one of: mp3, wav, both")


def write_song_download_results_file(
    path: str | Path,
    results: list[SongDownloadResult],
    *,
    source_url: str,
    output_dir: str | Path,
    requested_formats: Iterable[SongDownloadFormat],
) -> SongDownloadExport:
    """Write generated-song audio download results to JSON."""

    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export = SongDownloadExport(
        downloaded_at=datetime.now(timezone.utc).isoformat(),
        source_url=source_url,
        output_dir=str(Path(output_dir).expanduser()),
        requested_formats=list(requested_formats),
        count=len(results),
        results=list(results),
    )
    output_path.write_text(json.dumps(_export_payload(export), indent=2) + "\n", encoding="utf-8")
    return export


def normalize_downloaded_song_results(results: list[SongDownloadResult]) -> list[SongDownloadResult]:
    """Rename downloaded files to title-based names and sync MP3 title tags."""

    normalized: list[SongDownloadResult] = []
    for result in results:
        normalized.append(_normalize_downloaded_song_result(result))
    return normalized


def _normalize_downloaded_song_result(result: SongDownloadResult) -> SongDownloadResult:
    if result.outcome != "downloaded" or not result.output_path:
        return result

    current_path = Path(result.output_path).expanduser()
    if not current_path.exists():
        return result

    desired_path = _resolved_download_target_path(
        current_path=current_path,
        title=result.title,
        song_id=result.song_id,
        download_format=result.download_format,
    )
    if desired_path != current_path:
        desired_path.parent.mkdir(parents=True, exist_ok=True)
        current_path.rename(desired_path)

    if desired_path.suffix.casefold() == ".mp3":
        _sync_mp3_title_tag(desired_path, desired_path.stem)

    return dataclass_replace(result, output_path=str(desired_path))


def _resolved_download_target_path(
    *,
    current_path: Path,
    title: str | None,
    song_id: str | None,
    download_format: SongDownloadFormat,
) -> Path:
    suffix = current_path.suffix or f".{download_format}"
    target_stem = _sanitize_filename_stem(title or current_path.stem)
    candidate = current_path.with_name(f"{target_stem}{suffix}")
    if candidate == current_path:
        return current_path
    if not candidate.exists():
        return candidate

    suffix_id = (song_id or "copy")[:8]
    candidate = current_path.with_name(f"{target_stem} [{suffix_id}]{suffix}")
    attempt = 2
    while candidate.exists() and candidate != current_path:
        candidate = current_path.with_name(f"{target_stem} [{suffix_id}-{attempt}]{suffix}")
        attempt += 1
    return candidate


def _sanitize_filename_stem(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or "song"


def _sync_mp3_title_tag(path: Path, title: str) -> None:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        return

    fd, tmp_name = tempfile.mkstemp(prefix=".title-sync-", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        subprocess.run(
            [
                ffmpeg_path,
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(path),
                "-map",
                "0",
                "-map_metadata",
                "0",
                "-c",
                "copy",
                "-id3v2_version",
                "3",
                "-metadata",
                f"title={title}",
                str(tmp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        tmp_path.replace(path)
    except (OSError, subprocess.SubprocessError):
        if tmp_path.exists():
            tmp_path.unlink()


def extract_downloaded_song_id(path: str | Path) -> str | None:
    """Extract the embedded Suno song id from a downloaded audio file when available."""

    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path is None:
        return None

    try:
        probe = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format_tags=comment",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(Path(path).expanduser()),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    match = _SONG_ID_PATTERN.search(probe.stdout)
    if match is None:
        return None
    return match.group(1).lower()


def validate_downloaded_song_file(path: str | Path, expected_song_id: str | None) -> tuple[bool, str | None, str | None]:
    """Return whether a downloaded file embeds the expected Suno song id."""

    if not expected_song_id:
        return False, None, "Expected Suno song id missing for validation"

    actual_song_id = extract_downloaded_song_id(path)
    if actual_song_id is None:
        return False, None, "Downloaded file is missing an embedded Suno song id"
    if actual_song_id != expected_song_id.casefold():
        return False, actual_song_id, f"Downloaded file song id mismatch: expected {expected_song_id}, got {actual_song_id}"
    return True, actual_song_id, None


def _export_payload(export: SongDownloadExport) -> dict[str, Any]:
    return {
        "downloaded_at": export.downloaded_at,
        "source_url": export.source_url,
        "output_dir": export.output_dir,
        "requested_formats": list(export.requested_formats),
        "count": export.count,
        "results": [asdict(result) for result in export.results],
    }

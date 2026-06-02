"""Generated-song title rename request and result helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

SongRenameOutcome = Literal["renamed", "failed"]


@dataclass(frozen=True)
class SongRenameRequest:
    """One generated-song title rename request."""

    url: str
    title: str


@dataclass(frozen=True)
class SongRenameResult:
    """Outcome for one generated-song title rename attempt."""

    url: str
    requested_title: str
    outcome: SongRenameOutcome
    error: str | None = None


@dataclass(frozen=True)
class SongRenameExport:
    """Persisted summary of generated-song rename attempts."""

    renamed_at: str
    count: int
    results: list[SongRenameResult]


def load_song_rename_requests(path: str | Path) -> list[SongRenameRequest]:
    """Load generated-song rename requests from JSON.

    Accepted formats:

    - `{"renames": [{"url": "...", "title": "..."}]}`
    - `[{"url": "...", "title": "..."}]`
    - `{"https://suno.com/song/...": "New Title"}`
    """

    input_path = Path(path).expanduser()
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    return parse_song_rename_requests(raw)


def parse_song_rename_requests(raw: Any) -> list[SongRenameRequest]:
    """Parse generated-song rename requests from a decoded JSON value."""

    if isinstance(raw, dict) and "renames" in raw:
        raw = raw["renames"]
    elif isinstance(raw, dict):
        raw = [{"url": url, "title": title} for url, title in raw.items()]

    if not isinstance(raw, list):
        raise ValueError("song rename plan must be a list, a mapping, or an object with a 'renames' list")

    requests = [_parse_song_rename_request(item, index=index) for index, item in enumerate(raw)]
    if not requests:
        raise ValueError("song rename plan must contain at least one rename")
    return requests


def write_song_rename_results_file(path: str | Path, results: list[SongRenameResult]) -> SongRenameExport:
    """Write generated-song rename results to JSON."""

    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export = SongRenameExport(
        renamed_at=datetime.now(timezone.utc).isoformat(),
        count=len(results),
        results=list(results),
    )
    output_path.write_text(json.dumps(_export_payload(export), indent=2) + "\n", encoding="utf-8")
    return export


def _parse_song_rename_request(item: Any, *, index: int) -> SongRenameRequest:
    if not isinstance(item, dict):
        raise ValueError(f"song rename entry {index} must be an object")
    url = _required_string(item.get("url"), f"song rename entry {index} url")
    title = _required_string(item.get("title"), f"song rename entry {index} title")
    return SongRenameRequest(url=url, title=title)


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _export_payload(export: SongRenameExport) -> dict[str, Any]:
    return {
        "renamed_at": export.renamed_at,
        "count": export.count,
        "results": [asdict(result) for result in export.results],
    }

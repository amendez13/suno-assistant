"""Generated-song link extraction and file export helpers."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urljoin, urlparse

SongLinkFormat = Literal["json", "jsonl", "markdown"]

_AUTH_TEXT_MARKERS = ("sign in", "log in", "login")
_SONG_HREF_MARKERS = ("/song/", "/songs/")


@dataclass(frozen=True)
class GeneratedSongLink:
    """Reviewable generated-song metadata without downloading audio."""

    title: str | None
    url: str
    song_id: str | None = None


@dataclass(frozen=True)
class SongLinksPageState:
    """Classified state for pages that may contain generated-song links."""

    authenticated: bool
    songs: list[GeneratedSongLink] = field(default_factory=list)
    blocked_reason: Literal["auth_required"] | None = None
    diagnostics: dict[str, int | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class SongLinksExport:
    """Metadata for one generated-song link export file."""

    source_url: str
    collected_at: str
    count: int
    songs: list[GeneratedSongLink]


@dataclass(frozen=True)
class _Element:
    tag: str
    attrs: dict[str, str]
    text: str

    @property
    def haystack(self) -> str:
        """Return searchable text and attribute values."""
        return " ".join([self.tag, self.text, *self.attrs.values()]).casefold()


class _ElementCollector(HTMLParser):
    """Collect elements with shallow accumulated visible text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[_Element] = []
        self._stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack.append({"tag": tag, "attrs": {key: value or "" for key, value in attrs}, "text": []})

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        current = self._stack.pop()
        if current["tag"] != tag:
            return
        text = _clean_text(" ".join(part.strip() for part in current["text"] if part.strip()))
        element = _Element(tag=current["tag"], attrs=current["attrs"], text=text)
        self.elements.append(element)
        if self._stack and text:
            self._stack[-1]["text"].append(text)


async def extract_song_links_page_state(page: Any, *, base_url: str = "https://suno.com") -> SongLinksPageState:
    """Extract generated-song links from the currently loaded Playwright page."""

    return classify_song_links_html(await page.content(), base_url=base_url)


def classify_song_links_html(html: str, *, base_url: str = "https://suno.com") -> SongLinksPageState:
    """Classify an HTML snapshot and extract visible generated-song links."""

    elements = _parse_elements(html)
    document_text = " ".join(element.text for element in elements).casefold()
    songs = _extract_song_links(elements, base_url=base_url)
    auth_required = not songs and any(marker in document_text for marker in _AUTH_TEXT_MARKERS)
    return SongLinksPageState(
        authenticated=not auth_required,
        songs=songs,
        blocked_reason="auth_required" if auth_required else None,
        diagnostics={
            "elements_seen": len(elements),
            "songs_seen": len(songs),
            "auth_text_seen": any(marker in document_text for marker in _AUTH_TEXT_MARKERS),
        },
    )


def write_song_links_file(
    path: str | Path,
    songs: list[GeneratedSongLink],
    *,
    source_url: str,
    output_format: SongLinkFormat | None = None,
) -> SongLinksExport:
    """Write generated-song links to disk in JSON, JSONL, or Markdown."""

    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    export = SongLinksExport(
        source_url=source_url,
        collected_at=datetime.now(timezone.utc).isoformat(),
        count=len(songs),
        songs=list(songs),
    )
    format_name = output_format or infer_song_link_format(output_path)
    if format_name == "json":
        output_path.write_text(json.dumps(_export_payload(export), indent=2) + "\n", encoding="utf-8")
    elif format_name == "jsonl":
        output_path.write_text(_jsonl_payload(export), encoding="utf-8")
    elif format_name == "markdown":
        output_path.write_text(_markdown_payload(export), encoding="utf-8")
    else:
        raise ValueError(f"Unsupported song link output format: {format_name}")
    return export


def infer_song_link_format(path: str | Path) -> SongLinkFormat:
    """Infer an output format from the file extension."""

    suffix = Path(path).suffix.casefold()
    if suffix == ".jsonl":
        return "jsonl"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    return "json"


def _parse_elements(html: str) -> list[_Element]:
    parser = _ElementCollector()
    parser.feed(html)
    return parser.elements


def _extract_song_links(elements: list[_Element], *, base_url: str) -> list[GeneratedSongLink]:
    songs: list[GeneratedSongLink] = []
    seen: set[str] = set()
    for element in elements:
        song = _song_from_element(element, base_url=base_url)
        if song is None:
            continue
        key = song.url or song.song_id or song.title or ""
        if not key or key in seen:
            continue
        seen.add(key)
        songs.append(song)
    return songs


def _song_from_element(element: _Element, *, base_url: str) -> GeneratedSongLink | None:
    href = element.attrs.get("href")
    if _is_comment_href(href):
        return None
    song_id = element.attrs.get("data-song-id") or element.attrs.get("data-result-id") or _song_id_from_href(href)
    looks_like_song_card = _looks_like_song_card(element)
    looks_like_song_href = bool(href and any(marker in href for marker in _SONG_HREF_MARKERS))
    if not looks_like_song_card and not looks_like_song_href and song_id is None:
        return None
    url = _song_url(href=href, song_id=song_id, base_url=base_url)
    if url is None:
        return None
    return GeneratedSongLink(
        title=_song_title(element),
        url=url,
        song_id=song_id,
    )


def _looks_like_song_card(element: _Element) -> bool:
    test_id = element.attrs.get("data-testid", "").casefold()
    class_name = element.attrs.get("class", "").casefold()
    return "song-card" in test_id or "song-card" in class_name or "track-card" in class_name or "song-row" in class_name


def _song_url(*, href: str | None, song_id: str | None, base_url: str) -> str | None:
    if href and any(marker in href for marker in _SONG_HREF_MARKERS):
        parsed = urlparse(urljoin(base_url, href))
        return parsed._replace(query="", fragment="").geturl()
    if song_id:
        return urljoin(base_url, f"/song/{song_id}")
    return None


def _song_title(element: _Element) -> str | None:
    title = (
        element.attrs.get("data-title")
        or element.attrs.get("title")
        or element.attrs.get("aria-label")
        or element.text
        or None
    )
    return _clean_text(title) if title else None


def _song_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    parsed = urlparse(href)
    parts = [part for part in parsed.path.rstrip("/").split("/") if part]
    if not parts:
        return None
    if parts[-2:-1] in (["song"], ["songs"]):
        return parts[-1]
    return None


def _is_comment_href(href: str | None) -> bool:
    if not href:
        return False
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    return any(value.casefold() == "true" for value in query.get("show_comments", []))


def _clean_text(value: str) -> str:
    return " ".join(value.split()).strip()


def _export_payload(export: SongLinksExport) -> dict[str, Any]:
    return {
        "source_url": export.source_url,
        "collected_at": export.collected_at,
        "count": export.count,
        "songs": [asdict(song) for song in export.songs],
    }


def _jsonl_payload(export: SongLinksExport) -> str:
    rows = []
    for song in export.songs:
        payload = asdict(song)
        payload["source_url"] = export.source_url
        payload["collected_at"] = export.collected_at
        rows.append(json.dumps(payload, sort_keys=True))
    return "\n".join(rows) + ("\n" if rows else "")


def _markdown_payload(export: SongLinksExport) -> str:
    lines = [
        "# Suno Generated Song Links",
        "",
        f"- Source: {export.source_url}",
        f"- Collected at: {export.collected_at}",
        f"- Count: {export.count}",
        "",
        "| Title | URL | Song ID |",
        "| --- | --- | --- |",
    ]
    for song in export.songs:
        lines.append(f"| {_markdown_cell(song.title)} | {_markdown_cell(song.url)} | {_markdown_cell(song.song_id)} |")
    return "\n".join(lines) + "\n"


def _markdown_cell(value: str | None) -> str:
    return (value or "").replace("|", "\\|")

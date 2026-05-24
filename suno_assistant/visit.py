"""Suno visit plans."""

from __future__ import annotations

from pathlib import Path

from gsv.apps import register_app
from gsv.visit import VisitContext, VisitPlan
from gsv.visit.steps import Navigate

from .requests import SongRequest
from .song_downloads import SongDownloadFormat
from .song_links import SongLinkFormat
from .song_renames import SongRenameRequest
from .steps import (
    CollectGeneratedSongLinks,
    DownloadGeneratedSongs,
    FillSunoRequest,
    RenameGeneratedSongs,
    SelectAdvancedMode,
    SubmitGeneration,
    VerifyCreatePageFillable,
    VerifyCreatePageReady,
    WaitForGenerationResult,
    classify_generation_outcome,
    classify_song_collection_outcome,
    classify_song_download_outcome,
    classify_song_rename_outcome,
)

SUNO_CREATE_URL = "https://suno.com/create"
SUNO_LIBRARY_URL = "https://suno.com/library"


def build_plan(
    ctx: VisitContext | None = None,
    *,
    song_request: SongRequest | None = None,
    fill_only: bool = False,
) -> VisitPlan:
    """Build the first bounded Suno plan."""
    del ctx
    steps = [
        Navigate(
            url=SUNO_CREATE_URL,
            name="navigate_create_page",
        )
    ]
    if song_request is not None:
        if song_request.uses_advanced_controls:
            steps.append(SelectAdvancedMode(song_request))
        verify_step = VerifyCreatePageFillable(song_request) if fill_only else VerifyCreatePageReady(song_request)
        steps.extend([verify_step, FillSunoRequest(song_request)])
        if not fill_only:
            steps.extend([SubmitGeneration(song_request), WaitForGenerationResult(song_request)])
    return VisitPlan(
        steps=steps,
        outcome_classifier=classify_generation_outcome if song_request is not None else None,
    )


def build_song_collection_plan(
    *,
    output_path: Path,
    output_format: SongLinkFormat | None = None,
    source_url: str = SUNO_LIBRARY_URL,
) -> VisitPlan:
    """Build a bounded plan that exports visible generated-song links."""

    return VisitPlan(
        steps=[
            Navigate(
                url=source_url,
                name="navigate_song_links_source",
            ),
            CollectGeneratedSongLinks(
                output_path=output_path,
                output_format=output_format,
                source_url=source_url,
            ),
        ],
        outcome_classifier=classify_song_collection_outcome,
    )


def build_song_rename_plan(
    *,
    renames: list[SongRenameRequest],
    output_path: Path,
) -> VisitPlan:
    """Build a bounded plan that renames generated songs."""

    return VisitPlan(
        steps=[
            RenameGeneratedSongs(
                renames=renames,
                output_path=output_path,
            ),
        ],
        outcome_classifier=classify_song_rename_outcome,
    )


def build_song_download_plan(
    *,
    source_url: str,
    output_dir: Path,
    output_path: Path,
    download_formats: tuple[SongDownloadFormat, ...],
) -> VisitPlan:
    """Build a bounded plan that downloads generated-song audio files."""

    return VisitPlan(
        steps=[
            Navigate(
                url=source_url,
                name="navigate_song_download_source",
            ),
            DownloadGeneratedSongs(
                source_url=source_url,
                output_dir=output_dir,
                output_path=output_path,
                download_formats=download_formats,
            ),
        ],
        outcome_classifier=classify_song_download_outcome,
    )


register_app("suno", build_plan)

__all__ = [
    "SUNO_CREATE_URL",
    "SUNO_LIBRARY_URL",
    "build_plan",
    "build_song_collection_plan",
    "build_song_download_plan",
    "build_song_rename_plan",
]

"""Suno visit plans."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gsv.apps import register_app
from gsv.visit import VisitContext, VisitPlan
from gsv.visit.plan import StepResult
from gsv.visit.steps import Navigate

from .evidence import visit_step_finished_payload, visit_step_started_payload
from .requests import SongRequest
from .song_downloads import SongDownloadFormat
from .song_links import SongLinkFormat
from .song_renames import SongRenameRequest
from .steps import (
    CollectGeneratedSongLinks,
    DownloadGeneratedSongs,
    FillSunoRequest,
    PreSubmitInspection,
    RenameGeneratedSongs,
    SelectAdvancedMode,
    SubmitGeneration,
    VerifyCreatePageFillable,
    VerifyCreatePageReady,
    WaitForGenerationResult,
    _page_ref_payload,
    classify_generation_outcome,
    classify_song_collection_outcome,
    classify_song_download_outcome,
    classify_song_rename_outcome,
)

SUNO_CREATE_URL = "https://suno.com/create"
SUNO_LIBRARY_URL = "https://suno.com/library"


@dataclass
class ObservedStep:
    """Wrap a visit step with safe start/finish evidence."""

    step: Any

    def __post_init__(self) -> None:
        self.name = getattr(self.step, "name", self.step.__class__.__name__)
        self.content_marker = getattr(self.step, "content_marker", None)
        self.skip_runner_burst_tick = getattr(self.step, "skip_runner_burst_tick", False)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.step, name)

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Run the wrapped step and emit safe lifecycle evidence."""
        started = time.monotonic()
        await ctx.sink.write(
            "visit_step_started",
            visit_step_started_payload(step_name=self.name, page=_page_ref_payload(ctx.page)),
        )
        try:
            result = await self.step.execute(ctx)
        except Exception as exc:
            await ctx.sink.write(
                "visit_step_finished",
                visit_step_finished_payload(
                    step_name=self.name,
                    outcome="fail",
                    error=str(exc),
                    duration_seconds=time.monotonic() - started,
                    page=_page_ref_payload(ctx.page),
                ),
            )
            raise
        await ctx.sink.write(
            "visit_step_finished",
            visit_step_finished_payload(
                step_name=self.name,
                outcome=result.outcome,
                error=result.error,
                duration_seconds=time.monotonic() - started,
                page=_page_ref_payload(ctx.page),
            ),
        )
        return result


def build_plan(
    ctx: VisitContext | None = None,
    *,
    song_request: SongRequest | None = None,
    fill_only: bool = False,
    confirm_submit: bool = False,
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
        if confirm_submit:
            steps.append(PreSubmitInspection(song_request))
        elif not fill_only:
            steps.extend([SubmitGeneration(song_request), WaitForGenerationResult(song_request)])
    return VisitPlan(
        steps=_observed_steps(steps),
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
        steps=_observed_steps(
            [
                Navigate(
                    url=source_url,
                    name="navigate_song_links_source",
                ),
                CollectGeneratedSongLinks(
                    output_path=output_path,
                    output_format=output_format,
                    source_url=source_url,
                ),
            ]
        ),
        outcome_classifier=classify_song_collection_outcome,
    )


def build_song_rename_plan(
    *,
    renames: list[SongRenameRequest],
    output_path: Path,
) -> VisitPlan:
    """Build a bounded plan that renames generated songs."""

    return VisitPlan(
        steps=_observed_steps(
            [
                RenameGeneratedSongs(
                    renames=renames,
                    output_path=output_path,
                ),
            ]
        ),
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
        steps=_observed_steps(
            [
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
            ]
        ),
        outcome_classifier=classify_song_download_outcome,
    )


def _observed_steps(steps: list[Any]) -> list[ObservedStep]:
    return [ObservedStep(step) for step in steps]


register_app("suno", build_plan)

__all__ = [
    "SUNO_CREATE_URL",
    "SUNO_LIBRARY_URL",
    "build_plan",
    "build_song_collection_plan",
    "build_song_download_plan",
    "build_song_rename_plan",
]

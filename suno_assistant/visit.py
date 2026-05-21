"""Suno visit plans."""

from __future__ import annotations

from gsv.apps import register_app
from gsv.visit import VisitContext, VisitPlan
from gsv.visit.steps import Navigate

from .requests import SongRequest
from .steps import (
    FillSunoRequest,
    SubmitGeneration,
    VerifyCreatePageFillable,
    VerifyCreatePageReady,
    WaitForGenerationResult,
    classify_generation_outcome,
)

SUNO_CREATE_URL = "https://suno.com/create"


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
        verify_step = VerifyCreatePageFillable(song_request) if fill_only else VerifyCreatePageReady(song_request)
        steps.extend([verify_step, FillSunoRequest(song_request)])
        if not fill_only:
            steps.extend([SubmitGeneration(song_request), WaitForGenerationResult(song_request)])
    return VisitPlan(
        steps=steps,
        outcome_classifier=classify_generation_outcome if song_request is not None else None,
    )


register_app("suno", build_plan)

__all__ = ["SUNO_CREATE_URL", "build_plan"]

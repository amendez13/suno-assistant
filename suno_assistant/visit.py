"""Suno visit plans."""

from __future__ import annotations

from gsv.apps import register_app
from gsv.visit import VisitContext, VisitPlan
from gsv.visit.steps import Navigate

from .requests import SongRequest

SUNO_CREATE_URL = "https://suno.com/create"


def build_plan(ctx: VisitContext | None = None, *, song_request: SongRequest | None = None) -> VisitPlan:
    """Build the first bounded Suno plan."""
    del ctx
    del song_request
    return VisitPlan(
        steps=[
            Navigate(
                url=SUNO_CREATE_URL,
                name="navigate_create_page",
            )
        ]
    )


register_app("suno", build_plan)

__all__ = ["SUNO_CREATE_URL", "build_plan"]

"""Suno-specific visit steps for bounded generation."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from gsv.visit import VisitContext
from gsv.visit.plan import StepResult, VisitOutcome

from .evidence import (
    generation_blocked_payload,
    generation_completed_payload,
    generation_failed_payload,
    generation_submitted_payload,
    request_loaded_payload,
)
from .extractors import CreatePageState, extract_create_page_state
from .requests import SongRequest
from .selectors import (
    CREATE_BUTTON_SELECTORS,
    CUSTOM_MODE_SELECTORS,
    LYRICS_INPUT_SELECTORS,
    PROMPT_INPUT_SELECTORS,
    STYLE_INPUT_SELECTORS,
)


@dataclass
class VerifyCreatePageReady:
    """Verify the authenticated create page can accept a generation request."""

    request: SongRequest
    name: str = "verify_create_page_ready"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Extract and validate the current create-page state."""
        state = await extract_create_page_state(ctx.page)
        ctx.extracted["suno_create_state"] = state
        if state.blocked_reason is not None:
            _increment_blocked_counters(ctx, state)
            await ctx.sink.write("generation_blocked", generation_blocked_payload(self.request, phase=self.name, state=state))
            return StepResult(name=self.name, outcome="fail", error=f"blocked:{state.blocked_reason}", extracted=state)
        if not state.prompt_input_visible:
            return StepResult(name=self.name, outcome="fail", error="Prompt input is not visible", extracted=state)
        if not state.create_button_visible:
            return StepResult(name=self.name, outcome="fail", error="Create button is not visible", extracted=state)
        if not state.create_button_enabled:
            return StepResult(name=self.name, outcome="fail", error="Create button is disabled", extracted=state)
        return StepResult(name=self.name, outcome="ok", extracted=state)


@dataclass
class FillSunoRequest:
    """Fill supported Suno create-page fields from a validated request."""

    request: SongRequest
    name: str = "fill_suno_request"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Fill the prompt and supported optional fields."""
        if self.request.custom_mode:
            await _click_optional(ctx.page, CUSTOM_MODE_SELECTORS.selectors)
        if not await _fill_first_available(ctx.page, PROMPT_INPUT_SELECTORS.selectors, self.request.prompt):
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Prompt input selector not found"),
            )
            return StepResult(name=self.name, outcome="fail", error="Prompt input selector not found")
        if self.request.style is not None:
            filled_style = await _fill_first_available(ctx.page, STYLE_INPUT_SELECTORS.selectors, self.request.style)
            if not filled_style:
                await ctx.sink.write(
                    "generation_failed",
                    generation_failed_payload(self.request, phase=self.name, error="Style input selector not found"),
                )
                return StepResult(name=self.name, outcome="fail", error="Style input selector not found")
        if self.request.lyrics is not None:
            filled_lyrics = await _fill_first_available(ctx.page, LYRICS_INPUT_SELECTORS.selectors, self.request.lyrics)
            if not filled_lyrics:
                await ctx.sink.write(
                    "generation_failed",
                    generation_failed_payload(self.request, phase=self.name, error="Lyrics input selector not found"),
                )
                return StepResult(name=self.name, outcome="fail", error="Lyrics input selector not found")
        ctx.increment("suno.requests_loaded")
        ctx.increment("suno.generations_requested", self.request.count)
        await ctx.sink.write("request_loaded", request_loaded_payload(self.request))
        return StepResult(
            name=self.name,
            outcome="ok",
            extracted={
                "prompt_length": len(self.request.prompt),
                "has_style": self.request.style is not None,
                "has_lyrics": self.request.lyrics is not None,
                "custom_mode": self.request.custom_mode,
                "count": self.request.count,
            },
        )


@dataclass
class SubmitGeneration:
    """Submit one bounded generation request."""

    request: SongRequest
    name: str = "submit_generation"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Click the first available create/generate button."""
        clicked = await _click_first_available(ctx.page, CREATE_BUTTON_SELECTORS.selectors)
        if not clicked:
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Create button selector not found"),
            )
            return StepResult(name=self.name, outcome="fail", error="Create button selector not found")
        ctx.increment("suno.requests_submitted")
        attempt = ctx.counters.get("suno.requests_submitted", 1)
        await ctx.sink.write("generation_submitted", generation_submitted_payload(self.request, attempt=attempt))
        return StepResult(name=self.name, outcome="ok", extracted={"submitted": True})


@dataclass
class WaitForGenerationResult:
    """Wait for completion or a known blocked state within a bounded timeout."""

    request: SongRequest
    timeout_seconds: float = 120.0
    poll_interval_seconds: float = 2.0
    name: str = "wait_for_generation_result"
    content_marker: str | None = None
    skip_runner_burst_tick: bool = True

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Poll loaded page state until completion, block, or timeout."""
        deadline = time.monotonic() + max(0.1, self.timeout_seconds)
        last_state: CreatePageState | None = None
        while time.monotonic() < deadline:
            state = await extract_create_page_state(ctx.page)
            last_state = state
            ctx.extracted["suno_create_state"] = state
            if state.blocked_reason is not None:
                _increment_blocked_counters(ctx, state)
                await ctx.sink.write(
                    "generation_blocked",
                    generation_blocked_payload(self.request, phase=self.name, state=state),
                )
                return StepResult(
                    name=self.name,
                    outcome="fail",
                    error=f"blocked:{state.blocked_reason}",
                    extracted=state,
                )
            if state.results:
                ctx.increment("suno.generations_detected", len(state.results))
                ctx.extracted["generation_results"] = state.results
                await ctx.sink.write("generation_completed", generation_completed_payload(self.request, state=state))
                return StepResult(name=self.name, outcome="ok", extracted=state)
            await asyncio.sleep(max(0.0, self.poll_interval_seconds))

        error = "Timed out waiting for generation result"
        await ctx.sink.write(
            "generation_failed",
            generation_failed_payload(self.request, phase=self.name, error=error, state=last_state),
        )
        return StepResult(
            name=self.name,
            outcome="fail",
            error=error,
            extracted=last_state,
        )


def classify_generation_outcome(step_results: list[StepResult]) -> VisitOutcome:
    """Classify generation outcomes with known platform blocks separated."""
    for result in step_results:
        if result.outcome != "fail":
            continue
        if _is_blocked_step(result):
            return "blocked"
        return "failed"
    return "completed"


async def _fill_first_available(page: Any, selectors: tuple[str, ...], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if int(await locator.count()) <= 0:
            continue
        target = locator.first() if hasattr(locator, "first") else locator
        await target.fill(value)
        return True
    return False


async def _click_first_available(page: Any, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if int(await locator.count()) <= 0:
            continue
        target = locator.first() if hasattr(locator, "first") else locator
        await target.click()
        return True
    return False


async def _click_optional(page: Any, selectors: tuple[str, ...]) -> None:
    await _click_first_available(page, selectors)


def _is_blocked_step(result: StepResult) -> bool:
    if isinstance(result.extracted, CreatePageState) and result.extracted.blocked_reason is not None:
        return True
    return bool(result.error and result.error.startswith("blocked:"))


def _increment_blocked_counters(ctx: VisitContext, state: CreatePageState) -> None:
    ctx.increment("suno.blocked_states_detected")
    if state.blocked_reason == "policy_rejected":
        ctx.increment("suno.policy_blocks_detected")

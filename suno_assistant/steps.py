"""Suno-specific visit steps for bounded generation."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gsv.visit import VisitContext
from gsv.visit.plan import StepResult, VisitOutcome

from .evidence import (
    generation_blocked_payload,
    generation_completed_payload,
    generation_failed_payload,
    generation_submitted_payload,
    request_loaded_payload,
    song_links_collected_payload,
    song_links_failed_payload,
)
from .extractors import CreatePageState, extract_create_page_state
from .requests import SongRequest
from .selectors import (
    ADVANCED_TAB_SELECTORS,
    AUTO_STYLE_MODE_SELECTORS,
    CREATE_BUTTON_SELECTORS,
    CUSTOM_MODE_SELECTORS,
    EXCLUDE_STYLES_INPUT_SELECTORS,
    FEMALE_VOCAL_SELECTORS,
    INSTRUMENTAL_SELECTORS,
    LYRICS_INPUT_SELECTORS,
    MALE_VOCAL_SELECTORS,
    MANUAL_STYLE_MODE_SELECTORS,
    MORE_OPTIONS_SELECTORS,
    PROMPT_INPUT_SELECTORS,
    STYLE_INFLUENCE_SLIDER_SELECTORS,
    STYLE_INPUT_SELECTORS,
    TITLE_INPUT_SELECTORS,
    WEIRDNESS_SLIDER_SELECTORS,
)
from .song_links import SongLinkFormat, extract_song_links_page_state, write_song_links_file


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
class VerifyCreatePageFillable:
    """Verify the create page has a prompt box for fill-only preview runs."""

    request: SongRequest
    name: str = "verify_create_page_fillable"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Allow filling visible prompt controls without requiring submission readiness."""
        state = await extract_create_page_state(ctx.page)
        ctx.extracted["suno_create_state"] = state
        if not state.authenticated:
            await ctx.sink.write("generation_blocked", generation_blocked_payload(self.request, phase=self.name, state=state))
            return StepResult(name=self.name, outcome="fail", error="blocked:auth_required", extracted=state)
        if not state.prompt_input_visible:
            if state.blocked_reason is not None:
                _increment_blocked_counters(ctx, state)
                await ctx.sink.write(
                    "generation_blocked",
                    generation_blocked_payload(self.request, phase=self.name, state=state),
                )
                return StepResult(name=self.name, outcome="fail", error=f"blocked:{state.blocked_reason}", extracted=state)
            return StepResult(name=self.name, outcome="fail", error="Prompt input is not visible", extracted=state)
        if state.blocked_reason is not None:
            _increment_blocked_counters(ctx, state)
            ctx.extracted["suno_fill_only_blocked_reason"] = state.blocked_reason
        return StepResult(
            name=self.name,
            outcome="ok",
            extracted={
                "prompt_input_visible": state.prompt_input_visible,
                "create_button_visible": state.create_button_visible,
                "create_button_enabled": state.create_button_enabled,
                "blocked_reason": state.blocked_reason,
                "fill_only": True,
            },
        )


@dataclass
class SelectAdvancedMode:
    """Switch the Suno create page to Advanced mode before field fill."""

    request: SongRequest
    name: str = "select_advanced_mode"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Click the Advanced tab when an advanced request needs it."""
        clicked = await _click_first_available(ctx.page, ADVANCED_TAB_SELECTORS.selectors)
        if not clicked:
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Advanced tab selector not found"),
            )
            return StepResult(name=self.name, outcome="fail", error="Advanced tab selector not found")
        await asyncio.sleep(1.0)
        return StepResult(name=self.name, outcome="ok", extracted={"advanced_mode": True})


@dataclass
class FillSunoRequest:
    """Fill supported Suno create-page fields from a validated request."""

    request: SongRequest
    name: str = "fill_suno_request"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Fill the prompt and supported optional fields."""
        if self.request.uses_advanced_controls:
            return await self._execute_advanced(ctx)

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
                "advanced_mode": False,
                "count": self.request.count,
            },
        )

    async def _execute_advanced(self, ctx: VisitContext) -> StepResult:
        """Fill supported fields in Suno Advanced mode."""
        text_error = await _fill_advanced_primary_text_fields(ctx, self.request)
        if text_error is not None:
            return await _failed_fill(ctx, self.request, self.name, text_error)
        await _open_more_options_for_advanced_levers(ctx, self.request)
        more_options_text_error = await _fill_advanced_more_options_text_fields(ctx, self.request)
        if more_options_text_error is not None:
            return await _failed_fill(ctx, self.request, self.name, more_options_text_error)
        await _apply_advanced_button_fields(ctx, self.request)
        slider_error = await _apply_advanced_sliders(ctx, self.request)
        if slider_error is not None:
            return await _failed_fill(ctx, self.request, self.name, slider_error)

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
                "instrumental": self.request.instrumental,
                "advanced_mode": True,
                "has_exclude_styles": self.request.exclude_styles is not None,
                "vocal_gender": self.request.vocal_gender,
                "style_mode": self.request.style_mode,
                "weirdness": self.request.weirdness,
                "style_influence": self.request.style_influence,
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


@dataclass
class CollectGeneratedSongLinks:
    """Collect visible generated-song links and write them to an operator file."""

    output_path: Path
    source_url: str
    output_format: SongLinkFormat | None = None
    timeout_seconds: float = 20.0
    poll_interval_seconds: float = 1.0
    name: str = "collect_generated_song_links"
    content_marker: str | None = None
    skip_runner_burst_tick: bool = True

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Poll the loaded page briefly, then export any visible song links."""

        deadline = time.monotonic() + max(0.1, self.timeout_seconds)
        while True:
            state = await extract_song_links_page_state(ctx.page, base_url=self.source_url)
            ctx.extracted["song_links_page_state"] = state
            if state.blocked_reason is not None:
                ctx.increment("suno.song_link_collection_blocked")
                await ctx.sink.write(
                    "song_links_failed",
                    song_links_failed_payload(
                        phase=self.name,
                        error=f"blocked:{state.blocked_reason}",
                        source_url=self.source_url,
                    ),
                )
                return StepResult(name=self.name, outcome="fail", error=f"blocked:{state.blocked_reason}", extracted=state)
            if state.songs or time.monotonic() >= deadline:
                export = write_song_links_file(
                    self.output_path,
                    state.songs,
                    source_url=self.source_url,
                    output_format=self.output_format,
                )
                ctx.increment("suno.song_links_collected", len(state.songs))
                ctx.extracted["song_links"] = state.songs
                ctx.extracted["song_links_output_path"] = str(self.output_path)
                await ctx.sink.write(
                    "song_links_collected",
                    song_links_collected_payload(
                        songs=state.songs,
                        output_path=str(self.output_path),
                        source_url=self.source_url,
                    ),
                )
                return StepResult(
                    name=self.name,
                    outcome="ok",
                    extracted={
                        "output_path": str(self.output_path),
                        "result_count": export.count,
                        "source_url": export.source_url,
                    },
                )
            await asyncio.sleep(max(0.0, self.poll_interval_seconds))


def classify_generation_outcome(step_results: list[StepResult]) -> VisitOutcome:
    """Classify generation outcomes with known platform blocks separated."""
    for result in step_results:
        if result.outcome != "fail":
            continue
        if _is_blocked_step(result):
            return "blocked"
        return "failed"
    return "completed"


def classify_song_collection_outcome(step_results: list[StepResult]) -> VisitOutcome:
    """Classify song-link collection outcomes with auth blocks separated."""

    for result in step_results:
        if result.outcome != "fail":
            continue
        if result.error and result.error.startswith("blocked:"):
            return "blocked"
        return "failed"
    return "completed"


async def _fill_first_available(page: Any, selectors: tuple[str, ...], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        target = await _first_visible_locator(locator)
        if target is None:
            continue
        await target.fill(value)
        return True
    return False


async def _click_first_available(page: Any, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        target = await _first_visible_locator(locator)
        if target is None:
            continue
        await target.click()
        return True
    return False


async def _click_optional(page: Any, selectors: tuple[str, ...]) -> None:
    await _click_first_available(page, selectors)


async def _fill_advanced_primary_text_fields(ctx: VisitContext, request: SongRequest) -> str | None:
    fields = (
        (request.lyrics, LYRICS_INPUT_SELECTORS.selectors, "Lyrics input selector not found"),
        (request.style, STYLE_INPUT_SELECTORS.selectors, "Style input selector not found"),
        (request.title, TITLE_INPUT_SELECTORS.selectors, "Title input selector not found"),
    )
    return await _fill_text_fields(ctx, fields)


async def _fill_advanced_more_options_text_fields(ctx: VisitContext, request: SongRequest) -> str | None:
    fields = ((request.exclude_styles, EXCLUDE_STYLES_INPUT_SELECTORS.selectors, "Exclude styles input selector not found"),)
    return await _fill_text_fields(ctx, fields)


async def _fill_text_fields(ctx: VisitContext, fields: tuple[tuple[str | None, tuple[str, ...], str], ...]) -> str | None:
    for value, selectors, error in fields:
        if value is None:
            continue
        if not await _fill_first_available(ctx.page, selectors, value):
            return error
        await _gentle_action_pause(ctx)
    return None


async def _apply_advanced_button_fields(ctx: VisitContext, request: SongRequest) -> None:
    if request.instrumental:
        await _click_optional(ctx.page, INSTRUMENTAL_SELECTORS.selectors)
        await _gentle_action_pause(ctx)
    if request.vocal_gender == "male":
        await _click_optional(ctx.page, MALE_VOCAL_SELECTORS.selectors)
        await _gentle_action_pause(ctx)
    elif request.vocal_gender == "female":
        await _click_optional(ctx.page, FEMALE_VOCAL_SELECTORS.selectors)
        await _gentle_action_pause(ctx)
    if request.style_mode == "manual":
        await _click_optional(ctx.page, MANUAL_STYLE_MODE_SELECTORS.selectors)
        await _gentle_action_pause(ctx)
    elif request.style_mode == "auto":
        await _click_optional(ctx.page, AUTO_STYLE_MODE_SELECTORS.selectors)
        await _gentle_action_pause(ctx)


async def _open_more_options_for_advanced_levers(ctx: VisitContext, request: SongRequest) -> None:
    if not _needs_more_options(request):
        return
    expanded = await _more_options_expanded(ctx.page)
    if expanded is True:
        return
    if expanded is None and await _requested_more_options_controls_visible(ctx.page, request):
        return
    await _click_optional(ctx.page, MORE_OPTIONS_SELECTORS.selectors)
    await _gentle_action_pause(ctx)


async def _more_options_expanded(page: Any) -> bool | None:
    for selector in MORE_OPTIONS_SELECTORS.selectors:
        locator = page.locator(selector)
        if int(await locator.count()) <= 0:
            continue
        target = _first_locator(locator)
        expanded = await target.get_attribute("aria-expanded")
        if expanded is not None:
            return str(expanded).casefold() == "true"
    return None


async def _requested_more_options_controls_visible(page: Any, request: SongRequest) -> bool:
    selectors_by_value = (
        (request.exclude_styles, EXCLUDE_STYLES_INPUT_SELECTORS.selectors),
        (request.vocal_gender == "male", MALE_VOCAL_SELECTORS.selectors),
        (request.vocal_gender == "female", FEMALE_VOCAL_SELECTORS.selectors),
        (request.style_mode == "manual", MANUAL_STYLE_MODE_SELECTORS.selectors),
        (request.style_mode == "auto", AUTO_STYLE_MODE_SELECTORS.selectors),
        (request.weirdness, WEIRDNESS_SLIDER_SELECTORS.selectors),
        (request.style_influence, STYLE_INFLUENCE_SLIDER_SELECTORS.selectors),
    )
    for requested_value, selectors in selectors_by_value:
        if requested_value and await _selector_group_visible(page, selectors):
            return True
    return False


async def _selector_group_visible(page: Any, selectors: tuple[str, ...]) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if await _first_visible_locator(locator) is not None:
            return True
    return False


def _needs_more_options(request: SongRequest) -> bool:
    return bool(
        request.exclude_styles is not None
        or request.vocal_gender is not None
        or request.style_mode is not None
        or request.weirdness is not None
        or request.style_influence is not None
    )


async def _apply_advanced_sliders(ctx: VisitContext, request: SongRequest) -> str | None:
    sliders = (
        (request.weirdness, WEIRDNESS_SLIDER_SELECTORS.selectors, "Weirdness slider selector not found"),
        (
            request.style_influence,
            STYLE_INFLUENCE_SLIDER_SELECTORS.selectors,
            "Style influence slider selector not found",
        ),
    )
    for value, selectors, error in sliders:
        if value is None:
            continue
        if not await _set_slider_first_available(ctx, selectors, value):
            return error
        await _gentle_action_pause(ctx)
    return None


async def _set_slider_first_available(ctx: VisitContext, selectors: tuple[str, ...], value: int) -> bool:
    bounded_value = max(0, min(100, value))
    for selector in selectors:
        locator = ctx.page.locator(selector)
        target = await _first_visible_locator(locator)
        if target is None:
            continue
        current_value = await _slider_current_value(target)
        if current_value is None:
            continue
        await target.focus()
        await _nudge_slider_to_value(ctx, current_value=current_value, target_value=bounded_value)
        return True
    return False


async def _slider_current_value(locator: Any) -> int | None:
    value = await locator.get_attribute("aria-valuenow")
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except ValueError:
        return None


async def _nudge_slider_to_value(ctx: VisitContext, *, current_value: int, target_value: int) -> None:
    delta = target_value - current_value
    if delta == 0:
        return
    key = "ArrowRight" if delta > 0 else "ArrowLeft"
    for _ in range(abs(delta)):
        await ctx.page.keyboard.press(key)
        await _gentle_key_pause(ctx)


async def _gentle_key_pause(ctx: VisitContext, *, min_seconds: float = 0.015, max_seconds: float = 0.045) -> None:
    if bool(getattr(ctx, "_skip_gentle_pause", False)):
        return
    rng = getattr(ctx, "rng", None)
    if rng is None:
        await asyncio.sleep(min_seconds)
        return
    await asyncio.sleep(rng.uniform(min_seconds, max_seconds))


async def _gentle_action_pause(ctx: VisitContext, *, min_seconds: float = 0.35, max_seconds: float = 0.9) -> None:
    if bool(getattr(ctx, "_skip_gentle_pause", False)):
        return
    rng = getattr(ctx, "rng", None)
    if rng is None:
        await asyncio.sleep(min_seconds)
        return
    await asyncio.sleep(rng.uniform(min_seconds, max_seconds))


async def _failed_fill(ctx: VisitContext, request: SongRequest, phase: str, error: str) -> StepResult:
    await ctx.sink.write(
        "generation_failed",
        generation_failed_payload(request, phase=phase, error=error),
    )
    return StepResult(name=phase, outcome="fail", error=error)


def _first_locator(locator: Any) -> Any:
    first = getattr(locator, "first", None)
    if first is None:
        return locator
    return first() if callable(first) else first


async def _first_visible_locator(locator: Any) -> Any | None:
    count = int(await locator.count())
    for index in range(count):
        target = _locator_at(locator, index)
        if await target.is_visible():
            return target
    return None


def _locator_at(locator: Any, index: int) -> Any:
    nth = getattr(locator, "nth", None)
    if callable(nth):
        return nth(index)
    return _first_locator(locator)


def _is_blocked_step(result: StepResult) -> bool:
    if isinstance(result.extracted, CreatePageState) and result.extracted.blocked_reason is not None:
        return True
    return bool(result.error and result.error.startswith("blocked:"))


def _increment_blocked_counters(ctx: VisitContext, state: CreatePageState) -> None:
    ctx.increment("suno.blocked_states_detected")
    if state.blocked_reason == "policy_rejected":
        ctx.increment("suno.policy_blocks_detected")

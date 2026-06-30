"""Suno-specific visit steps for bounded generation."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gsv.visit import VisitContext
from gsv.visit.plan import StepResult, VisitOutcome
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .evidence import (
    create_click_attempted_payload,
    create_click_skipped_payload,
    generation_blocked_payload,
    generation_completed_payload,
    generation_failed_payload,
    generation_pending_payload,
    generation_pre_submit_payload,
    generation_submitted_payload,
    request_loaded_payload,
    song_downloads_completed_payload,
    song_downloads_failed_payload,
    song_links_collected_payload,
    song_links_failed_payload,
    song_renames_completed_payload,
    song_renames_failed_payload,
    ui_click_payload,
)
from .extractors import CreatePageState, extract_create_page_state
from .requests import SongRequest
from .selectors import (
    ADVANCED_TAB_SELECTORS,
    AUTH_REQUIRED_SELECTORS,
    AUTO_STYLE_MODE_SELECTORS,
    CREATE_BUTTON_SELECTORS,
    EXCLUDE_STYLES_INPUT_SELECTORS,
    FEMALE_VOCAL_SELECTORS,
    INSTRUMENTAL_SELECTORS,
    LYRICS_INPUT_SELECTORS,
    MALE_VOCAL_SELECTORS,
    MANUAL_STYLE_MODE_SELECTORS,
    MORE_OPTIONS_SELECTORS,
    PROMPT_INPUT_SELECTORS,
    SONG_DOWNLOAD_ACTION_SELECTORS,
    SONG_DOWNLOAD_MP3_SELECTORS,
    SONG_DOWNLOAD_WAV_SELECTORS,
    SONG_MORE_MENU_SELECTORS,
    SONG_TITLE_EDIT_SELECTORS,
    SONG_TITLE_INPUT_SELECTORS,
    SONG_TITLE_SAVE_SELECTORS,
    STYLE_INFLUENCE_SLIDER_SELECTORS,
    STYLE_INPUT_SELECTORS,
    TITLE_INPUT_SELECTORS,
    WEIRDNESS_SLIDER_SELECTORS,
)
from .song_downloads import (
    SongDownloadFormat,
    SongDownloadResult,
    normalize_downloaded_song_results,
    validate_downloaded_song_file,
    write_song_download_results_file,
)
from .song_links import GeneratedSongLink, SongLinkFormat, extract_song_links_page_state, write_song_links_file
from .song_renames import SongRenameRequest, SongRenameResult, write_song_rename_results_file


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
        ctx.extracted["suno_create_page_ready_monotonic"] = time.monotonic()
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
        ctx.extracted["suno_create_page_ready_monotonic"] = time.monotonic()
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
        clicked = await _click_first_available(
            ctx.page,
            ADVANCED_TAB_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=ADVANCED_TAB_SELECTORS.name,
            phase=self.name,
            source="select_advanced_mode.advanced_tab",
            record_miss=True,
        )
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

        # Simple mode exposes only the description/prompt box. Style, Lyrics, and
        # custom_mode all set uses_advanced_controls (the Suno UI exposes those
        # controls only in the Advanced layout), so a request reaching this branch
        # has none of them and is filled from the prompt alone.
        if not await _fill_first_available(
            ctx.page,
            PROMPT_INPUT_SELECTORS.selectors,
            self.request.prompt,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=PROMPT_INPUT_SELECTORS.name,
            phase=self.name,
            source="fill_suno_request.prompt_input",
        ):
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Prompt input selector not found"),
            )
            return StepResult(name=self.name, outcome="fail", error="Prompt input selector not found")
        ctx.increment("suno.requests_loaded")
        ctx.increment("suno.generations_requested", self.request.count)
        ctx.extracted["suno_request_loaded_monotonic"] = time.monotonic()
        ctx.extracted["suno_request_advanced_mode"] = False
        await ctx.sink.write("request_loaded", request_loaded_payload(self.request))
        return StepResult(
            name=self.name,
            outcome="ok",
            extracted={
                "prompt_length": len(self.request.prompt),
                "has_style": False,
                "has_lyrics": False,
                "custom_mode": False,
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
        ctx.extracted["suno_request_loaded_monotonic"] = time.monotonic()
        ctx.extracted["suno_request_advanced_mode"] = True
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
class PreSubmitInspection:
    """Record submit readiness and then stop before Create for operator inspection."""

    request: SongRequest
    name: str = "pre_submit_inspection"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Capture submit diagnostics without clicking the create/generate button."""
        state = await extract_create_page_state(ctx.page)
        ctx.extracted["suno_create_state"] = state
        diagnostics = await _pre_submit_diagnostics(ctx, state)
        ctx.extracted["suno_pre_submit_diagnostics"] = diagnostics
        await ctx.sink.write(
            "generation_pre_submit",
            generation_pre_submit_payload(self.request, state=state, diagnostics=diagnostics),
        )
        if state.blocked_reason is not None:
            _increment_blocked_counters(ctx, state)
            await ctx.sink.write("generation_blocked", generation_blocked_payload(self.request, phase=self.name, state=state))
            return StepResult(name=self.name, outcome="fail", error=f"blocked:{state.blocked_reason}", extracted=state)
        return StepResult(
            name=self.name,
            outcome="ok",
            extracted={"submit_deferred": True, "pre_submit_diagnostics": diagnostics},
        )


@dataclass
class SubmitGeneration:
    """Submit one bounded generation request."""

    request: SongRequest
    name: str = "submit_generation"
    content_marker: str | None = None

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Click the first available create/generate button."""
        state = await extract_create_page_state(ctx.page)
        ctx.extracted["suno_create_state"] = state
        diagnostics = await _pre_submit_diagnostics(ctx, state)
        ctx.extracted["suno_pre_submit_diagnostics"] = diagnostics
        await ctx.sink.write(
            "generation_pre_submit",
            generation_pre_submit_payload(self.request, state=state, diagnostics=diagnostics),
        )
        if state.blocked_reason is not None:
            _increment_blocked_counters(ctx, state)
            await ctx.sink.write(
                "create_click_skipped",
                create_click_skipped_payload(
                    self.request,
                    phase=self.name,
                    reason=f"blocked:{state.blocked_reason}",
                    state=state,
                    diagnostics=diagnostics,
                ),
            )
            await ctx.sink.write("generation_blocked", generation_blocked_payload(self.request, phase=self.name, state=state))
            return StepResult(name=self.name, outcome="fail", error=f"blocked:{state.blocked_reason}", extracted=state)
        if not state.create_button_visible:
            await ctx.sink.write(
                "create_click_skipped",
                create_click_skipped_payload(
                    self.request,
                    phase=self.name,
                    reason="create_button_not_visible",
                    state=state,
                    diagnostics=diagnostics,
                ),
            )
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Create button is not visible", state=state),
            )
            return StepResult(name=self.name, outcome="fail", error="Create button is not visible", extracted=state)
        if not state.create_button_enabled:
            await ctx.sink.write(
                "create_click_skipped",
                create_click_skipped_payload(
                    self.request,
                    phase=self.name,
                    reason="create_button_disabled",
                    state=state,
                    diagnostics=diagnostics,
                ),
            )
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Create button is disabled", state=state),
            )
            return StepResult(name=self.name, outcome="fail", error="Create button is disabled", extracted=state)

        await _gentle_action_pause(ctx, min_seconds=2.0, max_seconds=4.0)
        clicked = await _click_first_available(
            ctx.page,
            CREATE_BUTTON_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=CREATE_BUTTON_SELECTORS.name,
            phase=self.name,
            source="submit_generation.create_button",
            record_miss=True,
        )
        if not clicked:
            await ctx.sink.write(
                "create_click_skipped",
                create_click_skipped_payload(
                    self.request,
                    phase=self.name,
                    reason="create_button_selector_not_found",
                    state=state,
                    diagnostics=diagnostics,
                ),
            )
            await ctx.sink.write(
                "generation_failed",
                generation_failed_payload(self.request, phase=self.name, error="Create button selector not found"),
            )
            return StepResult(name=self.name, outcome="fail", error="Create button selector not found")
        click = ctx.extracted.get("suno_last_ui_click")
        await ctx.sink.write(
            "create_click_attempted",
            create_click_attempted_payload(
                self.request,
                phase=self.name,
                source="submit_generation.create_button",
                click=click if isinstance(click, dict) else None,
                diagnostics=diagnostics,
            ),
        )
        ctx.increment("suno.requests_submitted")
        attempt = ctx.counters.get("suno.requests_submitted", 1)
        await ctx.sink.write(
            "generation_submitted",
            generation_submitted_payload(self.request, attempt=attempt, pre_submit_diagnostics=diagnostics),
        )
        return StepResult(name=self.name, outcome="ok", extracted={"submitted": True, "pre_submit_diagnostics": diagnostics})


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
        """Poll loaded page state until a new result appears, a block, or timeout.

        The create page lists prior songs, so completion is detected as a *new*
        song result (one not present on the first poll) once generation is no
        longer in progress. This step runs only after a successful submit, so a
        bounded-wait timeout is reported as a soft ``generation_pending`` result
        rather than a hard failure.
        """
        deadline = time.monotonic() + max(0.1, self.timeout_seconds)
        last_state: CreatePageState | None = None
        baseline_keys: set[str] | None = None
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
            if baseline_keys is None:
                baseline_keys = {key for key in (_result_key(result) for result in state.results) if key}
            new_results = [result for result in state.results if _result_key(result) not in baseline_keys]
            if new_results and not state.generation_in_progress:
                ctx.increment("suno.generations_detected", len(new_results))
                ctx.extracted["generation_results"] = new_results
                await ctx.sink.write("generation_completed", generation_completed_payload(self.request, state=state))
                return StepResult(name=self.name, outcome="ok", extracted=state)
            await asyncio.sleep(max(0.0, self.poll_interval_seconds))

        ctx.increment("suno.generation_pending")
        ctx.extracted["suno_generation_pending"] = True
        await ctx.sink.write(
            "generation_pending",
            generation_pending_payload(self.request, state=last_state),
        )
        return StepResult(
            name=self.name,
            outcome="ok",
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
                state = await _collect_song_links_until_stable(ctx, base_url=self.source_url, initial_state=state)
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


@dataclass
class DownloadGeneratedSongs:
    """Download MP3 and/or WAV audio from a playlist page or a single song page."""

    source_url: str
    output_dir: Path
    output_path: Path
    download_formats: tuple[SongDownloadFormat, ...]
    name: str = "download_generated_songs"
    content_marker: str | None = None
    skip_runner_burst_tick: bool = True

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Resolve song targets, download requested audio files, and write a report."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        targets = await _resolve_song_download_targets(ctx, self.source_url)
        if isinstance(targets, StepResult):
            return targets

        results: list[SongDownloadResult] = []
        for song in targets:
            song_results = await _download_generated_song_audio(
                ctx,
                song=song,
                output_dir=self.output_dir,
                formats=self.download_formats,
            )
            results.extend(song_results)
            for result in song_results:
                if result.outcome == "downloaded":
                    ctx.increment("suno.song_audio_downloaded")
                elif result.outcome == "blocked":
                    ctx.increment("suno.song_audio_downloads_blocked")
                else:
                    ctx.increment("suno.song_audio_downloads_failed")

        results = normalize_downloaded_song_results(results)
        export = write_song_download_results_file(
            self.output_path,
            results,
            source_url=self.source_url,
            output_dir=self.output_dir,
            requested_formats=self.download_formats,
        )
        ctx.extracted["song_download_results"] = results
        ctx.extracted["song_download_output_path"] = str(self.output_path)

        blocked = [result for result in results if result.outcome == "blocked"]
        failed = [result for result in results if result.outcome == "failed"]
        if blocked or failed:
            summary_parts: list[str] = []
            if blocked:
                summary_parts.append(f"{len(blocked)} blocked")
            if failed:
                summary_parts.append(f"{len(failed)} failed")
            error = ", ".join(summary_parts) + " song audio download(s)"
            await ctx.sink.write(
                "song_downloads_failed",
                song_downloads_failed_payload(
                    phase=self.name,
                    error=error,
                    source_url=self.source_url,
                    output_dir=str(self.output_dir),
                    output_path=str(self.output_path),
                    requested_formats=list(self.download_formats),
                    results=results,
                ),
            )
            return StepResult(
                name=self.name,
                outcome="fail",
                error=error,
                extracted={"output_path": str(self.output_path), "result_count": export.count},
            )

        await ctx.sink.write(
            "song_downloads_completed",
            song_downloads_completed_payload(
                source_url=self.source_url,
                output_dir=str(self.output_dir),
                output_path=str(self.output_path),
                requested_formats=list(self.download_formats),
                results=results,
            ),
        )
        return StepResult(
            name=self.name,
            outcome="ok",
            extracted={"output_path": str(self.output_path), "result_count": export.count},
        )


@dataclass
class RenameGeneratedSongs:
    """Rename generated songs through normal visible Suno song-page controls."""

    renames: list[SongRenameRequest]
    output_path: Path
    name: str = "rename_generated_songs"
    content_marker: str | None = None
    skip_runner_burst_tick: bool = True

    async def execute(self, ctx: VisitContext) -> StepResult:
        """Visit each song URL, update its title, and write a result report."""

        results: list[SongRenameResult] = []
        for rename in self.renames:
            result = await _rename_generated_song(ctx, rename)
            results.append(result)
            if result.outcome == "renamed":
                ctx.increment("suno.song_titles_renamed")
            else:
                ctx.increment("suno.song_title_renames_failed")

        export = write_song_rename_results_file(self.output_path, results)
        ctx.extracted["song_rename_results"] = results
        ctx.extracted["song_rename_output_path"] = str(self.output_path)
        failed = [result for result in results if result.outcome == "failed"]
        if failed:
            error = f"{len(failed)} song rename(s) failed"
            await ctx.sink.write(
                "song_renames_failed",
                song_renames_failed_payload(phase=self.name, error=error, results=results),
            )
            return StepResult(
                name=self.name,
                outcome="fail",
                error=error,
                extracted={"output_path": str(self.output_path), "result_count": export.count},
            )

        await ctx.sink.write(
            "song_renames_completed",
            song_renames_completed_payload(results=results, output_path=str(self.output_path)),
        )
        return StepResult(
            name=self.name,
            outcome="ok",
            extracted={"output_path": str(self.output_path), "result_count": export.count},
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


def classify_song_collection_outcome(step_results: list[StepResult]) -> VisitOutcome:
    """Classify song-link collection outcomes with auth blocks separated."""

    for result in step_results:
        if result.outcome != "fail":
            continue
        if result.error and result.error.startswith("blocked:"):
            return "blocked"
        return "failed"
    return "completed"


def classify_song_download_outcome(step_results: list[StepResult]) -> VisitOutcome:
    """Classify generated-song audio download outcomes."""

    for result in step_results:
        if result.outcome != "fail":
            continue
        if result.error and "blocked" in result.error:
            return "blocked"
        return "failed"
    return "completed"


def classify_song_rename_outcome(step_results: list[StepResult]) -> VisitOutcome:
    """Classify generated-song rename outcomes."""

    for result in step_results:
        if result.outcome != "fail":
            continue
        if result.error and result.error.startswith("blocked:"):
            return "blocked"
        return "failed"
    return "completed"


async def _fill_first_available(
    page: Any,
    selectors: tuple[str, ...],
    value: str,
    *,
    rng: Any | None = None,
    ctx: VisitContext | None = None,
    selector_group: str = "unknown",
    phase: str = "unknown",
    source: str = "fill_text",
) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        target, index = await _first_visible_locator_with_index(locator)
        if target is None:
            continue
        if await _type_into_locator(
            page,
            target,
            value,
            rng=rng,
            ctx=ctx,
            selector_group=selector_group,
            selector=selector,
            selector_index=index,
            phase=phase,
            source=source,
        ):
            return True
        await target.fill(value)
        return True
    return False


async def _click_first_available(
    page: Any,
    selectors: tuple[str, ...],
    *,
    rng: Any | None = None,
    ctx: VisitContext | None = None,
    selector_group: str = "unknown",
    phase: str = "unknown",
    source: str = "click",
    record_miss: bool = False,
) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        target, index = await _first_visible_locator_with_index(locator)
        if target is None:
            continue
        await _click_locator_with_evidence(
            page,
            target,
            rng=rng,
            ctx=ctx,
            selector_group=selector_group,
            selector=selector,
            selector_index=index,
            phase=phase,
            source=source,
        )
        return True
    if record_miss and ctx is not None:
        await ctx.sink.write(
            "ui_click",
            ui_click_payload(
                phase=phase,
                source=source,
                selector_group=selector_group,
                selector=None,
                selector_index=None,
                outcome="skipped",
                click=None,
                page=_page_ref_payload(page),
                error="selector_not_found",
            ),
        )
    return False


async def _click_optional(
    page: Any,
    selectors: tuple[str, ...],
    *,
    rng: Any | None = None,
    ctx: VisitContext | None = None,
    selector_group: str = "unknown",
    phase: str = "unknown",
    source: str = "optional_click",
) -> None:
    await _click_first_available(
        page,
        selectors,
        rng=rng,
        ctx=ctx,
        selector_group=selector_group,
        phase=phase,
        source=source,
        record_miss=False,
    )


async def _pre_submit_diagnostics(ctx: VisitContext, state: CreatePageState) -> dict[str, Any]:
    now = time.monotonic()
    request_loaded_at = ctx.extracted.get("suno_request_loaded_monotonic")
    ready_checked_at = ctx.extracted.get("suno_create_page_ready_monotonic")
    diagnostics: dict[str, Any] = {
        "url_path": _safe_url_path(getattr(ctx.page, "url", "")),
        "create_button_visible": state.create_button_visible,
        "create_button_enabled": state.create_button_enabled,
        "prompt_input_visible": state.prompt_input_visible,
        "advanced_mode": bool(ctx.extracted.get("suno_request_advanced_mode", False)),
        "blocked_reason": state.blocked_reason,
        "manual_verification_visible": bool(state.diagnostics.get("manual_verification_visible", False)),
    }
    diagnostics.update(await _challenge_frame_diagnostics(ctx.page))
    if isinstance(request_loaded_at, (int, float)):
        diagnostics["seconds_since_request_loaded"] = round(max(0.0, now - float(request_loaded_at)), 3)
    if isinstance(ready_checked_at, (int, float)):
        diagnostics["seconds_since_ready_check"] = round(max(0.0, now - float(ready_checked_at)), 3)
    return diagnostics


def _safe_url_path(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme:
        return url.split("?", 1)[0]
    return parsed.path or "/"


async def _type_into_locator(
    page: Any,
    target: Any,
    value: str,
    *,
    rng: Any | None = None,
    ctx: VisitContext | None = None,
    selector_group: str = "unknown",
    selector: str | None = None,
    selector_index: int | None = None,
    phase: str = "unknown",
    source: str = "type_into_locator",
) -> bool:
    keyboard = getattr(page, "keyboard", None)
    keyboard_type = getattr(keyboard, "type", None)
    if not callable(keyboard_type):
        return False
    try:
        await _click_locator_with_evidence(
            page,
            target,
            rng=rng,
            ctx=ctx,
            selector_group=selector_group,
            selector=selector,
            selector_index=selector_index,
            phase=phase,
            source=source,
        )
        await target.fill("")
        delay = _typing_delay_ms(rng)
        await keyboard_type(value, delay=delay)
        return True
    except Exception:
        return False


async def _click_locator_with_evidence(
    page: Any,
    target: Any,
    *,
    rng: Any | None = None,
    ctx: VisitContext | None = None,
    selector_group: str = "unknown",
    selector: str | None = None,
    selector_index: int | None = None,
    phase: str = "unknown",
    source: str = "click",
) -> dict[str, Any]:
    try:
        click = await _click_locator(page, target, rng=rng)
    except Exception as exc:
        if ctx is not None:
            await ctx.sink.write(
                "ui_click",
                ui_click_payload(
                    phase=phase,
                    source=source,
                    selector_group=selector_group,
                    selector=selector,
                    selector_index=selector_index,
                    outcome="failed",
                    click=None,
                    page=_page_ref_payload(page),
                    error=_safe_error(exc),
                ),
            )
        raise
    if ctx is not None:
        payload = ui_click_payload(
            phase=phase,
            source=source,
            selector_group=selector_group,
            selector=selector,
            selector_index=selector_index,
            outcome="ok",
            click=click,
            page=_page_ref_payload(page),
        )
        ctx.extracted["suno_last_ui_click"] = payload
        await ctx.sink.write("ui_click", payload)
    return click


async def _click_locator(page: Any, target: Any, *, rng: Any | None = None) -> dict[str, Any]:
    box = None
    try:
        box = await target.bounding_box()
    except Exception:
        box = None

    mouse = getattr(page, "mouse", None)
    mouse_move = getattr(mouse, "move", None)
    mouse_click = getattr(mouse, "click", None)
    if isinstance(box, dict) and callable(mouse_move) and callable(mouse_click):
        width = float(box.get("width", 0.0))
        height = float(box.get("height", 0.0))
        if width > 0 and height > 0:
            sampler = rng if rng is not None else None
            uniform = getattr(sampler, "uniform", None)
            randint = getattr(sampler, "randint", None)
            x_ratio = uniform(0.35, 0.65) if callable(uniform) else 0.5
            y_ratio = uniform(0.35, 0.65) if callable(uniform) else 0.5
            steps = randint(4, 10) if callable(randint) else 6
            x = float(box.get("x", 0.0)) + width * x_ratio
            y = float(box.get("y", 0.0)) + height * y_ratio
            try:
                await mouse_move(x, y, steps=steps)
                await mouse_click(x, y)
                return {
                    "method": "mouse",
                    "bounding_box": _box_payload(box),
                    "click_point": {"x": round(x, 1), "y": round(y, 1)},
                    "pointer_steps": steps,
                }
            except Exception as exc:
                fallback_error = _safe_error(exc)
                pass
    await target.click()
    payload: dict[str, Any] = {"method": "locator"}
    if isinstance(box, dict):
        payload["bounding_box"] = _box_payload(box)
    if "fallback_error" in locals():
        payload["fallback_error"] = fallback_error
    return payload


async def _challenge_frame_diagnostics(page: Any) -> dict[str, Any]:
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        return {}
    try:
        result = await evaluate("""() => {
                const providerFor = (value) => {
                    const haystack = String(value || "").toLowerCase();
                    if (haystack.includes("hcaptcha")) return "hcaptcha";
                    if (haystack.includes("challenges.cloudflare") || haystack.includes("turnstile")) return "cloudflare";
                    if (haystack.includes("recaptcha")) return "recaptcha";
                    return null;
                };
                const counts = {};
                let total = 0;
                let visible = 0;
                for (const frame of Array.from(document.querySelectorAll("iframe"))) {
                    const provider = providerFor(`${frame.src} ${frame.title} ${frame.getAttribute("aria-label")}`);
                    if (!provider) continue;
                    total += 1;
                    counts[provider] = (counts[provider] || 0) + 1;
                    const rect = frame.getBoundingClientRect();
                    const style = window.getComputedStyle(frame);
                    if (rect.width > 1 && rect.height > 1 && style.visibility !== "hidden" && style.display !== "none") {
                        visible += 1;
                    }
                }
                return {
                    challenge_frame_count: total,
                    visible_challenge_frame_count: visible,
                    challenge_frame_providers: counts,
                };
            }""")
    except Exception:
        return {}
    if not isinstance(result, dict):
        return {}
    providers = result.get("challenge_frame_providers")
    if not isinstance(providers, dict):
        providers = {}
    return {
        "challenge_frame_count": int(result.get("challenge_frame_count") or 0),
        "visible_challenge_frame_count": int(result.get("visible_challenge_frame_count") or 0),
        "challenge_frame_providers": {str(key): int(value) for key, value in providers.items()},
    }


def _page_ref_payload(page: Any) -> dict[str, Any]:
    return {
        "page_object_id": f"{page.__class__.__name__}:{id(page):x}",
        "url_path": _safe_url_path(getattr(page, "url", "")),
    }


def _box_payload(box: dict[str, Any]) -> dict[str, float]:
    return {
        "x": round(float(box.get("x", 0.0)), 1),
        "y": round(float(box.get("y", 0.0)), 1),
        "width": round(float(box.get("width", 0.0)), 1),
        "height": round(float(box.get("height", 0.0)), 1),
    }


def _safe_error(exc: Exception) -> str:
    text = str(exc).replace("\n", " ").strip()
    if len(text) > 160:
        text = f"{text[:157]}..."
    return text or exc.__class__.__name__


def _typing_delay_ms(rng: Any | None) -> int:
    randint = getattr(rng, "randint", None)
    if callable(randint):
        return int(randint(15, 45))
    return 30


async def _resolve_song_download_targets(ctx: VisitContext, source_url: str) -> list[GeneratedSongLink] | StepResult:
    direct_song = _generated_song_link_from_url(source_url)
    if direct_song is not None:
        return [direct_song]

    state = await _collect_song_links_until_stable(ctx, base_url=source_url)
    ctx.extracted["song_links_page_state"] = state
    if state.blocked_reason is not None:
        ctx.increment("suno.song_downloads_blocked")
        await ctx.sink.write(
            "song_downloads_failed",
            song_downloads_failed_payload(
                phase="resolve_song_download_targets",
                error=f"blocked:{state.blocked_reason}",
                source_url=source_url,
                output_dir="",
                output_path="",
                requested_formats=[],
                results=[],
            ),
        )
        return StepResult(name="resolve_song_download_targets", outcome="fail", error=f"blocked:{state.blocked_reason}")
    return state.songs


async def _collect_song_links_until_stable(
    ctx: VisitContext,
    *,
    base_url: str,
    initial_state: Any | None = None,
    max_scroll_rounds: int = 12,
    stable_rounds: int = 3,
) -> Any:
    """Scroll song-list pages until the extracted song count stops increasing."""

    state = initial_state or await extract_song_links_page_state(ctx.page, base_url=base_url)
    if state.blocked_reason is not None or not state.songs:
        return state

    best_state = state
    stagnant = 0
    last_height = await _page_scroll_height(ctx.page)
    for _ in range(max_scroll_rounds):
        if not hasattr(ctx.page, "evaluate"):
            break
        await ctx.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await _gentle_action_pause(ctx, min_seconds=0.6, max_seconds=1.1)
        state = await extract_song_links_page_state(ctx.page, base_url=base_url)
        if state.blocked_reason is not None:
            return state
        current_height = await _page_scroll_height(ctx.page)
        if len(state.songs) > len(best_state.songs):
            best_state = state
            stagnant = 0
        elif current_height == last_height:
            stagnant += 1
        else:
            stagnant = 0
        last_height = current_height
        if stagnant >= stable_rounds:
            break
    return best_state


async def _download_generated_song_audio(
    ctx: VisitContext,
    *,
    song: GeneratedSongLink,
    output_dir: Path,
    formats: tuple[SongDownloadFormat, ...],
) -> list[SongDownloadResult]:
    results: list[SongDownloadResult] = []
    for download_format in formats:
        result = await _download_generated_song_format(ctx, song=song, output_dir=output_dir, download_format=download_format)
        results.append(result)
    return results


async def _download_generated_song_format(
    ctx: VisitContext,
    *,
    song: GeneratedSongLink,
    output_dir: Path,
    download_format: SongDownloadFormat,
) -> SongDownloadResult:
    try:
        await ctx.page.goto(song.url, wait_until="domcontentloaded")
        await _wait_for_song_page_interactive(ctx)
        if await _selector_group_visible(ctx.page, AUTH_REQUIRED_SELECTORS.selectors):
            return SongDownloadResult(
                url=song.url,
                title=song.title,
                song_id=song.song_id,
                download_format=download_format,
                outcome="blocked",
                error="blocked:auth_required",
            )
        if not await _open_song_download_menu(ctx):
            return SongDownloadResult(
                url=song.url,
                title=song.title,
                song_id=song.song_id,
                download_format=download_format,
                outcome="failed",
                error="Song download menu not found",
            )
        target = await _first_visible_selector(
            ctx.page,
            SONG_DOWNLOAD_MP3_SELECTORS.selectors if download_format == "mp3" else SONG_DOWNLOAD_WAV_SELECTORS.selectors,
        )
        if target is None:
            return SongDownloadResult(
                url=song.url,
                title=song.title,
                song_id=song.song_id,
                download_format=download_format,
                outcome="failed",
                error=f"{download_format.upper()} download action not found",
            )

        label_text = await _locator_text(target)
        try:
            async with ctx.page.expect_download(timeout=10_000) as download_info:
                await target.click()
            download = await download_info.value
            output_path = _unique_download_output_path(
                output_dir=output_dir,
                suggested_filename=download.suggested_filename,
                song_id=song.song_id,
            )
            await download.save_as(str(output_path))
            valid_download, verified_song_id, validation_error = validate_downloaded_song_file(output_path, song.song_id)
            if not valid_download:
                return SongDownloadResult(
                    url=song.url,
                    title=song.title or output_path.stem,
                    song_id=song.song_id,
                    download_format=download_format,
                    outcome="failed",
                    output_path=str(output_path),
                    suggested_filename=download.suggested_filename,
                    verified_song_id=verified_song_id,
                    error=validation_error,
                )
            return SongDownloadResult(
                url=song.url,
                title=song.title or output_path.stem,
                song_id=song.song_id,
                download_format=download_format,
                outcome="downloaded",
                output_path=str(output_path),
                suggested_filename=download.suggested_filename,
                verified_song_id=verified_song_id,
            )
        except PlaywrightTimeoutError:
            error = _download_timeout_reason(download_format=download_format, button_text=label_text)
            return SongDownloadResult(
                url=song.url,
                title=song.title,
                song_id=song.song_id,
                download_format=download_format,
                outcome="blocked" if error.startswith("blocked:") else "failed",
                error=error,
            )
    except Exception as exc:  # noqa: BLE001 - visit steps must serialize unexpected UI/runtime errors.
        return SongDownloadResult(
            url=song.url,
            title=song.title,
            song_id=song.song_id,
            download_format=download_format,
            outcome="failed",
            error=str(exc),
        )


async def _open_song_download_menu(ctx: VisitContext) -> bool:
    candidates = await _ranked_song_menu_candidates(ctx.page)
    for target in candidates:
        await target.click()
        await _gentle_action_pause(ctx)
        if await _selector_group_visible(ctx.page, SONG_DOWNLOAD_ACTION_SELECTORS.selectors):
            clicked = await _click_first_available(ctx.page, SONG_DOWNLOAD_ACTION_SELECTORS.selectors)
            if clicked:
                await _gentle_action_pause(ctx)
                return True
        await _dismiss_song_overlay(ctx)
    return False


async def _dismiss_song_overlay(ctx: VisitContext) -> None:
    try:
        await ctx.page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        await ctx.page.mouse.click(10, 10)
    except Exception:
        pass
    await _gentle_action_pause(ctx)


async def _ranked_song_menu_candidates(page: Any) -> list[Any]:
    viewport_width = await _page_viewport_width(page)
    scored_candidates: list[tuple[tuple[int, int, float, float], Any]] = []
    fallback_candidates: list[Any] = []
    seen_boxes: set[tuple[float, float, float, float]] = set()
    for selector in SONG_MORE_MENU_SELECTORS.selectors:
        locator = page.locator(selector)
        count = int(await locator.count())
        for index in range(count):
            target = _locator_at(locator, index)
            if not await target.is_visible():
                continue
            fallback_candidates.append(target)
            box = await target.bounding_box()
            if box is None:
                continue
            box_key = (
                round(float(box.get("x", 0.0)), 1),
                round(float(box.get("y", 0.0)), 1),
                round(float(box.get("width", 0.0)), 1),
                round(float(box.get("height", 0.0)), 1),
            )
            if box_key in seen_boxes:
                continue
            seen_boxes.add(box_key)
            shallow_context_texts = await _song_menu_candidate_context_texts(target)
            scored_candidates.append(
                (
                    _song_menu_candidate_sort_key(
                        box=box,
                        viewport_width=viewport_width,
                        shallow_context_texts=shallow_context_texts,
                    ),
                    target,
                )
            )
    if not scored_candidates:
        return fallback_candidates
    scored_candidates.sort(key=lambda item: item[0])
    return [target for _, target in scored_candidates]


async def _rename_generated_song(ctx: VisitContext, rename: SongRenameRequest) -> SongRenameResult:
    try:
        await ctx.page.goto(rename.url, wait_until="domcontentloaded")
        await _wait_for_song_page_interactive(ctx)
        if await _selector_group_visible(ctx.page, AUTH_REQUIRED_SELECTORS.selectors):
            return SongRenameResult(
                url=rename.url, requested_title=rename.title, outcome="failed", error="blocked:auth_required"
            )
        if not await _open_song_title_editor(ctx):
            return SongRenameResult(
                url=rename.url,
                requested_title=rename.title,
                outcome="failed",
                error="Song title edit control not found",
            )
        if not await _fill_first_available(ctx.page, SONG_TITLE_INPUT_SELECTORS.selectors, rename.title):
            return SongRenameResult(
                url=rename.url,
                requested_title=rename.title,
                outcome="failed",
                error="Song title input selector not found",
            )
        await _gentle_action_pause(ctx)
        saved = await _click_first_available(ctx.page, SONG_TITLE_SAVE_SELECTORS.selectors)
        if not saved:
            await ctx.page.keyboard.press("Enter")
        await _gentle_action_pause(ctx)
        return SongRenameResult(url=rename.url, requested_title=rename.title, outcome="renamed")
    except Exception as exc:  # noqa: BLE001 - visit steps must serialize unexpected UI/runtime errors.
        return SongRenameResult(url=rename.url, requested_title=rename.title, outcome="failed", error=str(exc))


async def _open_song_title_editor(ctx: VisitContext) -> bool:
    if await _selector_group_visible(ctx.page, SONG_TITLE_INPUT_SELECTORS.selectors):
        return True
    if await _click_first_available(ctx.page, SONG_TITLE_EDIT_SELECTORS.selectors):
        await _gentle_action_pause(ctx)
        if await _selector_group_visible(ctx.page, SONG_TITLE_INPUT_SELECTORS.selectors):
            return True
    if await _click_first_available(ctx.page, SONG_MORE_MENU_SELECTORS.selectors):
        await _gentle_action_pause(ctx)
        if await _click_first_available(ctx.page, SONG_TITLE_EDIT_SELECTORS.selectors):
            await _gentle_action_pause(ctx)
            return True
    return await _selector_group_visible(ctx.page, SONG_TITLE_INPUT_SELECTORS.selectors)


async def _wait_for_song_page_interactive(ctx: VisitContext, timeout_seconds: float = 20.0) -> None:
    try:
        await ctx.page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass

    if getattr(ctx, "_skip_gentle_pause", False):
        return

    deadline = time.monotonic() + max(0.1, timeout_seconds)
    while time.monotonic() < deadline:
        if (
            await _selector_group_visible(ctx.page, SONG_TITLE_INPUT_SELECTORS.selectors)
            or await _selector_group_visible(ctx.page, SONG_TITLE_EDIT_SELECTORS.selectors)
            or await _selector_group_visible(ctx.page, SONG_MORE_MENU_SELECTORS.selectors)
            or await _selector_group_visible(ctx.page, AUTH_REQUIRED_SELECTORS.selectors)
        ):
            return
        await asyncio.sleep(1.0)


async def _first_visible_selector(page: Any, selectors: tuple[str, ...]) -> Any | None:
    for selector in selectors:
        locator = page.locator(selector)
        target = await _first_visible_locator(locator)
        if target is not None:
            return target
    return None


async def _locator_text(locator: Any) -> str | None:
    inner_text = getattr(locator, "inner_text", None)
    if callable(inner_text):
        try:
            value = await inner_text()
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            pass
    text_content = getattr(locator, "text_content", None)
    if callable(text_content):
        try:
            value = await text_content()
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            pass
    return None


def _generated_song_link_from_url(source_url: str) -> GeneratedSongLink | None:
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.rstrip("/").split("/") if part]
    if len(parts) < 2 or parts[-2] not in {"song", "songs"}:
        return None
    song_id = parts[-1]
    if not song_id:
        return None
    return GeneratedSongLink(title=None, url=source_url, song_id=song_id)


def _unique_download_output_path(*, output_dir: Path, suggested_filename: str, song_id: str | None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate = output_dir / suggested_filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    suffix_id = (song_id or "copy")[:8]
    candidate = output_dir / f"{stem} [{suffix_id}]{suffix}"
    attempt = 2
    while candidate.exists():
        candidate = output_dir / f"{stem} [{suffix_id}-{attempt}]{suffix}"
        attempt += 1
    return candidate


def _download_timeout_reason(*, download_format: SongDownloadFormat, button_text: str | None) -> str:
    if button_text and "pro" in button_text.casefold():
        return f"blocked:{download_format}_requires_pro"
    return f"{download_format.upper()} download did not start"


async def _fill_advanced_primary_text_fields(ctx: VisitContext, request: SongRequest) -> str | None:
    fields = (
        (request.lyrics, LYRICS_INPUT_SELECTORS, "Lyrics input selector not found"),
        (request.style, STYLE_INPUT_SELECTORS, "Style input selector not found"),
        (request.title, TITLE_INPUT_SELECTORS, "Title input selector not found"),
    )
    return await _fill_text_fields(ctx, fields)


async def _fill_advanced_more_options_text_fields(ctx: VisitContext, request: SongRequest) -> str | None:
    fields = ((request.exclude_styles, EXCLUDE_STYLES_INPUT_SELECTORS, "Exclude styles input selector not found"),)
    return await _fill_text_fields(ctx, fields)


async def _fill_text_fields(ctx: VisitContext, fields: tuple[tuple[str | None, Any, str], ...]) -> str | None:
    for value, selector_group, error in fields:
        if value is None:
            continue
        if not await _fill_first_available(
            ctx.page,
            selector_group.selectors,
            value,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=selector_group.name,
            phase="fill_suno_request",
            source=f"fill_suno_request.{selector_group.name}",
        ):
            return error
        await _gentle_action_pause(ctx)
    return None


async def _apply_advanced_button_fields(ctx: VisitContext, request: SongRequest) -> None:
    if request.instrumental:
        await _click_optional(
            ctx.page,
            INSTRUMENTAL_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=INSTRUMENTAL_SELECTORS.name,
            phase="fill_suno_request",
            source="fill_suno_request.instrumental",
        )
        await _gentle_action_pause(ctx)
    if request.vocal_gender == "male":
        await _click_optional(
            ctx.page,
            MALE_VOCAL_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=MALE_VOCAL_SELECTORS.name,
            phase="fill_suno_request",
            source="fill_suno_request.male_vocal",
        )
        await _gentle_action_pause(ctx)
    elif request.vocal_gender == "female":
        await _click_optional(
            ctx.page,
            FEMALE_VOCAL_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=FEMALE_VOCAL_SELECTORS.name,
            phase="fill_suno_request",
            source="fill_suno_request.female_vocal",
        )
        await _gentle_action_pause(ctx)
    if request.style_mode == "manual":
        await _click_optional(
            ctx.page,
            MANUAL_STYLE_MODE_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=MANUAL_STYLE_MODE_SELECTORS.name,
            phase="fill_suno_request",
            source="fill_suno_request.manual_style_mode",
        )
        await _gentle_action_pause(ctx)
    elif request.style_mode == "auto":
        await _click_optional(
            ctx.page,
            AUTO_STYLE_MODE_SELECTORS.selectors,
            rng=getattr(ctx, "rng", None),
            ctx=ctx,
            selector_group=AUTO_STYLE_MODE_SELECTORS.name,
            phase="fill_suno_request",
            source="fill_suno_request.auto_style_mode",
        )
        await _gentle_action_pause(ctx)


async def _open_more_options_for_advanced_levers(ctx: VisitContext, request: SongRequest) -> None:
    if not _needs_more_options(request):
        return
    expanded = await _more_options_expanded(ctx.page)
    if expanded is True:
        return
    if expanded is None and await _requested_more_options_controls_visible(ctx.page, request):
        return
    await _click_optional(
        ctx.page,
        MORE_OPTIONS_SELECTORS.selectors,
        rng=getattr(ctx, "rng", None),
        ctx=ctx,
        selector_group=MORE_OPTIONS_SELECTORS.name,
        phase="fill_suno_request",
        source="fill_suno_request.more_options",
    )
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


async def _page_scroll_height(page: Any) -> int:
    try:
        height = await page.evaluate("() => Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)")
    except Exception:
        return 0
    if isinstance(height, (int, float)):
        return int(height)
    return 0


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
    target, _ = await _first_visible_locator_with_index(locator)
    return target


async def _first_visible_locator_with_index(locator: Any) -> tuple[Any | None, int | None]:
    count = int(await locator.count())
    for index in range(count):
        target = _locator_at(locator, index)
        if await target.is_visible():
            return target, index
    return None, None


async def _song_menu_candidate_context_texts(target: Any, *, max_depth: int = 4) -> list[str]:
    evaluate = getattr(target, "evaluate", None)
    if not callable(evaluate):
        return []
    try:
        return list(
            await target.evaluate(
                """(node, depth) => {
                    const texts = [];
                    let current = node.parentElement;
                    for (let level = 0; level < depth && current; level += 1, current = current.parentElement) {
                        const text = (current.innerText || current.textContent || "").trim().slice(0, 160);
                        texts.push(text);
                    }
                    return texts;
                }""",
                max_depth,
            )
        )
    except Exception:
        return []


def _song_menu_candidate_sort_key(
    *,
    box: dict[str, float],
    viewport_width: float | None,
    shallow_context_texts: list[str],
) -> tuple[int, int, float, float]:
    x = float(box.get("x", 0.0))
    y = float(box.get("y", 0.0))
    is_cover_reference = any(_looks_like_cover_reference_context(text) for text in shallow_context_texts)
    is_far_right = viewport_width is not None and x > viewport_width * 0.72
    return (1 if is_cover_reference else 0, 1 if is_far_right else 0, y, x)


def _looks_like_cover_reference_context(text: str) -> bool:
    normalized = " ".join(text.split()).strip().lower()
    for prefix in ("cover", "remaster", "edit", "remix"):
        if normalized.startswith(f"{prefix} of "):
            return True
    return False


def _locator_at(locator: Any, index: int) -> Any:
    nth = getattr(locator, "nth", None)
    if callable(nth):
        return nth(index)
    return _first_locator(locator)


def _is_blocked_step(result: StepResult) -> bool:
    if isinstance(result.extracted, CreatePageState) and result.extracted.blocked_reason is not None:
        return True
    return bool(result.error and result.error.startswith("blocked:"))


def _result_key(result: Any) -> str | None:
    """Return a stable identity for a visible song result, for baseline diffing."""
    return getattr(result, "result_id", None) or getattr(result, "url", None) or getattr(result, "title", None)


def _increment_blocked_counters(ctx: VisitContext, state: CreatePageState) -> None:
    ctx.increment("suno.blocked_states_detected")
    if state.blocked_reason == "policy_rejected":
        ctx.increment("suno.policy_blocks_detected")
    elif state.blocked_reason == "manual_verification_required":
        ctx.increment("suno.manual_verification_blocks_detected")


async def _page_viewport_width(page: Any) -> float | None:
    viewport_size = getattr(page, "viewport_size", None)
    if isinstance(viewport_size, dict) and viewport_size.get("width"):
        return float(viewport_size["width"])
    if not hasattr(page, "evaluate"):
        return None
    try:
        width = await page.evaluate("window.innerWidth")
    except Exception:
        return None
    if width is None:
        return None
    return float(width)

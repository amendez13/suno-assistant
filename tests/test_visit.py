"""Tests for the Suno create-page visit plan."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from gsv.apps import get_app

from tests.module_loader import import_source_module

visit_module = import_source_module("visit")


class FakeSink:
    """Capture safe visit lifecycle evidence."""

    def __init__(self) -> None:
        self.events = []

    async def write(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class SuccessfulStep:
    """Minimal step that exposes runner metadata and succeeds."""

    name = "successful_step"
    content_marker = "ready"
    skip_runner_burst_tick = True
    url = "https://suno.com/create"

    async def execute(self, ctx: SimpleNamespace):
        del ctx
        return visit_module.StepResult(name=self.name, outcome="ok", error=None)


class FailingStep:
    """Minimal step that raises after the wrapper starts timing."""

    name = "failing_step"

    async def execute(self, ctx: SimpleNamespace):
        del ctx
        raise RuntimeError("step failed")


def make_observed_ctx() -> SimpleNamespace:
    """Build a context-shaped fake for observed-step tests."""
    return SimpleNamespace(
        page=SimpleNamespace(url="https://suno.com/create?draft=123"),
        sink=FakeSink(),
    )


class TestSunoVisitPlan:
    """Tests for the Suno smoke visit plan."""

    def test_build_plan_navigates_to_suno_create(self) -> None:
        """The initial Suno plan should only navigate to the create page."""
        plan = visit_module.build_plan()

        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.name == "navigate_create_page"
        assert step.url == visit_module.SUNO_CREATE_URL

    def test_observed_step_emits_success_lifecycle_evidence(self) -> None:
        """Observed steps should record safe start and finish events."""
        ctx = make_observed_ctx()
        step = visit_module.ObservedStep(SuccessfulStep())

        result = asyncio.run(step.execute(ctx))

        assert result.outcome == "ok"
        assert step.content_marker == "ready"
        assert step.skip_runner_burst_tick is True
        assert step.url == "https://suno.com/create"
        assert [event[0] for event in ctx.sink.events] == ["visit_step_started", "visit_step_finished"]
        assert ctx.sink.events[0][1]["step"] == "successful_step"
        assert ctx.sink.events[0][1]["page"]["url_path"] == "/create"
        assert ctx.sink.events[1][1]["outcome"] == "ok"
        assert ctx.sink.events[1][1]["error"] is None
        assert ctx.sink.events[1][1]["duration_seconds"] >= 0

    def test_observed_step_emits_failure_lifecycle_evidence(self) -> None:
        """Observed steps should record failed executions before re-raising."""
        ctx = make_observed_ctx()
        step = visit_module.ObservedStep(FailingStep())

        with pytest.raises(RuntimeError, match="step failed"):
            asyncio.run(step.execute(ctx))

        assert [event[0] for event in ctx.sink.events] == ["visit_step_started", "visit_step_finished"]
        assert ctx.sink.events[1][1]["step"] == "failing_step"
        assert ctx.sink.events[1][1]["outcome"] == "fail"
        assert ctx.sink.events[1][1]["error"] == "step failed"

    def test_build_plan_accepts_normalized_song_request(self) -> None:
        """The plan factory should expose the request-aware generation boundary."""
        request = visit_module.SongRequest.from_prompt("An original synth pop song about a careful launch.")

        plan = visit_module.build_plan(song_request=request)

        assert [step.name for step in plan.steps] == [
            "navigate_create_page",
            "verify_create_page_ready",
            "fill_suno_request",
            "submit_generation",
            "wait_for_generation_result",
        ]
        assert plan.outcome_classifier is visit_module.classify_generation_outcome

    def test_build_plan_can_fill_request_without_submit(self) -> None:
        """Fill-only runs should stop after populating supported create fields."""
        request = visit_module.SongRequest.from_prompt("An original synth pop song about a careful launch.")

        plan = visit_module.build_plan(song_request=request, fill_only=True)

        assert [step.name for step in plan.steps] == [
            "navigate_create_page",
            "verify_create_page_fillable",
            "fill_suno_request",
        ]
        assert plan.outcome_classifier is visit_module.classify_generation_outcome

    def test_build_plan_can_inspect_before_submit_without_clicking(self) -> None:
        """Confirm-submit runs should record submit readiness and stop before Create."""
        request = visit_module.SongRequest.from_prompt("An original synth pop song about a careful launch.")

        plan = visit_module.build_plan(song_request=request, confirm_submit=True)

        assert [step.name for step in plan.steps] == [
            "navigate_create_page",
            "verify_create_page_ready",
            "fill_suno_request",
            "pre_submit_inspection",
        ]
        assert plan.outcome_classifier is visit_module.classify_generation_outcome

    def test_build_plan_switches_to_advanced_for_advanced_requests(self) -> None:
        """Advanced-mode requests should switch tabs before readiness and fill steps."""
        request = visit_module.SongRequest.from_mapping(
            {
                "prompt": "An original synth pop song about a careful launch.",
                "advanced_mode": True,
                "weirdness": 60,
            }
        )

        plan = visit_module.build_plan(song_request=request, fill_only=True)

        assert [step.name for step in plan.steps] == [
            "navigate_create_page",
            "select_advanced_mode",
            "verify_create_page_fillable",
            "fill_suno_request",
        ]
        assert plan.outcome_classifier is visit_module.classify_generation_outcome

    def test_build_song_collection_plan_exports_links(self) -> None:
        """The song-link plan should navigate to the library and collect links."""
        output_path = Path("song-links.json")

        plan = visit_module.build_song_collection_plan(output_path=output_path)

        assert [step.name for step in plan.steps] == [
            "navigate_song_links_source",
            "collect_generated_song_links",
        ]
        assert plan.steps[0].url == visit_module.SUNO_LIBRARY_URL
        assert plan.steps[1].output_path == output_path
        assert plan.outcome_classifier is visit_module.classify_song_collection_outcome

    def test_build_song_rename_plan_renames_titles(self) -> None:
        """The song-rename plan should expose a bounded rename step."""
        output_path = Path("song-renames.json")
        renames = [visit_module.SongRenameRequest(url="https://suno.com/song/song_abc", title="Song v1-b")]

        plan = visit_module.build_song_rename_plan(renames=renames, output_path=output_path)

        assert [step.name for step in plan.steps] == ["rename_generated_songs"]
        assert plan.steps[0].renames == renames
        assert plan.steps[0].output_path == output_path
        assert plan.outcome_classifier is visit_module.classify_song_rename_outcome

    def test_build_song_download_plan_downloads_audio(self) -> None:
        """The song-download plan should navigate to the source and expose one bounded download step."""

        output_dir = Path("downloads")
        output_path = output_dir / "song-downloads.json"

        plan = visit_module.build_song_download_plan(
            source_url="https://suno.com/playlist/example",
            output_dir=output_dir,
            output_path=output_path,
            download_formats=("mp3", "wav"),
        )

        assert [step.name for step in plan.steps] == [
            "navigate_song_download_source",
            "download_generated_songs",
        ]
        assert plan.steps[0].url == "https://suno.com/playlist/example"
        assert plan.steps[1].output_dir == output_dir
        assert plan.steps[1].output_path == output_path
        assert plan.steps[1].download_formats == ("mp3", "wav")
        assert plan.outcome_classifier is visit_module.classify_song_download_outcome

    def test_visit_module_registers_suno_app(self) -> None:
        """Importing the module should register the Suno plan factory."""
        assert get_app("suno") is visit_module.build_plan

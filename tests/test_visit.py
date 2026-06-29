"""Tests for the Suno create-page visit plan."""

from pathlib import Path

from gsv.apps import get_app

from tests.module_loader import import_source_module

visit_module = import_source_module("visit")


class TestSunoVisitPlan:
    """Tests for the Suno smoke visit plan."""

    def test_build_plan_navigates_to_suno_create(self) -> None:
        """The initial Suno plan should only navigate to the create page."""
        plan = visit_module.build_plan()

        assert len(plan.steps) == 1
        step = plan.steps[0]
        assert step.name == "navigate_create_page"
        assert step.url == visit_module.SUNO_CREATE_URL

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

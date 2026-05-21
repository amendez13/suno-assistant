"""Tests for the Suno create-page visit plan."""

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

    def test_visit_module_registers_suno_app(self) -> None:
        """Importing the module should register the Suno plan factory."""
        assert get_app("suno") is visit_module.build_plan

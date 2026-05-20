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

    def test_visit_module_registers_suno_app(self) -> None:
        """Importing the module should register the Suno plan factory."""
        assert get_app("suno") is visit_module.build_plan

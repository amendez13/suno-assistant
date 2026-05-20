"""Tests for the main module."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from gsv.config import SiteConfig, VisitorConfig
from gsv.visit import StepResult, VisitResult

from tests.module_loader import import_source_module

main_module = import_source_module("main")
dependency_summary = main_module.dependency_summary
describe_project = main_module.describe_project


class FakeBrowserManager:
    """Fake browser manager for orchestration tests."""

    def __init__(self, visitor, site, rng=None) -> None:  # type: ignore[no-untyped-def]
        del visitor, site, rng
        self.rate_limiter = "rate-limiter"
        self.events: list[object] = []

    def attach_recorder(self, recorder) -> None:  # type: ignore[no-untyped-def]
        self.events.append(("attach_recorder", recorder))

    def get_browser_metadata(self) -> dict[str, str]:
        return {"browser": "fake"}

    async def start(self) -> None:
        self.events.append("start")

    async def start_tracing(self) -> None:
        self.events.append("start_tracing")

    async def enable_har_for_session(self) -> None:
        self.events.append("enable_har_for_session")

    async def new_page(self) -> str:
        self.events.append("new_page")
        return "page"

    async def stop_tracing(self) -> None:
        self.events.append("stop_tracing")

    async def finalize_har(self) -> None:
        self.events.append("finalize_har")

    async def save_session(self) -> None:
        self.events.append("save_session")

    def finalize_video(self) -> None:
        self.events.append("finalize_video")

    async def close(self) -> None:
        self.events.append("close")


class FakeRecorder:
    """Fake session recorder that captures the final outcome."""

    def __init__(self, events: list[object]) -> None:
        self._events = events
        self._tmp = TemporaryDirectory()
        self.session_dir = Path(self._tmp.name)

    def register_artifact(self, kind: str, relative_path: str) -> None:
        self._events.append(("register_artifact", kind, relative_path))

    def finalize(self, *, outcome: str, error: str | None) -> None:
        self._events.append(("recorder_finalize", outcome, error))


class FakeVisitRunner:
    """Fake visit runner that returns a canned result."""

    result: VisitResult
    events: list[object]

    def __init__(self, ctx) -> None:  # type: ignore[no-untyped-def]
        self.events.append(("visit_context", ctx))

    async def run(self, plan) -> VisitResult:  # type: ignore[no-untyped-def]
        self.events.append(("plan", plan))
        return self.result


class TestProjectSummary:
    """Tests for the project identity helpers."""

    def test_describe_project_names_suno_assistant(self) -> None:
        """The project summary names the app and target site."""
        result = describe_project()

        assert result.name == "Suno Assistant"
        assert result.target_site == "suno.com"

    def test_describe_project_records_gsv_dependency(self) -> None:
        """The project summary documents the framework package boundary."""
        result = describe_project()

        assert result.framework_package == "gentle-site-visitor"
        assert result.framework_import == "gsv"

    def test_dependency_summary_mentions_gsv(self) -> None:
        """The startup summary proves the framework dependency is importable."""
        result = dependency_summary()

        assert "Suno Assistant visits suno.com" in result
        assert "using gsv from gentle-site-visitor" in result

    def test_load_runtime_config_can_force_headed_mode(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The CLI override should flip headless mode off when requested."""
        visitor = VisitorConfig(headless=True)
        site = SiteConfig(name="suno")

        monkeypatch.setattr(main_module, "load_config", lambda path, site_name: (visitor, site))

        resolved = main_module.load_runtime_config(Path("config/config.yaml"), headed=True)

        assert resolved.visitor.headless is False
        assert resolved.site is site

    def test_main_summary_only_prints_dependency_summary(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """Summary-only mode should avoid the live visit orchestration."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        exit_code = main_module.main(["--summary-only"])

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\n"

    def test_main_runs_create_page_visit(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """The CLI should run the create-page smoke visit and report completion."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_create_visit(
            config_path: Path,
            *,
            headed: bool = False,
            keep_open: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is False
            assert keep_open is False
            return VisitResult(
                outcome="completed",
                error=None,
                counters={},
                extracted={},
                step_results=[StepResult(name="navigate_create_page", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_create_visit", fake_run_create_visit)

        exit_code = main_module.main([])

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\nRun completed: suno\n"

    def test_main_passes_keep_open_flag(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """The CLI should pass through the keep-open flag for manual inspection runs."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_create_visit(
            config_path: Path,
            *,
            headed: bool = False,
            keep_open: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is True
            assert keep_open is True
            return VisitResult(
                outcome="completed",
                error=None,
                counters={},
                extracted={},
                step_results=[StepResult(name="navigate_create_page", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_create_visit", fake_run_create_visit)

        exit_code = main_module.main(["--headed", "--keep-open"])

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\nRun completed: suno\n"

    def test_run_create_visit_uses_browser_runtime(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The smoke visit should build a visit context and finalize recording."""
        fake_result = VisitResult(
            outcome="completed",
            error=None,
            counters={"requests_made": 1},
            extracted={},
            step_results=[StepResult(name="navigate_create_page", outcome="ok")],
        )
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeVisitRunner.result = fake_result
        FakeVisitRunner.events = events

        monkeypatch.setattr(
            main_module,
            "load_runtime_config",
            lambda config_path, headed=False: main_module.ResolvedRunConfig(  # type: ignore[no-untyped-def]
                visitor=SimpleNamespace(
                    observability=SimpleNamespace(mode="always", sessions_dir="data/sessions"),
                ),
                site=SimpleNamespace(name="suno"),
            ),
        )
        monkeypatch.setattr(main_module, "BrowserManager", lambda visitor, site, rng=None: browser)
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(main_module, "build_create_plan", lambda: "create-page-plan")
        monkeypatch.setattr(main_module, "keep_browser_open", lambda page: main_module.asyncio.sleep(0))

        result = main_module.asyncio.run(main_module.run_create_visit(Path("config/config.yaml")))

        assert result is fake_result
        assert "start" in events
        assert "start_tracing" in events
        assert "enable_har_for_session" in events
        assert "new_page" in events
        assert "save_session" in events
        assert ("plan", "create-page-plan") in events
        assert ("recorder_finalize", "completed", None) in events
        assert "close" in events

    def test_run_create_visit_can_keep_browser_open(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Inspection mode should wait on the live page before cleanup."""
        fake_result = VisitResult(
            outcome="completed",
            error=None,
            counters={"requests_made": 1},
            extracted={},
            step_results=[StepResult(name="navigate_create_page", outcome="ok")],
        )
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeVisitRunner.result = fake_result
        FakeVisitRunner.events = events

        async def fake_keep_browser_open(page: str) -> None:
            events.append(("keep_open", page))

        monkeypatch.setattr(
            main_module,
            "load_runtime_config",
            lambda config_path, headed=False: main_module.ResolvedRunConfig(  # type: ignore[no-untyped-def]
                visitor=SimpleNamespace(
                    observability=SimpleNamespace(mode="always", sessions_dir="data/sessions"),
                ),
                site=SimpleNamespace(name="suno"),
            ),
        )
        monkeypatch.setattr(main_module, "BrowserManager", lambda visitor, site, rng=None: browser)
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(main_module, "build_create_plan", lambda: "create-page-plan")
        monkeypatch.setattr(main_module, "keep_browser_open", fake_keep_browser_open)

        result = main_module.asyncio.run(main_module.run_create_visit(Path("config/config.yaml"), keep_open=True))

        assert result is fake_result
        assert ("keep_open", "page") in events
        assert "save_session" in events


class TestSampleData:
    """Tests demonstrating fixture usage."""

    def test_sample_data_has_key(self, sample_data: dict) -> None:
        """Test that sample_data fixture has expected key."""
        assert "key" in sample_data
        assert sample_data["key"] == "value"

    def test_sample_data_has_number(self, sample_data: dict) -> None:
        """Test that sample_data fixture has expected number."""
        assert sample_data["number"] == 42

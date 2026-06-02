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


class FakeSession:
    """Fake GSV session wrapper for auth orchestration tests."""

    authenticated: bool = True
    login_authenticated: bool = True
    events: list[object]
    last_instance: "FakeSession | None" = None

    def __init__(self, browser, adapter, config, rng=None) -> None:  # type: ignore[no-untyped-def]
        del rng
        self.browser = browser
        self.adapter = adapter
        self.config = config
        self.is_authenticated = False
        self.events.append(("session_init", adapter))
        FakeSession.last_instance = self

    async def start(self) -> bool:
        self.events.append("session_start")
        self.is_authenticated = self.authenticated
        if self.authenticated:
            await self.browser.start()
        return self.authenticated

    async def login(self) -> bool:
        self.events.append("session_login")
        self.is_authenticated = self.login_authenticated
        if self.login_authenticated:
            await self.browser.start()
        return self.login_authenticated


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
            login: bool = False,
            song_request=None,
            fill_only: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is False
            assert keep_open is False
            assert login is False
            assert song_request is None
            assert fill_only is False
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
            login: bool = False,
            song_request=None,
            fill_only: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is True
            assert keep_open is True
            assert login is False
            assert song_request is None
            assert fill_only is False
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

    def test_main_passes_prompt_song_request(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """The CLI should normalize a one-line prompt before running the visit."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_create_visit(
            config_path: Path,
            *,
            headed: bool = False,
            keep_open: bool = False,
            login: bool = False,
            song_request=None,
            fill_only: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is False
            assert keep_open is False
            assert login is False
            assert song_request.prompt == "Make an original acoustic song about a quiet morning."
            assert song_request.count == 1
            assert fill_only is False
            return VisitResult(
                outcome="completed",
                error=None,
                counters={},
                extracted={},
                step_results=[StepResult(name="navigate_create_page", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_create_visit", fake_run_create_visit)

        exit_code = main_module.main(["--prompt", "Make an original acoustic song about a quiet morning."])

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\nRun completed: suno\n"

    def test_main_passes_yaml_song_request(self, monkeypatch, capsys, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        """The CLI should load structured song requests before running the visit."""
        request_path = tmp_path / "request.yaml"
        request_path.write_text(
            "prompt: A cinematic original song about launching a satellite.\n"
            "title: Orbital Morning\n"
            "style: cinematic synth pop\n"
            "count: 2\n"
            "tags:\n"
            "  - smoke\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_create_visit(
            config_path: Path,
            *,
            headed: bool = False,
            keep_open: bool = False,
            login: bool = False,
            song_request=None,
            fill_only: bool = False,
        ) -> VisitResult:
            del headed, keep_open
            assert config_path == Path("config/config.yaml")
            assert login is False
            assert song_request.title == "Orbital Morning"
            assert song_request.style == "cinematic synth pop"
            assert song_request.count == 2
            assert song_request.tags == ["smoke"]
            assert fill_only is False
            return VisitResult(
                outcome="completed",
                error=None,
                counters={},
                extracted={},
                step_results=[StepResult(name="navigate_create_page", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_create_visit", fake_run_create_visit)

        exit_code = main_module.main(["--request", str(request_path)])

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\nRun completed: suno\n"

    def test_main_requires_headed_login_bootstrap(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """Manual login bootstrap should not start a headless browser."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_create_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--login"])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert "use --headed --login" in captured.err

    def test_main_passes_login_bootstrap_flag(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """The CLI should pass through the headed login bootstrap flag."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_create_visit(
            config_path: Path,
            *,
            headed: bool = False,
            keep_open: bool = False,
            login: bool = False,
            song_request=None,
            fill_only: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is True
            assert keep_open is False
            assert login is True
            assert song_request is None
            assert fill_only is False
            return VisitResult(
                outcome="completed",
                error=None,
                counters={"auth_bootstrap_completed": 1},
                extracted={},
                step_results=[StepResult(name="suno_login_bootstrap", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_create_visit", fake_run_create_visit)

        exit_code = main_module.main(["--headed", "--login"])

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\nRun completed: suno\n"

    def test_main_passes_fill_only_flag_with_prompt(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """Fill-only mode should pass a validated request without submit behavior."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_create_visit(
            config_path: Path,
            *,
            headed: bool = False,
            keep_open: bool = False,
            login: bool = False,
            song_request=None,
            fill_only: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert headed is True
            assert keep_open is True
            assert login is False
            assert song_request.prompt == "Make an original acoustic song about filling the create box."
            assert fill_only is True
            return VisitResult(
                outcome="completed",
                error=None,
                counters={"suno.requests_loaded": 1},
                extracted={},
                step_results=[StepResult(name="fill_suno_request", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_create_visit", fake_run_create_visit)

        exit_code = main_module.main(
            [
                "--headed",
                "--keep-open",
                "--fill-only",
                "--prompt",
                "Make an original acoustic song about filling the create box.",
            ]
        )

        assert exit_code == 0
        assert capsys.readouterr().out == "summary from test\nRun completed: suno\n"

    def test_main_rejects_fill_only_without_request(self, monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
        """Fill-only mode needs request content to put into the create box."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_create_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--fill-only"])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert "use --prompt or --request with --fill-only" in captured.err

    def test_main_passes_collect_songs_options(
        self, monkeypatch, capsys, tmp_path: Path
    ) -> None:  # type: ignore[no-untyped-def]
        """The CLI should run the song-link collection path when requested."""

        output_path = tmp_path / "songs.md"
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_song_collection_visit(
            config_path: Path,
            *,
            output_path: Path,
            output_format=None,
            source_url: str,
            headed: bool = False,
            keep_open: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert output_path.name == "songs.md"
            assert output_format == "markdown"
            assert source_url == "https://suno.com/library"
            assert headed is True
            assert keep_open is True
            return VisitResult(
                outcome="completed",
                error=None,
                counters={"suno.song_links_collected": 2},
                extracted={},
                step_results=[StepResult(name="collect_generated_song_links", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_song_collection_visit", fake_run_song_collection_visit)

        exit_code = main_module.main(
            [
                "--headed",
                "--keep-open",
                "--collect-songs",
                str(output_path),
                "--songs-format",
                "markdown",
            ]
        )

        assert exit_code == 0
        assert capsys.readouterr().out == f"summary from test\nCollected 2 song link(s): {output_path}\nRun completed: suno\n"

    def test_main_rejects_collect_songs_with_generation_request(self, monkeypatch, capsys, tmp_path: Path) -> None:
        """Song-link collection is a separate mode from create-page generation."""

        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_song_collection_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--collect-songs", str(tmp_path / "songs.json"), "--prompt", "A song"])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert "use --collect-songs without --login, --fill-only, --prompt, --request, or --rename-songs" in captured.err

    def test_main_passes_rename_songs_options(self, monkeypatch, capsys, tmp_path: Path) -> None:
        """The CLI should run the generated-song rename path when requested."""

        plan_path = tmp_path / "renames.json"
        result_path = tmp_path / "rename-results.json"
        plan_path.write_text(
            '{"renames": [{"url": "https://suno.com/song/song_abc", "title": "Song v1-b"}]}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_song_rename_visit(
            config_path: Path,
            *,
            renames,
            output_path: Path,
            headed: bool = False,
            keep_open: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert renames[0].url == "https://suno.com/song/song_abc"
            assert renames[0].title == "Song v1-b"
            assert output_path == result_path
            assert headed is True
            assert keep_open is False
            return VisitResult(
                outcome="completed",
                error=None,
                counters={"suno.song_titles_renamed": 1},
                extracted={},
                step_results=[StepResult(name="rename_generated_songs", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_song_rename_visit", fake_run_song_rename_visit)

        exit_code = main_module.main(
            [
                "--headed",
                "--rename-songs",
                str(plan_path),
                "--rename-results",
                str(result_path),
            ]
        )

        assert exit_code == 0
        assert (
            capsys.readouterr().out
            == f"summary from test\nRenamed 1 song title(s), 0 failed: {result_path}\nRun completed: suno\n"
        )

    def test_main_rejects_rename_songs_with_generation_request(self, monkeypatch, capsys, tmp_path: Path) -> None:
        """Generated-song renaming is a separate mode from create-page generation."""

        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_song_rename_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--rename-songs", str(tmp_path / "renames.json"), "--prompt", "A song"])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert "use --rename-songs without --login, --fill-only, --prompt, or --request" in captured.err

    def test_main_passes_download_songs_options(self, monkeypatch, capsys, tmp_path: Path) -> None:
        """The CLI should run the generated-song audio download path when requested."""

        output_dir = tmp_path / "audio"
        result_path = output_dir / "song-downloads.json"
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        async def fake_run_song_download_visit(
            config_path: Path,
            *,
            source_url: str,
            output_dir: Path,
            output_path: Path,
            download_formats,
            headed: bool = False,
            keep_open: bool = False,
        ) -> VisitResult:
            assert config_path == Path("config/config.yaml")
            assert source_url == "https://suno.com/playlist/example"
            assert output_dir.name == "audio"
            assert output_path == result_path
            assert download_formats == ("mp3", "wav")
            assert headed is True
            assert keep_open is False
            return VisitResult(
                outcome="completed",
                error=None,
                counters={"suno.song_audio_downloaded": 4},
                extracted={},
                step_results=[StepResult(name="download_generated_songs", outcome="ok")],
            )

        monkeypatch.setattr(main_module, "run_song_download_visit", fake_run_song_download_visit)

        exit_code = main_module.main(
            [
                "--headed",
                "--download-songs",
                str(output_dir),
                "--songs-url",
                "https://suno.com/playlist/example",
                "--download-formats",
                "both",
            ]
        )

        assert exit_code == 0
        assert (
            capsys.readouterr().out
            == f"summary from test\nDownloaded 4 audio file(s), 0 blocked, 0 failed: {result_path}\nRun completed: suno\n"
        )

    def test_main_rejects_download_songs_with_generation_request(self, monkeypatch, capsys, tmp_path: Path) -> None:
        """Audio downloading is a separate mode from create-page generation."""

        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_song_download_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--download-songs", str(tmp_path / "audio"), "--prompt", "A song"])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert (
            "use --download-songs without --login, --fill-only, --prompt, --request, --collect-songs, or --rename-songs"
            in captured.err
        )

    def test_main_rejects_invalid_prompt_before_browser_start(
        self, monkeypatch, capsys
    ) -> None:  # type: ignore[no-untyped-def]
        """Invalid prompt input should stop before the browser runtime is called."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_create_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--prompt", "   "])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert "Invalid song request: prompt must not be empty" in captured.err

    def test_main_rejects_missing_request_before_browser_start(
        self, monkeypatch, capsys
    ) -> None:  # type: ignore[no-untyped-def]
        """Missing request files should stop before the browser runtime is called."""
        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")
        monkeypatch.setattr(
            main_module,
            "run_create_visit",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("browser should not start")),
        )

        exit_code = main_module.main(["--request", "missing.yaml"])

        captured = capsys.readouterr()
        assert exit_code == 2
        assert captured.out == "summary from test\n"
        assert "Invalid song request: Request file not found: missing.yaml" in captured.err

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
        FakeSession.events = events
        FakeSession.authenticated = True
        FakeSession.login_authenticated = True

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(
            main_module,
            "build_create_plan",
            lambda song_request=None, fill_only=False: f"create-page-plan:{song_request}:{fill_only}",
        )
        monkeypatch.setattr(main_module, "keep_browser_open", lambda page: main_module.asyncio.sleep(0))

        result = main_module.asyncio.run(main_module.run_create_visit(Path("config/config.yaml")))

        assert result is fake_result
        assert "session_start" in events
        assert "start" in events
        assert "start_tracing" in events
        assert "enable_har_for_session" in events
        assert "new_page" in events
        assert "save_session" in events
        assert ("plan", "create-page-plan:None:False") in events
        assert ("recorder_finalize", "completed", None) in events
        assert "close" in events

    def test_run_create_visit_passes_fill_only_to_plan(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Fill-only orchestration should build a non-submitting request plan."""
        fake_result = VisitResult(
            outcome="completed",
            error=None,
            counters={"suno.requests_loaded": 1},
            extracted={},
            step_results=[StepResult(name="fill_suno_request", outcome="ok")],
        )
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeVisitRunner.result = fake_result
        FakeVisitRunner.events = events
        FakeSession.events = events
        FakeSession.authenticated = True
        FakeSession.login_authenticated = True
        request = main_module.SongRequest.from_prompt("Make an original song about filling a form.")

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(
            main_module,
            "build_create_plan",
            lambda song_request=None, fill_only=False: f"create-page-plan:{song_request.prompt}:{fill_only}",
        )

        result = main_module.asyncio.run(
            main_module.run_create_visit(Path("config/config.yaml"), song_request=request, fill_only=True)
        )

        assert result is fake_result
        assert ("plan", "create-page-plan:Make an original song about filling a form.:True") in events
        assert "save_session" in events

    def test_run_create_visit_blocks_when_auth_required(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Unauthenticated sessions should stop before the visit plan runs."""
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeSession.events = events
        FakeSession.authenticated = False
        FakeSession.login_authenticated = True

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(
            main_module,
            "VisitRunner",
            lambda ctx: (_ for _ in ()).throw(AssertionError("visit plan should not run")),
        )

        result = main_module.asyncio.run(main_module.run_create_visit(Path("config/config.yaml")))

        assert result.outcome == "blocked"
        assert result.counters == {"auth_required": 1}
        assert "session_start" in events
        assert "start" not in events
        assert "save_session" not in events
        assert ("recorder_finalize", "blocked", result.error) in events
        assert "close" in events

    def test_run_create_visit_login_bootstrap_uses_session_login(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The login path should use GSV Session.login and skip the visit plan."""
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeSession.events = events
        FakeSession.authenticated = False
        FakeSession.login_authenticated = True

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(
            main_module,
            "VisitRunner",
            lambda ctx: (_ for _ in ()).throw(AssertionError("visit plan should not run")),
        )

        result = main_module.asyncio.run(main_module.run_create_visit(Path("config/config.yaml"), login=True))

        assert result.outcome == "completed"
        assert result.counters == {"auth_bootstrap_completed": 1}
        assert "session_login" in events
        assert "save_session" in events
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
        FakeSession.events = events
        FakeSession.authenticated = True
        FakeSession.login_authenticated = True

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(main_module, "build_create_plan", lambda song_request=None, fill_only=False: "create-page-plan")
        monkeypatch.setattr(main_module, "keep_browser_open", fake_keep_browser_open)

        result = main_module.asyncio.run(main_module.run_create_visit(Path("config/config.yaml"), keep_open=True))

        assert result is fake_result
        assert ("keep_open", "page") in events
        assert "save_session" in events

    def test_run_song_collection_visit_uses_collection_plan(self, monkeypatch, tmp_path: Path) -> None:
        """Song-link collection should build its own bounded visit plan."""

        fake_result = VisitResult(
            outcome="completed",
            error=None,
            counters={"suno.song_links_collected": 2},
            extracted={},
            step_results=[StepResult(name="collect_generated_song_links", outcome="ok")],
        )
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeVisitRunner.result = fake_result
        FakeVisitRunner.events = events
        FakeSession.events = events
        FakeSession.authenticated = True
        FakeSession.login_authenticated = True
        output_path = tmp_path / "songs.json"

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(
            main_module,
            "build_song_collection_plan",
            lambda output_path, output_format=None, source_url="": f"song-links-plan:{output_path.name}:{source_url}",
        )

        result = main_module.asyncio.run(
            main_module.run_song_collection_visit(
                Path("config/config.yaml"),
                output_path=output_path,
                source_url="https://suno.com/library",
            )
        )

        assert result is fake_result
        assert "session_start" in events
        assert "start_tracing" in events
        assert "enable_har_for_session" in events
        assert ("plan", "song-links-plan:songs.json:https://suno.com/library") in events
        assert "save_session" in events

    def test_run_song_rename_visit_uses_rename_plan(self, monkeypatch, tmp_path: Path) -> None:
        """Song-title renaming should build its own bounded visit plan."""

        fake_result = VisitResult(
            outcome="completed",
            error=None,
            counters={"suno.song_titles_renamed": 1},
            extracted={},
            step_results=[StepResult(name="rename_generated_songs", outcome="ok")],
        )
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeVisitRunner.result = fake_result
        FakeVisitRunner.events = events
        FakeSession.events = events
        FakeSession.authenticated = True
        FakeSession.login_authenticated = True
        output_path = tmp_path / "rename-results.json"
        renames = [main_module.SongRenameRequest(url="https://suno.com/song/song_abc", title="Song v1-b")]

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(
            main_module,
            "build_song_rename_plan",
            lambda renames, output_path: f"song-rename-plan:{len(renames)}:{output_path.name}",
        )

        result = main_module.asyncio.run(
            main_module.run_song_rename_visit(
                Path("config/config.yaml"),
                renames=renames,
                output_path=output_path,
            )
        )

        assert result is fake_result
        assert "session_start" in events
        assert "start_tracing" in events
        assert "enable_har_for_session" in events
        assert ("plan", "song-rename-plan:1:rename-results.json") in events
        assert "save_session" in events

    def test_run_song_download_visit_uses_download_plan(self, monkeypatch, tmp_path: Path) -> None:
        """Song audio downloads should build their own bounded visit plan."""

        fake_result = VisitResult(
            outcome="completed",
            error=None,
            counters={"suno.song_audio_downloaded": 2},
            extracted={},
            step_results=[StepResult(name="download_generated_songs", outcome="ok")],
        )
        browser = FakeBrowserManager(None, None)
        events = browser.events
        FakeVisitRunner.result = fake_result
        FakeVisitRunner.events = events
        FakeSession.events = events
        FakeSession.authenticated = True
        output_dir = tmp_path / "audio"
        output_path = output_dir / "song-downloads.json"

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
        monkeypatch.setattr(main_module, "Session", FakeSession)
        monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
        monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: FakeRecorder(events))
        monkeypatch.setattr(main_module, "build_pacing", lambda visitor, site, rate_limiter, rng=None: "pacing")
        monkeypatch.setattr(main_module, "VisitRunner", FakeVisitRunner)
        monkeypatch.setattr(
            main_module,
            "build_song_download_plan",
            lambda source_url, output_dir, output_path, download_formats: (
                f"song-download-plan:{source_url}:{output_dir.name}:{output_path.name}:{download_formats}"
            ),
        )

        result = main_module.asyncio.run(
            main_module.run_song_download_visit(
                Path("config/config.yaml"),
                source_url="https://suno.com/playlist/example",
                output_dir=output_dir,
                output_path=output_path,
                download_formats=("mp3", "wav"),
            )
        )

        assert result is fake_result
        assert "session_start" in events
        assert "start_tracing" in events
        assert "enable_har_for_session" in events
        assert (
            "plan",
            "song-download-plan:https://suno.com/playlist/example:audio:song-downloads.json:('mp3', 'wav')",
        ) in events
        assert "save_session" in events

    def test_run_collection_and_download_return_auth_required_when_session_fails(
        self, monkeypatch, tmp_path: Path
    ) -> None:  # type: ignore[no-untyped-def]
        """Collection/download orchestration should stop cleanly when auth is missing."""

        def resolved_config(config_path, headed=False):  # type: ignore[no-untyped-def]
            return main_module.ResolvedRunConfig(
                visitor=SimpleNamespace(observability=SimpleNamespace(mode="off", sessions_dir="data/sessions")),
                site=SimpleNamespace(name="suno"),
            )

        for runner_name in ("run_song_collection_visit", "run_song_download_visit"):
            browser = FakeBrowserManager(None, None)
            events = browser.events
            FakeSession.events = events
            FakeSession.authenticated = False
            monkeypatch.setattr(main_module, "load_runtime_config", resolved_config)
            monkeypatch.setattr(main_module, "BrowserManager", lambda visitor, site, rng=None, browser=browser: browser)
            monkeypatch.setattr(main_module, "Session", FakeSession)
            monkeypatch.setattr(main_module, "build_suno_auth_adapter", lambda site: "auth-adapter")
            monkeypatch.setattr(main_module, "open_session_recorder", lambda visitor, site, browser: None)

            if runner_name == "run_song_collection_visit":
                result = main_module.asyncio.run(
                    main_module.run_song_collection_visit(Path("config/config.yaml"), output_path=tmp_path / "songs.json")
                )
            else:
                result = main_module.asyncio.run(
                    main_module.run_song_download_visit(
                        Path("config/config.yaml"),
                        source_url="https://suno.com/library",
                        output_dir=tmp_path / "audio",
                        output_path=tmp_path / "audio" / "song-downloads.json",
                        download_formats=("mp3",),
                    )
                )

            assert result.outcome == "blocked"
            assert result.error == main_module.AUTH_REQUIRED_MESSAGE
            assert "save_session" not in events
            assert "close" in events

    def test_finalize_recording_and_login_result_helpers(self) -> None:
        """Small main helpers should handle recorder/no-recorder and login outcomes."""

        browser = FakeBrowserManager(None, None)
        assert main_module.asyncio.run(main_module.finalize_recording(browser, None, None)) is None

        events = browser.events
        recorder = FakeRecorder(events)
        failed_result = VisitResult(outcome="failed", error="boom", counters={}, extracted={}, step_results=[])
        main_module.asyncio.run(main_module.finalize_recording(browser, recorder, failed_result))

        assert "stop_tracing" in events
        assert "finalize_har" in events
        assert "finalize_video" in events
        assert ("recorder_finalize", "failed", "boom") in events
        assert main_module.build_login_result(authenticated=False).error == (
            "Suno login did not reach the authenticated create page before timeout."
        )

    def test_open_session_recorder_builds_suno_run_ref(
        self, monkeypatch, tmp_path: Path
    ) -> None:  # type: ignore[no-untyped-def]
        """Recorder setup should scope session artifacts to the Suno site."""

        captured: dict[str, object] = {}

        def fake_open(*, sessions_dir, mode, run, browser_meta_provider):  # type: ignore[no-untyped-def]
            captured["sessions_dir"] = sessions_dir
            captured["mode"] = mode
            captured["run"] = run
            captured["browser_meta"] = browser_meta_provider()
            return "recorder"

        monkeypatch.setattr(main_module.SessionRecorder, "open", fake_open)
        visitor = SimpleNamespace(observability=SimpleNamespace(mode="always", sessions_dir=str(tmp_path / "sessions")))
        site = SimpleNamespace(name="suno")
        browser = FakeBrowserManager(None, None)

        recorder = main_module.open_session_recorder(visitor, site, browser)

        assert recorder == "recorder"
        assert captured["sessions_dir"] == tmp_path / "sessions" / "suno"
        assert captured["mode"] == "always"
        assert captured["browser_meta"] == {"browser": "fake"}
        run = captured["run"]
        assert run.plan_name == "suno:create-smoke"
        assert run.parameters == {"source": "suno_assistant.main"}
        assert run.site == "suno"

    def test_keep_browser_open_exits_when_page_closes(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The headed keep-open loop should stop once the page reports closed."""

        sleeps: list[float] = []

        class ClosingPage:
            def __init__(self) -> None:
                self.calls = 0

            def is_closed(self) -> bool:
                self.calls += 1
                return self.calls > 1

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

        main_module.asyncio.run(main_module.keep_browser_open(ClosingPage()))

        assert sleeps == [0.5]

    def test_main_rejects_or_reports_invalid_mode_options(self, monkeypatch, capsys, tmp_path: Path) -> None:
        """Invalid result-path and plan/format combinations should return CLI usage errors."""

        monkeypatch.setattr(main_module, "configure_logging", lambda: None)
        monkeypatch.setattr(main_module, "get_release_info", lambda: {"source": "test"})
        monkeypatch.setattr(main_module, "dependency_summary", lambda: "summary from test")

        assert main_module.main(["--rename-results", str(tmp_path / "rename-results.json")]) == 2
        assert "use --rename-results together with --rename-songs" in capsys.readouterr().err

        assert main_module.main(["--download-results", str(tmp_path / "downloads.json")]) == 2
        assert "use --download-results together with --download-songs" in capsys.readouterr().err

        missing_plan = tmp_path / "missing-renames.json"
        assert main_module.main(["--rename-songs", str(missing_plan)]) == 2
        assert "Invalid song rename plan:" in capsys.readouterr().err

        invalid_download_args = SimpleNamespace(
            login=False,
            fill_only=False,
            request=None,
            prompt=None,
            collect_songs=None,
            rename_songs=None,
            download_songs=tmp_path / "audio",
            download_formats="aac",
        )
        assert main_module._run_song_download_mode(invalid_download_args) == 2
        assert "Invalid song download request:" in capsys.readouterr().err


class TestSampleData:
    """Tests demonstrating fixture usage."""

    def test_sample_data_has_key(self, sample_data: dict) -> None:
        """Test that sample_data fixture has expected key."""
        assert "key" in sample_data
        assert sample_data["key"] == "value"

    def test_sample_data_has_number(self, sample_data: dict) -> None:
        """Test that sample_data fixture has expected number."""
        assert sample_data["number"] == 42

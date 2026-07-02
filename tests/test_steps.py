"""Tests for Suno generation visit steps."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import suno_assistant.steps as steps_module
from suno_assistant.requests import SongRequest
from suno_assistant.selectors import (
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
    SONG_MORE_MENU_SELECTORS,
    SONG_TITLE_EDIT_SELECTORS,
    SONG_TITLE_INPUT_SELECTORS,
    SONG_TITLE_SAVE_SELECTORS,
    STYLE_INFLUENCE_SLIDER_SELECTORS,
    STYLE_INPUT_SELECTORS,
    TITLE_INPUT_SELECTORS,
    WEIRDNESS_SLIDER_SELECTORS,
)
from suno_assistant.song_downloads import SongDownloadResult
from suno_assistant.song_links import GeneratedSongLink, SongLinksPageState
from suno_assistant.song_renames import SongRenameRequest
from suno_assistant.steps import (
    CollectGeneratedSongLinks,
    DownloadGeneratedSongs,
    FillSunoRequest,
    PreSubmitInspection,
    RenameGeneratedSongs,
    SelectAdvancedMode,
    SubmitGeneration,
    VerifyCreatePageFillable,
    VerifyCreatePageReady,
    WaitForGenerationResult,
    _challenge_frame_diagnostics,
    _click_first_available,
    _click_locator,
    _click_locator_with_evidence,
    _collect_song_links_until_stable,
    _dismiss_song_overlay,
    _download_generated_song_audio,
    _download_generated_song_format,
    _download_timeout_reason,
    _fill_first_available,
    _first_locator,
    _generated_song_link_from_url,
    _locator_text,
    _looks_like_cover_reference_context,
    _open_song_download_menu,
    _open_song_title_editor,
    _page_scroll_height,
    _page_viewport_width,
    _pre_submit_diagnostics,
    _ranked_song_menu_candidates,
    _resolve_song_download_targets,
    _safe_url_path,
    _song_menu_candidate_sort_key,
    _type_into_locator,
    _typing_delay_ms,
    _unique_download_output_path,
    _wait_for_song_page_interactive,
    classify_generation_outcome,
    classify_song_collection_outcome,
    classify_song_download_outcome,
    classify_song_rename_outcome,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "suno"


class FakeSink:
    """Capture evidence writes from visit steps."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def write(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


class FakeLocator:
    """Minimal Playwright locator fake."""

    def __init__(self, page: "FakePage", selector: str, index: int = 0) -> None:
        self.page = page
        self.selector = selector
        self.index = index

    async def count(self) -> int:
        if self.selector not in self.page.available_selectors:
            return 0
        return self.page.selector_counts.get(self.selector, 1)

    @property
    def first(self) -> "FakeLocator":
        return FakeLocator(self.page, self.selector, 0)

    def nth(self, index: int) -> "FakeLocator":
        return FakeLocator(self.page, self.selector, index)

    async def fill(self, value: str) -> None:
        self.page.fills.append((self.selector, value))
        self.page.fill_indexes.append((self.selector, self.index))
        if self.selector not in self.page.no_value_after_fill_selectors:
            self.page.input_values[(self.selector, self.index)] = value

    async def click(self) -> None:
        self.page.clicks.append(self.selector)

    async def is_visible(self) -> bool:
        if (self.selector, self.index) in self.page.hidden_selector_indexes:
            return False
        return self.selector not in self.page.hidden_selectors

    async def focus(self) -> None:
        self.page.focuses.append(self.selector)
        self.page.focused_selector = self.selector
        self.page.attribute_values.setdefault((self.selector, "aria-valuenow"), "50")

    async def get_attribute(self, name: str) -> str | None:
        value = self.page.attribute_values.get((self.selector, name))
        if value is not None:
            return value
        if name != "aria-valuenow" or self.selector in self.page.no_value_selectors:
            return None
        return "50"

    async def input_value(self) -> str:
        return self.page.input_values.get((self.selector, self.index), "")

    async def bounding_box(self) -> dict[str, float] | None:
        if self.selector not in self.page.available_selectors:
            return None
        if self.selector in self.page.no_box_selectors:
            return None
        return self.page.bounding_boxes.get(
            (self.selector, self.index),
            {"x": 10.0, "y": 20.0, "width": 100.0, "height": 10.0},
        )

    async def inner_text(self) -> str:
        return self.page.locator_texts.get((self.selector, self.index), "")

    async def text_content(self) -> str:
        return self.page.locator_texts.get((self.selector, self.index), "")

    async def evaluate(self, script: str, *args: Any) -> Any:
        del script, args
        if (self.selector, self.index) in self.page.locator_evaluate_errors:
            raise RuntimeError("locator evaluate failed")
        return self.page.locator_evaluate_values.get((self.selector, self.index), [])


class FakeDownload:
    """Minimal Playwright download fake."""

    def __init__(self, suggested_filename: str = "song.mp3") -> None:
        self.suggested_filename = suggested_filename
        self.saved_paths: list[str] = []

    async def save_as(self, path: str) -> None:
        self.saved_paths.append(path)
        Path(path).write_bytes(b"audio")


class FakeDownloadInfo:
    """Async context manager returned by expect_download."""

    def __init__(self, page: "FakePage") -> None:
        self.page = page

    async def _download_value(self) -> FakeDownload:
        return self.page.next_download

    @property
    def value(self):  # type: ignore[no-untyped-def]
        return self._download_value()

    async def __aenter__(self) -> "FakeDownloadInfo":
        if self.page.expect_download_raises is not None:
            raise self.page.expect_download_raises
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None


class FakeLocatorWithoutFirst:
    """Locator fake for the defensive fallback path."""

    pass


class FakePage:
    """Minimal Playwright page fake backed by fixture HTML."""

    def __init__(
        self,
        fixture_names: list[str],
        *,
        selectors: set[str] | None = None,
        no_box_selectors: set[str] | None = None,
        no_value_selectors: set[str] | None = None,
        hidden_selectors: set[str] | None = None,
        selector_counts: dict[str, int] | None = None,
        hidden_selector_indexes: set[tuple[str, int]] | None = None,
        viewport_size: dict[str, int] | None = None,
        evaluate_values: list[Any] | None = None,
        evaluate_error: bool = False,
        supports_keyboard_type: bool = False,
        keyboard_type_raises: bool = False,
        keyboard_press_updates_sliders: bool = True,
        no_value_after_fill_selectors: set[str] | None = None,
        supports_mouse_move: bool = False,
        mouse_move_raises: bool = False,
    ) -> None:
        self.fixture_names = fixture_names
        self.available_selectors = selectors or set()
        self.selector_counts = selector_counts or {}
        self.no_box_selectors = no_box_selectors or set()
        self.no_value_selectors = no_value_selectors or set()
        self.hidden_selectors = hidden_selectors or set()
        self.hidden_selector_indexes = hidden_selector_indexes or set()
        self.attribute_values: dict[tuple[str, str], str] = {}
        self.bounding_boxes: dict[tuple[str, int], dict[str, float]] = {}
        self.locator_texts: dict[tuple[str, int], str] = {}
        self.locator_evaluate_values: dict[tuple[str, int], Any] = {}
        self.locator_evaluate_errors: set[tuple[str, int]] = set()
        self.viewport_size = viewport_size
        self.evaluate_values = evaluate_values or []
        self.evaluate_error = evaluate_error
        self.keyboard_type_raises = keyboard_type_raises
        self.keyboard_press_updates_sliders = keyboard_press_updates_sliders
        self.no_value_after_fill_selectors = no_value_after_fill_selectors or set()
        self.mouse_move_raises = mouse_move_raises
        self.url = "https://suno.com/create"
        self.content_calls = 0
        self.load_state_calls: list[tuple[str, int]] = []
        self.evaluate_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fills: list[tuple[str, str]] = []
        self.fill_indexes: list[tuple[str, int]] = []
        self.input_values: dict[tuple[str, int], str] = {}
        self.clicks: list[str] = []
        self.focuses: list[str] = []
        self.focused_selector: str | None = None
        self.mouse_clicks: list[tuple[float, float]] = []
        self.mouse_moves: list[tuple[float, float, int]] = []
        self.gotos: list[str] = []
        if supports_mouse_move:
            self.mouse = SimpleNamespace(click=self._mouse_click, move=self._mouse_move)
        else:
            self.mouse = SimpleNamespace(click=self._mouse_click)
        self.keyboard_presses: list[str] = []
        self.typed_texts: list[tuple[str, int]] = []
        if supports_keyboard_type:
            self.keyboard = SimpleNamespace(press=self._keyboard_press, type=self._keyboard_type)
        else:
            self.keyboard = SimpleNamespace(press=self._keyboard_press)
        self.next_download = FakeDownload()
        self.expect_download_raises: Exception | None = None

    async def content(self) -> str:
        index = min(self.content_calls, len(self.fixture_names) - 1)
        self.content_calls += 1
        return (FIXTURE_DIR / self.fixture_names[index]).read_text(encoding="utf-8")

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    async def goto(self, url: str, wait_until: str = "load") -> None:
        del wait_until
        self.gotos.append(url)

    async def wait_for_load_state(self, state: str, timeout: int = 0) -> None:
        self.load_state_calls.append((state, timeout))

    async def evaluate(self, script: str, *args: Any) -> Any:
        self.evaluate_calls.append((script, args))
        if self.evaluate_error:
            raise RuntimeError("evaluate failed")
        if self.evaluate_values:
            return self.evaluate_values.pop(0)
        return 0

    def expect_download(self, timeout: int = 0) -> FakeDownloadInfo:
        del timeout
        return FakeDownloadInfo(self)

    async def _mouse_click(self, x: float, y: float) -> None:
        self.mouse_clicks.append((x, y))

    async def _mouse_move(self, x: float, y: float, steps: int = 1) -> None:
        if self.mouse_move_raises:
            raise RuntimeError("mouse move failed")
        self.mouse_moves.append((x, y, steps))

    async def _keyboard_press(self, key: str) -> None:
        self.keyboard_presses.append(key)
        if not self.keyboard_press_updates_sliders or self.focused_selector is None:
            return
        attr_key = (self.focused_selector, "aria-valuenow")
        current = int(round(float(self.attribute_values.get(attr_key, "50"))))
        if key == "ArrowRight":
            self.attribute_values[attr_key] = str(min(100, current + 1))
        elif key == "ArrowLeft":
            self.attribute_values[attr_key] = str(max(0, current - 1))

    async def _keyboard_type(self, text: str, delay: int = 0) -> None:
        if self.keyboard_type_raises:
            raise RuntimeError("keyboard type failed")
        self.typed_texts.append((text, delay))


class FakeContext(SimpleNamespace):
    """VisitContext-shaped fake for direct step tests."""

    page: FakePage
    counters: dict[str, int]
    extracted: dict[str, Any]
    sink: FakeSink

    def increment(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount


def make_ctx(page: FakePage) -> FakeContext:
    """Build a minimal step context."""
    return FakeContext(page=page, counters={}, extracted={}, sink=FakeSink(), _skip_gentle_pause=True)


def test_verify_create_page_ready_blocks_known_platform_state() -> None:
    """Known blocked page states should stop before filling or submitting."""
    ctx = make_ctx(FakePage(["quota_unavailable.html"]))
    request = SongRequest.from_prompt("An original song about a blocked state.")

    result = asyncio.run(VerifyCreatePageReady(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "blocked:quota_unavailable"
    assert ctx.counters == {"suno.blocked_states_detected": 1}
    assert ctx.sink.events[0][0] == "generation_blocked"
    assert ctx.sink.events[0][1]["reason"] == "quota_unavailable"
    assert classify_generation_outcome([result]) == "blocked"


def test_verify_create_page_ready_accepts_ready_state() -> None:
    """Ready pages should pass the submit-capable readiness gate."""
    ctx = make_ctx(FakePage(["create_ready.html"]))
    request = SongRequest.from_prompt("An original song about a ready create page.")

    result = asyncio.run(VerifyCreatePageReady(request).execute(ctx))

    assert result.outcome == "ok"
    assert result.extracted.ready_for_prompt is True


def test_verify_create_page_ready_rejects_disabled_submit() -> None:
    """Submit-capable generation should stop when create is disabled."""
    ctx = make_ctx(FakePage(["create_disabled.html"]))
    request = SongRequest.from_prompt("An original song about a disabled create button.")

    result = asyncio.run(VerifyCreatePageReady(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create button is disabled"


def test_verify_create_page_ready_rejects_missing_create_button() -> None:
    """Submit-capable generation should require a visible create control."""
    ctx = make_ctx(FakePage(["create_no_button.html"]))
    request = SongRequest.from_prompt("An original song about a missing create button.")

    result = asyncio.run(VerifyCreatePageReady(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create button is not visible"


def test_verify_create_page_ready_rejects_missing_prompt() -> None:
    """Submit-capable generation should require a prompt input."""
    ctx = make_ctx(FakePage(["unauthenticated.html"]))
    request = SongRequest.from_prompt("An original song about a missing prompt.")

    result = asyncio.run(VerifyCreatePageReady(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "blocked:auth_required"


def test_verify_create_page_fillable_allows_visible_prompt_with_quota_block() -> None:
    """Fill-only preview should allow prompt entry when quota blocks submission."""
    ctx = make_ctx(FakePage(["quota_unavailable.html"]))
    request = SongRequest.from_prompt("An original song about filling a visible prompt.")

    result = asyncio.run(VerifyCreatePageFillable(request).execute(ctx))

    assert result.outcome == "ok"
    assert result.extracted["blocked_reason"] == "quota_unavailable"
    assert result.extracted["fill_only"] is True
    assert ctx.counters == {"suno.blocked_states_detected": 1}
    assert ctx.extracted["suno_fill_only_blocked_reason"] == "quota_unavailable"
    assert ctx.sink.events == []


def test_verify_create_page_fillable_blocks_unauthenticated_page() -> None:
    """Fill-only preview should still stop before unauthenticated pages."""
    ctx = make_ctx(FakePage(["unauthenticated.html"]))
    request = SongRequest.from_prompt("An original song about missing auth.")

    result = asyncio.run(VerifyCreatePageFillable(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "blocked:auth_required"
    assert ctx.sink.events[0][0] == "generation_blocked"


def test_select_advanced_mode_clicks_advanced_tab() -> None:
    """Advanced requests should switch the create form before filling."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={ADVANCED_TAB_SELECTORS.selectors[0]}))
    request = SongRequest.from_mapping({"prompt": "An original song about advanced controls.", "advanced_mode": True})

    result = asyncio.run(SelectAdvancedMode(request).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.page.clicks == [ADVANCED_TAB_SELECTORS.selectors[0]]


def test_looks_like_cover_reference_context_matches_compact_reference_card_text() -> None:
    """Compact relationship cards should be identifiable from their short labels."""

    assert _looks_like_cover_reference_context("Cover of\nLimites")
    assert _looks_like_cover_reference_context("Remaster of\nHengist Cyning 4")
    assert _looks_like_cover_reference_context("Edit of\nSomething")
    assert _looks_like_cover_reference_context("Remix of\nSomething")
    assert not _looks_like_cover_reference_context("Alex M\nCover of\nLimites\n36")


def test_song_menu_candidate_sort_key_prefers_main_song_controls_over_cover_reference_card() -> None:
    """Main song action controls should outrank the compact cover-reference card menu."""

    cover_card_key = _song_menu_candidate_sort_key(
        box={"x": 612.0, "y": 259.5, "width": 28.0, "height": 28.0},
        viewport_width=1365.0,
        shallow_context_texts=["", "", "Cover of\nLimites"],
    )
    main_song_key = _song_menu_candidate_sort_key(
        box={"x": 644.8, "y": 321.0, "width": 40.0, "height": 28.0},
        viewport_width=1365.0,
        shallow_context_texts=["", "36", "36"],
    )

    assert main_song_key < cover_card_key


def test_select_advanced_mode_requires_tab_selector() -> None:
    """Advanced mode should fail clearly when the tab cannot be found."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))
    request = SongRequest.from_mapping({"prompt": "An original song about missing advanced mode.", "advanced_mode": True})

    result = asyncio.run(SelectAdvancedMode(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Advanced tab selector not found"
    assert [event[0] for event in ctx.sink.events] == ["ui_click", "generation_failed"]
    assert ctx.sink.events[0][1]["selector_group"] == ADVANCED_TAB_SELECTORS.name
    assert ctx.sink.events[0][1]["outcome"] == "skipped"


def test_fill_suno_request_routes_custom_mode_to_advanced_lyrics() -> None:
    """custom_mode/lyrics requests fill via the Advanced layout (no Simple description box)."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about careful launches.",
            "lyrics": "We launch when the sky is clear",
            "custom_mode": True,
        }
    )
    assert request.uses_advanced_controls is True
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={LYRICS_INPUT_SELECTORS.selectors[0]}))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "ok"
    assert result.extracted["advanced_mode"] is True
    assert ctx.counters == {"suno.generations_requested": 1, "suno.requests_loaded": 1}
    assert ctx.sink.events[0][0] == "request_loaded"
    assert ctx.sink.events[0][1]["prompt"] == "An original song about careful launches."
    assert ctx.page.fills == [
        (LYRICS_INPUT_SELECTORS.selectors[0], "We launch when the sky is clear"),
    ]


def test_fill_suno_request_reports_unverified_advanced_lyrics() -> None:
    """Requested lyrics must read back before the request is treated as loaded."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about careful launches.",
            "lyrics": "We launch when the sky is clear",
            "custom_mode": True,
        }
    )
    selector = LYRICS_INPUT_SELECTORS.selectors[0]
    ctx = make_ctx(
        FakePage(
            ["create_ready.html"],
            selectors={selector},
            no_value_after_fill_selectors={selector},
        )
    )

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Lyrics input selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"
    assert "request_loaded" not in [event[0] for event in ctx.sink.events]


def test_fill_suno_request_routes_style_to_advanced_layout() -> None:
    """A style-only request fills via the Advanced layout where the Styles control exists."""
    request = SongRequest.from_mapping({"prompt": "An original song about bright mornings.", "style": "bright acoustic pop"})
    assert request.uses_advanced_controls is True
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={STYLE_INPUT_SELECTORS.selectors[0]}))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "ok"
    assert result.extracted["advanced_mode"] is True
    assert ctx.page.fills == [(STYLE_INPUT_SELECTORS.selectors[0], "bright acoustic pop")]


def test_fill_first_available_skips_hidden_duplicate_controls() -> None:
    """Live Suno can render hidden duplicates before the visible control."""
    selector = TITLE_INPUT_SELECTORS.selectors[0]
    page = FakePage(
        ["create_ready.html"],
        selectors={selector},
        selector_counts={selector: 2},
        hidden_selector_indexes={(selector, 0)},
    )

    filled = asyncio.run(_fill_first_available(page, (selector,), "Careful Sparks"))

    assert filled is True
    assert page.fills == [(selector, "Careful Sparks")]
    assert page.fill_indexes == [(selector, 1)]


def test_fill_first_available_uses_direct_fill_without_pointer_click() -> None:
    """Text controls should avoid hover-prone pointer clicks and verify direct fill."""
    selector = TITLE_INPUT_SELECTORS.selectors[0]
    page = FakePage(
        ["create_ready.html"],
        selectors={selector},
        supports_keyboard_type=True,
    )

    filled = asyncio.run(_fill_first_available(page, (selector,), "Careful Sparks"))

    assert filled is True
    assert page.fills == [(selector, "Careful Sparks")]
    assert page.typed_texts == []
    assert page.clicks == []
    assert page.mouse_moves == []
    assert page.mouse_clicks == []


def test_fill_first_available_continues_after_unverified_selector() -> None:
    """A visible but wrong selector must not let a requested text field look loaded."""
    stale_selector = LYRICS_INPUT_SELECTORS.selectors[-1]
    good_selector = LYRICS_INPUT_SELECTORS.selectors[1]
    page = FakePage(
        ["create_ready.html"],
        selectors={stale_selector, good_selector},
        supports_keyboard_type=True,
        no_value_after_fill_selectors={stale_selector},
    )

    filled = asyncio.run(_fill_first_available(page, (stale_selector, good_selector), "Fallback Title"))

    assert filled is True
    assert page.fills == [(stale_selector, "Fallback Title"), (good_selector, "Fallback Title")]
    assert page.typed_texts == []
    assert page.clicks == []


def test_click_locator_uses_locator_click_even_when_mouse_api_exists() -> None:
    """UI controls should avoid random coordinate mouse clicks."""
    selector = CREATE_BUTTON_SELECTORS.selectors[0]
    page = FakePage(
        ["create_ready.html"],
        selectors={selector},
        supports_mouse_move=True,
    )
    target = page.locator(selector).first

    asyncio.run(_click_locator(page, target))

    assert page.clicks == [selector]
    assert page.mouse_moves == []
    assert page.mouse_clicks == []


def test_click_locator_with_evidence_records_failed_click() -> None:
    """Semantic click evidence should record selector attribution on click failures."""

    class FailingTarget:
        async def bounding_box(self) -> dict[str, float]:
            return {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}

        async def click(self) -> None:
            raise RuntimeError("target click failed")

    page = FakePage(["create_ready.html"])
    ctx = make_ctx(page)

    try:
        asyncio.run(
            _click_locator_with_evidence(
                page,
                FailingTarget(),
                ctx=ctx,
                selector_group="create_button",
                selector="button:has-text('Create')",
                selector_index=2,
                phase="submit",
                source="unit_test",
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "target click failed"

    assert ctx.sink.events[0][0] == "ui_click"
    assert ctx.sink.events[0][1]["outcome"] == "failed"
    assert ctx.sink.events[0][1]["selector_index"] == 2
    assert ctx.sink.events[0][1]["error"] == "target click failed"


def test_type_and_diagnostic_small_helpers() -> None:
    """Small helper branches should stay covered without live browser work."""
    selector = TITLE_INPUT_SELECTORS.selectors[0]
    page = FakePage(["create_ready.html"], selectors={selector})
    target = page.locator(selector).first

    typed = asyncio.run(_type_into_locator(page, target, "No keyboard API"))

    assert typed is False
    assert _typing_delay_ms(None) == 30
    assert _safe_url_path("") == ""
    assert _safe_url_path("create?draft=1") == "create"


def test_text_fill_readback_helpers_cover_defensive_paths() -> None:
    """Text readback helpers should fail closed when a control cannot verify."""

    class FillRaises:
        async def fill(self, value: str) -> None:
            del value
            raise RuntimeError("fill failed")

    class InputRaisesThenEvaluate:
        async def input_value(self) -> str:
            raise RuntimeError("input read failed")

        async def evaluate(self, script: str) -> str:
            del script
            return "  readback value  "

    class EvaluateRaises:
        async def input_value(self) -> None:
            return None

        async def evaluate(self, script: str) -> str:
            del script
            raise RuntimeError("evaluate failed")

    assert asyncio.run(steps_module._fill_locator_value(FillRaises(), "value")) is False
    assert asyncio.run(steps_module._text_field_value(InputRaisesThenEvaluate())) == "  readback value  "
    assert asyncio.run(steps_module._text_field_value(EvaluateRaises())) == ""
    assert asyncio.run(steps_module._wait_for_locator_value(EvaluateRaises(), "missing", timeout_seconds=0.01)) is False
    assert steps_module._normalise_text_field_value(" value\r\n") == "value"


def test_click_and_baseline_defensive_helpers() -> None:
    """Small submit-safety helpers should cover no-box and already-baselined paths."""

    class NoBoxTarget:
        def __init__(self) -> None:
            self.clicked = False

        async def bounding_box(self) -> None:
            raise RuntimeError("no box")

        async def click(self) -> None:
            self.clicked = True

    target = NoBoxTarget()
    payload = asyncio.run(steps_module._click_locator(FakePage(["create_ready.html"]), target))
    assert payload == {"method": "locator"}
    assert target.clicked is True

    ctx = make_ctx(FakePage(["create_ready.html"]))
    ctx.extracted["suno_pre_fill_result_keys"] = {"existing"}
    asyncio.run(steps_module._capture_pre_fill_result_baseline(ctx))
    assert ctx.extracted["suno_pre_fill_result_keys"] == {"existing"}


def test_slider_and_pause_defensive_helpers() -> None:
    """Slider readback and pause helpers should cover no-op and invalid-value branches."""
    selector = WEIRDNESS_SLIDER_SELECTORS.selectors[0]
    ctx = make_ctx(
        FakePage(
            ["create_ready.html"],
            selectors={selector},
        )
    )
    ctx.page.attribute_values[(selector, "aria-valuenow")] = "58"

    assert asyncio.run(steps_module._set_slider_first_available(ctx, (selector,), 58)) is True
    assert ctx.page.keyboard_presses == []

    target = ctx.page.locator(selector).first
    ctx.page.attribute_values[(selector, "aria-valuenow")] = "not-a-number"
    assert asyncio.run(steps_module._slider_current_value(target)) is None

    asyncio.run(steps_module._nudge_slider_to_value(ctx, current_value=42, target_value=42))
    assert ctx.page.keyboard_presses == []

    no_pause_ctx = make_ctx(FakePage(["create_ready.html"]))
    no_pause_ctx._skip_gentle_pause = False
    asyncio.run(steps_module._gentle_key_pause(no_pause_ctx, min_seconds=0, max_seconds=0))
    no_pause_ctx.rng = SimpleNamespace(uniform=lambda _min, _max: 0)
    asyncio.run(steps_module._gentle_key_pause(no_pause_ctx, min_seconds=0, max_seconds=0))


def test_fill_suno_request_fills_advanced_controls() -> None:
    """Advanced requests should fill deterministic text, button, and slider controls."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original art pop song about careful launches.",
            "advanced_mode": True,
            "title": "Careful Launch",
            "lyrics": "The checklist glows beside the door",
            "style": "art pop, warm synths, odd percussion",
            "exclude_styles": "metal, harsh noise",
            "vocal_gender": "female",
            "style_mode": "auto",
            "weirdness": 70,
            "style_influence": 30,
        }
    )
    selectors = {
        LYRICS_INPUT_SELECTORS.selectors[0],
        STYLE_INPUT_SELECTORS.selectors[0],
        TITLE_INPUT_SELECTORS.selectors[0],
        EXCLUDE_STYLES_INPUT_SELECTORS.selectors[0],
        MORE_OPTIONS_SELECTORS.selectors[0],
        FEMALE_VOCAL_SELECTORS.selectors[0],
        AUTO_STYLE_MODE_SELECTORS.selectors[0],
        WEIRDNESS_SLIDER_SELECTORS.selectors[0],
        STYLE_INFLUENCE_SLIDER_SELECTORS.selectors[0],
    }
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=selectors))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.page.fills == [
        (LYRICS_INPUT_SELECTORS.selectors[0], "The checklist glows beside the door"),
        (STYLE_INPUT_SELECTORS.selectors[0], "art pop, warm synths, odd percussion"),
        (TITLE_INPUT_SELECTORS.selectors[0], "Careful Launch"),
        (EXCLUDE_STYLES_INPUT_SELECTORS.selectors[0], "metal, harsh noise"),
    ]
    assert ctx.page.clicks == [
        FEMALE_VOCAL_SELECTORS.selectors[0],
        AUTO_STYLE_MODE_SELECTORS.selectors[0],
    ]
    assert ctx.page.focuses == [
        WEIRDNESS_SLIDER_SELECTORS.selectors[0],
        STYLE_INFLUENCE_SLIDER_SELECTORS.selectors[0],
    ]
    assert ctx.page.keyboard_presses == (["ArrowRight"] * 20) + (["ArrowLeft"] * 20)
    assert result.extracted["advanced_mode"] is True
    assert result.extracted["weirdness"] == 70
    assert result.extracted["style_influence"] == 30
    event_names = [event[0] for event in ctx.sink.events]
    assert event_names == ["ui_click", "ui_click", "request_loaded"]
    assert ctx.sink.events[0][1]["selector_group"] == FEMALE_VOCAL_SELECTORS.name
    assert ctx.sink.events[1][1]["selector_group"] == AUTO_STYLE_MODE_SELECTORS.name
    request_loaded = ctx.sink.events[2][1]
    assert request_loaded["advanced_mode"] is True


def test_fill_suno_request_fills_advanced_button_variants() -> None:
    """Advanced male/manual/instrumental branches should use their buttons."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original instrumental cue about careful launches.",
            "advanced_mode": True,
            "instrumental": True,
            "vocal_gender": "male",
            "style_mode": "manual",
        }
    )
    selectors = {
        MORE_OPTIONS_SELECTORS.selectors[0],
        INSTRUMENTAL_SELECTORS.selectors[0],
        MALE_VOCAL_SELECTORS.selectors[0],
        MANUAL_STYLE_MODE_SELECTORS.selectors[0],
    }
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=selectors))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.page.clicks == [
        INSTRUMENTAL_SELECTORS.selectors[0],
        MALE_VOCAL_SELECTORS.selectors[0],
        MANUAL_STYLE_MODE_SELECTORS.selectors[0],
    ]


def test_fill_suno_request_reports_missing_advanced_lyrics_selector() -> None:
    """Advanced lyrics should fail clearly when no lyrics control is available."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about missing lyrics controls.",
            "advanced_mode": True,
            "lyrics": "The form has no lyrics box",
        }
    )
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Lyrics input selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"


def test_fill_suno_request_reports_missing_advanced_slider() -> None:
    """Advanced slider requests should fail clearly when no usable slider is available."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about missing sliders.",
            "advanced_mode": True,
            "weirdness": 45,
        }
    )
    ctx = make_ctx(
        FakePage(
            ["create_ready.html"],
            selectors={WEIRDNESS_SLIDER_SELECTORS.selectors[0]},
            no_value_selectors={WEIRDNESS_SLIDER_SELECTORS.selectors[0]},
        )
    )

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Weirdness slider selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"


def test_fill_suno_request_reports_unverified_advanced_slider() -> None:
    """Slider fill must read back the requested value before the request is loaded."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about a stuck slider.",
            "advanced_mode": True,
            "style_influence": 92,
        }
    )
    ctx = make_ctx(
        FakePage(
            ["create_ready.html"],
            selectors={STYLE_INFLUENCE_SLIDER_SELECTORS.selectors[0]},
            keyboard_press_updates_sliders=False,
        )
    )

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Style influence slider selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"
    assert "request_loaded" not in [event[0] for event in ctx.sink.events]


def test_fill_suno_request_opens_more_options_before_advanced_levers() -> None:
    """Hidden Advanced levers should trigger the More Options expander first."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about hidden advanced options.",
            "advanced_mode": True,
            "weirdness": 45,
        }
    )
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={MORE_OPTIONS_SELECTORS.selectors[0]}))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Weirdness slider selector not found"
    assert ctx.page.clicks == [MORE_OPTIONS_SELECTORS.selectors[0]]


def test_fill_suno_request_requires_style_selector_when_style_requested() -> None:
    """Style requests should fail clearly when no style control is available."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about missing style controls.",
            "style": "bright acoustic pop",
        }
    )
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={PROMPT_INPUT_SELECTORS.selectors[0]}))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Style input selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"


def test_fill_suno_request_requires_prompt_selector() -> None:
    """The generation plan must not submit if the prompt field is missing."""
    request = SongRequest.from_prompt("An original song about missing controls.")
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Prompt input selector not found"


def test_submit_generation_requires_create_button_selector() -> None:
    """Submitting should fail clearly when no create selector matches."""
    ctx = make_ctx(FakePage(["create_no_button.html"], selectors=set()))
    request = SongRequest.from_prompt("An original song about a missing submit selector.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create button is not visible"
    assert ctx.sink.events[0][0] == "generation_pre_submit"
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "create_click_skipped",
        "generation_failed",
    ]
    assert ctx.sink.events[1][1]["reason"] == "create_button_not_visible"


def test_submit_generation_clicks_create_button_and_records_event() -> None:
    """Submitting should click one create control and emit a traceable event."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    request = SongRequest.from_prompt("An original song about submitting once.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.requests_submitted": 1}
    assert ctx.page.clicks == [CREATE_BUTTON_SELECTORS.selectors[0]]
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "ui_click",
        "create_click_attempted",
        "generation_submitted",
    ]
    assert ctx.sink.events[1][1]["selector_group"] == CREATE_BUTTON_SELECTORS.name
    assert ctx.sink.events[1][1]["selector"] == CREATE_BUTTON_SELECTORS.selectors[0]
    assert ctx.sink.events[2][1]["source"] == "submit_generation.create_button"
    assert ctx.sink.events[3][1]["attempt"] == 1
    assert ctx.sink.events[3][1]["request_id"]
    assert ctx.sink.events[3][1]["pre_submit_diagnostics"]["url_path"] == "/create"


def test_submit_generation_skips_if_create_was_already_attempted() -> None:
    """A run-local submit guard should prevent accidental duplicate Create clicks."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    ctx.extracted["suno_submit_generation_clicked"] = True
    request = SongRequest.from_prompt("An original song about duplicate submit guards.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create click was already attempted in this run"
    assert ctx.page.clicks == []
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "create_click_skipped",
        "generation_failed",
    ]
    assert ctx.sink.events[1][1]["reason"] == "create_click_already_attempted"


def test_submit_generation_skips_if_generation_started_before_submit_phase() -> None:
    """If filling triggered generation activity, the official submit must not click again."""
    ctx = make_ctx(FakePage(["create_with_new_song.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    ctx.extracted["suno_pre_fill_result_keys"] = set()
    request = SongRequest.from_prompt("An original song about pre-submit activity.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Generation activity detected before official Create click"
    assert ctx.page.clicks == []
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "create_click_skipped",
        "generation_failed",
    ]
    assert ctx.sink.events[1][1]["reason"] == "generation_activity_before_submit"
    assert ctx.sink.events[1][1]["diagnostics"]["pre_submit_new_result_count"] > 0


def test_pre_submit_inspection_records_diagnostics_without_clicking_create() -> None:
    """Confirm-submit mode should stop before the high-value create action."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    request = SongRequest.from_prompt("An original song about inspecting before submit.")

    result = asyncio.run(PreSubmitInspection(request).execute(ctx))

    assert result.outcome == "ok"
    assert result.extracted["submit_deferred"] is True
    assert ctx.page.clicks == []
    assert ctx.sink.events[0][0] == "generation_pre_submit"
    assert ctx.sink.events[0][1]["diagnostics"]["create_button_enabled"] is True


def test_pre_submit_inspection_blocks_manual_verification_without_clicking() -> None:
    """Confirm-submit mode should record and stop on visible manual verification."""
    ctx = make_ctx(FakePage(["manual_verification.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    request = SongRequest.from_prompt("An original song about inspection blocks.")

    result = asyncio.run(PreSubmitInspection(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "blocked:manual_verification_required"
    assert ctx.page.clicks == []
    assert [event[0] for event in ctx.sink.events] == ["generation_pre_submit", "generation_blocked"]


def test_pre_submit_diagnostics_records_timing_values() -> None:
    """Submit diagnostics should include safe path and monotonic timing values."""
    page = FakePage(["create_ready.html"])
    page.url = "https://suno.com/create?draft=abc"
    ctx = make_ctx(page)
    ctx.extracted["suno_request_advanced_mode"] = True
    ctx.extracted["suno_request_loaded_monotonic"] = 10.0
    ctx.extracted["suno_create_page_ready_monotonic"] = 9.0
    state = steps_module.CreatePageState(
        authenticated=True,
        prompt_input_visible=True,
        create_button_visible=True,
        create_button_enabled=True,
    )

    diagnostics = asyncio.run(_pre_submit_diagnostics(ctx, state))

    assert diagnostics["url_path"] == "/create"
    assert diagnostics["advanced_mode"] is True
    assert diagnostics["seconds_since_request_loaded"] >= 0
    assert diagnostics["seconds_since_ready_check"] >= diagnostics["seconds_since_request_loaded"]


def test_pre_submit_diagnostics_records_challenge_frame_counts() -> None:
    """Submit diagnostics should include provider counts without frame URLs or tokens."""
    page = FakePage(
        ["create_ready.html"],
        evaluate_values=[
            {
                "challenge_frame_count": 3,
                "visible_challenge_frame_count": 1,
                "challenge_frame_providers": {"hcaptcha": 2, "cloudflare": 1},
            }
        ],
    )
    ctx = make_ctx(page)
    state = steps_module.CreatePageState(authenticated=True)

    diagnostics = asyncio.run(_pre_submit_diagnostics(ctx, state))

    assert diagnostics["challenge_frame_count"] == 3
    assert diagnostics["visible_challenge_frame_count"] == 1
    assert diagnostics["challenge_frame_providers"] == {"hcaptcha": 2, "cloudflare": 1}


def test_challenge_frame_diagnostics_is_defensive() -> None:
    """Challenge diagnostics should omit unsafe or malformed browser results."""
    no_evaluate = SimpleNamespace(url="https://suno.com/create")
    assert asyncio.run(_challenge_frame_diagnostics(no_evaluate)) == {}

    error_page = FakePage(["create_ready.html"], evaluate_error=True)
    assert asyncio.run(_challenge_frame_diagnostics(error_page)) == {}

    malformed_page = FakePage(["create_ready.html"], evaluate_values=[[]])
    assert asyncio.run(_challenge_frame_diagnostics(malformed_page)) == {}

    provider_fallback_page = FakePage(
        ["create_ready.html"],
        evaluate_values=[
            {
                "challenge_frame_count": "2",
                "visible_challenge_frame_count": 0,
                "challenge_frame_providers": "not a dict",
            }
        ],
    )
    assert asyncio.run(_challenge_frame_diagnostics(provider_fallback_page)) == {
        "challenge_frame_count": 2,
        "visible_challenge_frame_count": 0,
        "challenge_frame_providers": {},
    }


def test_submit_generation_rejects_disabled_create_button_after_pre_submit() -> None:
    """Submit should fail before click when the create button is visible but disabled."""
    ctx = make_ctx(FakePage(["create_disabled.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    request = SongRequest.from_prompt("An original song about a disabled submit.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create button is disabled"
    assert ctx.page.clicks == []
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "create_click_skipped",
        "generation_failed",
    ]
    assert ctx.sink.events[1][1]["reason"] == "create_button_disabled"


def test_submit_generation_reports_create_selector_disappearing_after_state_check() -> None:
    """Submit should report selector drift if state has a button but selectors no longer match."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))
    request = SongRequest.from_prompt("An original song about selector drift.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create button selector not found"
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "ui_click",
        "create_click_skipped",
        "generation_failed",
    ]
    assert ctx.sink.events[1][1]["outcome"] == "skipped"
    assert ctx.sink.events[2][1]["reason"] == "create_button_selector_not_found"


def test_submit_generation_blocks_manual_verification_before_clicking() -> None:
    """Manual verification should be reported as blocked and never clicked around."""
    ctx = make_ctx(FakePage(["manual_verification.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    request = SongRequest.from_prompt("An original song about verification.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "blocked:manual_verification_required"
    assert ctx.page.clicks == []
    assert ctx.counters == {
        "suno.blocked_states_detected": 1,
        "suno.manual_verification_blocks_detected": 1,
    }
    assert [event[0] for event in ctx.sink.events] == [
        "generation_pre_submit",
        "create_click_skipped",
        "generation_blocked",
    ]
    assert ctx.sink.events[1][1]["reason"] == "blocked:manual_verification_required"


def test_first_locator_falls_back_when_locator_has_no_first_property() -> None:
    """The helper should support minimal locator-like objects without first."""
    locator = FakeLocatorWithoutFirst()

    assert _first_locator(locator) is locator


def test_wait_for_generation_result_detects_completed_results() -> None:
    """The wait step should finish when result cards become visible."""
    ctx = make_ctx(FakePage(["generation_in_progress.html", "generation_completed.html"]))
    request = SongRequest.from_prompt("An original song about finished output.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.generations_detected": 2}
    assert len(ctx.extracted["generation_results"]) == 2
    assert ctx.sink.events[0][0] == "generation_completed"
    assert ctx.sink.events[0][1]["result_count"] == 2
    assert classify_generation_outcome([result]) == "completed"


def test_wait_for_generation_result_detects_new_song_against_history() -> None:
    """A new /song/ anchor appearing over the baseline history completes the wait."""
    ctx = make_ctx(FakePage(["create_with_history_songs.html", "create_with_new_song.html"]))
    request = SongRequest.from_prompt("An original song that adds to a populated workspace.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.generations_detected": 1}
    new_results = ctx.extracted["generation_results"]
    assert [r.result_id for r in new_results] == ["cccccccc-1111-2222-3333-444444444444"]
    assert ctx.sink.events[-1][0] == "generation_completed"


def test_wait_for_generation_result_uses_pre_submit_baseline() -> None:
    """The new song is usually already visible by the first poll; the pre-submit
    baseline (captured before clicking Create) is what marks it as new."""
    ctx = make_ctx(FakePage(["create_with_new_song.html"]))
    ctx.extracted["suno_pre_submit_result_keys"] = {
        "aaaaaaaa-1111-2222-3333-444444444444",
        "bbbbbbbb-1111-2222-3333-444444444444",
    }
    request = SongRequest.from_prompt("An original song already shown by the first poll.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "ok"
    assert [r.result_id for r in ctx.extracted["generation_results"]] == ["cccccccc-1111-2222-3333-444444444444"]
    assert ctx.sink.events[-1][0] == "generation_completed"


def test_wait_for_generation_result_waits_while_generation_in_progress() -> None:
    """A new song still shown as generating must not complete until progress clears."""
    ctx = make_ctx(FakePage(["create_with_history_songs.html", "generation_in_progress.html", "create_with_new_song.html"]))
    request = SongRequest.from_prompt("An original song that finishes after a progress tick.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "ok"
    assert [r.result_id for r in ctx.extracted["generation_results"]] == ["cccccccc-1111-2222-3333-444444444444"]


def test_wait_for_generation_result_classifies_prompt_rejection_as_blocked() -> None:
    """Prompt rejection should produce blocked, not generic failed, outcome."""
    ctx = make_ctx(FakePage(["policy_rejected.html"]))
    request = SongRequest.from_prompt("An original song that the UI rejects.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "blocked:policy_rejected"
    assert ctx.counters == {"suno.blocked_states_detected": 1, "suno.policy_blocks_detected": 1}
    assert ctx.sink.events[0][0] == "generation_blocked"
    assert classify_generation_outcome([result]) == "blocked"


def test_wait_for_generation_result_times_out_to_pending() -> None:
    """A bounded-wait timeout after submit is a soft pending result, not a hard failure."""
    ctx = make_ctx(FakePage(["create_ready.html"]))
    request = SongRequest.from_prompt("An original song that times out.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=0.1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.generation_pending": 1}
    assert ctx.extracted["suno_generation_pending"] is True
    assert ctx.sink.events[-1][0] == "generation_pending"
    assert ctx.sink.events[-1][1]["reason"] == "result_not_confirmed_within_timeout"
    assert classify_generation_outcome([result]) == "completed"


def test_wait_for_generation_result_ignores_preexisting_history_songs() -> None:
    """Songs already present on the first poll are the baseline and do not count as new."""
    ctx = make_ctx(FakePage(["generation_completed.html"]))
    request = SongRequest.from_prompt("An original song with prior history visible.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=0.2, poll_interval_seconds=0).execute(ctx))

    # The two history cards are the baseline, so no new result -> soft pending.
    assert result.outcome == "ok"
    assert ctx.counters == {"suno.generation_pending": 1}
    assert "generation_results" not in ctx.extracted


def test_collect_generated_song_links_writes_output_file(tmp_path: Path) -> None:
    """The collection step should export visible generated-song links."""

    output_path = tmp_path / "songs.json"
    ctx = make_ctx(FakePage(["library_with_songs.html"]))

    result = asyncio.run(
        CollectGeneratedSongLinks(
            output_path=output_path,
            source_url="https://suno.com/library",
            timeout_seconds=0.1,
            poll_interval_seconds=0,
        ).execute(ctx)
    )

    assert result.outcome == "ok"
    assert result.extracted["result_count"] == 3
    assert ctx.counters == {"suno.song_links_collected": 3}
    assert ctx.sink.events[0][0] == "song_links_collected"
    assert output_path.exists()
    assert classify_song_collection_outcome([result]) == "completed"


def test_collect_generated_song_links_blocks_unauthenticated_page(tmp_path: Path) -> None:
    """Collection should stop before writing when the library requires auth."""

    output_path = tmp_path / "songs.json"
    ctx = make_ctx(FakePage(["library_unauthenticated.html"]))

    result = asyncio.run(
        CollectGeneratedSongLinks(
            output_path=output_path,
            source_url="https://suno.com/library",
            timeout_seconds=0.1,
            poll_interval_seconds=0,
        ).execute(ctx)
    )

    assert result.outcome == "fail"
    assert result.error == "blocked:auth_required"
    assert ctx.counters == {"suno.song_link_collection_blocked": 1}
    assert ctx.sink.events[0][0] == "song_links_failed"
    assert not output_path.exists()
    assert classify_song_collection_outcome([result]) == "blocked"


def test_download_generated_songs_writes_results_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The download step should write a result file when all requested audio downloads succeed."""

    output_dir = tmp_path / "audio"
    output_path = tmp_path / "downloads.json"
    ctx = make_ctx(FakePage(["library_with_songs.html"]))
    songs = [GeneratedSongLink(title="Camden, 1892 -v1", url="https://suno.com/song/song_abc", song_id="song_abc")]

    async def fake_resolve_song_download_targets(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return songs

    async def fake_download_generated_song_audio(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [
            SongDownloadResult(
                url="https://suno.com/song/song_abc",
                title="Camden, 1892 -v1",
                song_id="song_abc",
                download_format="mp3",
                outcome="downloaded",
                output_path=str(output_dir / "Camden, 1892 -v1.mp3"),
                suggested_filename="Camden, 1892 -v1.mp3",
            )
        ]

    monkeypatch.setattr("suno_assistant.steps._resolve_song_download_targets", fake_resolve_song_download_targets)
    monkeypatch.setattr("suno_assistant.steps._download_generated_song_audio", fake_download_generated_song_audio)

    result = asyncio.run(
        DownloadGeneratedSongs(
            source_url="https://suno.com/playlist/example",
            output_dir=output_dir,
            output_path=output_path,
            download_formats=("mp3",),
        ).execute(ctx)
    )

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.song_audio_downloaded": 1}
    assert ctx.sink.events[0][0] == "song_downloads_completed"
    assert output_path.exists()
    assert classify_song_download_outcome([result]) == "completed"


def test_download_generated_songs_reports_blocked_or_failed_assets(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    """The download step should serialize partial success and blocked assets as a failed run."""

    output_dir = tmp_path / "audio"
    output_path = tmp_path / "downloads.json"
    ctx = make_ctx(FakePage(["library_with_songs.html"]))
    songs = [
        GeneratedSongLink(
            title="Camden, 1892 -v1",
            url="https://suno.com/song/song_abc",
            song_id="song_abc",
        )
    ]

    async def fake_resolve_song_download_targets(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return songs

    async def fake_download_generated_song_audio(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return [
            SongDownloadResult(
                url="https://suno.com/song/song_abc",
                title="Camden, 1892 -v1",
                song_id="song_abc",
                download_format="mp3",
                outcome="downloaded",
                output_path=str(output_dir / "Camden, 1892 -v1.mp3"),
                suggested_filename="Camden, 1892 -v1.mp3",
            ),
            SongDownloadResult(
                url="https://suno.com/song/song_abc",
                title="Camden, 1892 -v1",
                song_id="song_abc",
                download_format="wav",
                outcome="blocked",
                error="blocked:wav_requires_pro",
            ),
        ]

    monkeypatch.setattr("suno_assistant.steps._resolve_song_download_targets", fake_resolve_song_download_targets)
    monkeypatch.setattr("suno_assistant.steps._download_generated_song_audio", fake_download_generated_song_audio)

    result = asyncio.run(
        DownloadGeneratedSongs(
            source_url="https://suno.com/playlist/example",
            output_dir=output_dir,
            output_path=output_path,
            download_formats=("mp3", "wav"),
        ).execute(ctx)
    )

    assert result.outcome == "fail"
    assert result.error == "1 blocked song audio download(s)"
    assert ctx.counters == {"suno.song_audio_downloaded": 1, "suno.song_audio_downloads_blocked": 1}
    assert ctx.sink.events[0][0] == "song_downloads_failed"
    assert output_path.exists()
    assert classify_song_download_outcome([result]) == "blocked"


def test_rename_generated_songs_updates_titles_and_writes_results(tmp_path: Path) -> None:
    """The rename step should visit song pages, edit titles, save, and write a report."""

    output_path = tmp_path / "rename-results.json"
    selectors = {
        SONG_MORE_MENU_SELECTORS.selectors[0],
        SONG_TITLE_EDIT_SELECTORS.selectors[0],
        SONG_TITLE_INPUT_SELECTORS.selectors[0],
        SONG_TITLE_SAVE_SELECTORS.selectors[0],
    }
    ctx = make_ctx(FakePage(["library_with_songs.html"], selectors=selectors))
    renames = [SongRenameRequest(url="https://suno.com/song/song_abc", title="Jonathan Edwards -v1-b")]

    result = asyncio.run(RenameGeneratedSongs(renames=renames, output_path=output_path).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.song_titles_renamed": 1}
    assert ctx.page.gotos == ["https://suno.com/song/song_abc"]
    assert ctx.page.clicks == [SONG_TITLE_SAVE_SELECTORS.selectors[0]]
    assert ctx.page.fills == [(SONG_TITLE_INPUT_SELECTORS.selectors[0], "Jonathan Edwards -v1-b")]
    assert ctx.sink.events[0][0] == "song_renames_completed"
    assert output_path.exists()
    assert classify_song_rename_outcome([result]) == "completed"


def test_rename_generated_songs_reports_missing_edit_control(tmp_path: Path) -> None:
    """Missing rename controls should produce a failed result file."""

    output_path = tmp_path / "rename-results.json"
    ctx = make_ctx(FakePage(["library_with_songs.html"]))
    renames = [SongRenameRequest(url="https://suno.com/song/song_abc", title="New Title")]

    result = asyncio.run(RenameGeneratedSongs(renames=renames, output_path=output_path).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "1 song rename(s) failed"
    assert ctx.counters == {"suno.song_title_renames_failed": 1}
    assert ctx.sink.events[0][0] == "song_renames_failed"
    assert output_path.exists()
    assert classify_song_rename_outcome([result]) == "failed"


def test_resolve_song_download_targets_accepts_direct_song_url() -> None:
    """Single-song URLs should bypass library-page scraping."""

    ctx = make_ctx(FakePage(["library_with_songs.html"]))

    targets = asyncio.run(_resolve_song_download_targets(ctx, "https://suno.com/song/song_abc"))

    assert isinstance(targets, list)
    assert targets == [GeneratedSongLink(title=None, url="https://suno.com/song/song_abc", song_id="song_abc")]
    assert _generated_song_link_from_url("https://suno.com/library") is None


def test_resolve_song_download_targets_reports_blocked_library(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Blocked library pages should write a failure event before download attempts."""

    ctx = make_ctx(FakePage(["library_unauthenticated.html"]))

    async def fake_collect(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return SongLinksPageState(authenticated=False, blocked_reason="auth_required")

    monkeypatch.setattr(steps_module, "_collect_song_links_until_stable", fake_collect)

    result = asyncio.run(_resolve_song_download_targets(ctx, "https://suno.com/library"))

    assert result.name == "resolve_song_download_targets"
    assert result.outcome == "fail"
    assert result.error == "blocked:auth_required"
    assert ctx.counters == {"suno.song_downloads_blocked": 1}
    assert ctx.sink.events[0][0] == "song_downloads_failed"


def test_collect_song_links_until_stable_scrolls_until_count_stops(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Collection should keep the largest seen song list while scrolling."""

    states = [
        SongLinksPageState(authenticated=True, songs=[GeneratedSongLink(title="A", url="https://suno.com/song/a")]),
        SongLinksPageState(
            authenticated=True,
            songs=[
                GeneratedSongLink(title="A", url="https://suno.com/song/a"),
                GeneratedSongLink(title="B", url="https://suno.com/song/b"),
            ],
        ),
        SongLinksPageState(
            authenticated=True,
            songs=[
                GeneratedSongLink(title="A", url="https://suno.com/song/a"),
                GeneratedSongLink(title="B", url="https://suno.com/song/b"),
            ],
        ),
    ]

    async def fake_extract(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        return states.pop(0)

    monkeypatch.setattr(steps_module, "extract_song_links_page_state", fake_extract)
    page = FakePage(["library_with_songs.html"], evaluate_values=[100, 100, 100])
    ctx = make_ctx(page)

    state = asyncio.run(
        _collect_song_links_until_stable(ctx, base_url="https://suno.com/library", max_scroll_rounds=2, stable_rounds=1)
    )

    assert len(state.songs) == 2
    assert page.evaluate_calls[0][0].startswith("() => Math.max")
    assert page.evaluate_calls[1][0] == "window.scrollTo(0, document.body.scrollHeight)"


def test_download_generated_song_audio_runs_requested_formats(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """The audio helper should collect one result for each requested format."""

    async def fake_download_format(ctx, *, song, output_dir, download_format):  # type: ignore[no-untyped-def]
        del ctx, output_dir
        return SongDownloadResult(
            url=song.url,
            title=song.title,
            song_id=song.song_id,
            download_format=download_format,
            outcome="downloaded",
        )

    monkeypatch.setattr(steps_module, "_download_generated_song_format", fake_download_format)
    ctx = make_ctx(FakePage(["library_with_songs.html"]))
    song = GeneratedSongLink(title="Song", url="https://suno.com/song/song_abc", song_id="song_abc")

    results = asyncio.run(_download_generated_song_audio(ctx, song=song, output_dir=tmp_path, formats=("mp3", "wav")))

    assert [result.download_format for result in results] == ["mp3", "wav"]


def test_download_generated_song_format_saves_valid_download(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """A visible menu and valid downloaded file should produce a downloaded result."""

    selectors = {
        SONG_MORE_MENU_SELECTORS.selectors[0],
        SONG_DOWNLOAD_ACTION_SELECTORS.selectors[0],
        SONG_DOWNLOAD_MP3_SELECTORS.selectors[0],
    }
    page = FakePage(["library_with_songs.html"], selectors=selectors)
    page.next_download = FakeDownload("Suno Song.mp3")
    ctx = make_ctx(page)
    song = GeneratedSongLink(title="Suno Song", url="https://suno.com/song/song_abc", song_id="song_abc")
    monkeypatch.setattr(steps_module, "_open_song_download_menu", lambda ctx: asyncio.sleep(0, result=True))
    monkeypatch.setattr(steps_module, "validate_downloaded_song_file", lambda path, song_id: (True, song_id, None))

    result = asyncio.run(_download_generated_song_format(ctx, song=song, output_dir=tmp_path, download_format="mp3"))

    assert result.outcome == "downloaded"
    assert result.output_path == str(tmp_path / "Suno Song.mp3")
    assert result.verified_song_id == "song_abc"
    assert page.gotos == ["https://suno.com/song/song_abc"]


def test_download_generated_song_format_reports_auth_required() -> None:
    """Authenticated-only song pages should block downloads explicitly."""

    page = FakePage(["library_unauthenticated.html"], selectors={AUTH_REQUIRED_SELECTORS.selectors[0]})
    ctx = make_ctx(page)
    song = GeneratedSongLink(title="Locked", url="https://suno.com/song/song_abc", song_id="song_abc")

    result = asyncio.run(_download_generated_song_format(ctx, song=song, output_dir=Path("."), download_format="mp3"))

    assert result.outcome == "blocked"
    assert result.error == "blocked:auth_required"


def test_download_generated_song_format_reports_missing_menu_and_action(tmp_path: Path) -> None:
    """Missing menu/action controls should be reported as serialized failures."""

    song = GeneratedSongLink(title="Song", url="https://suno.com/song/song_abc", song_id="song_abc")
    no_menu_result = asyncio.run(
        _download_generated_song_format(
            make_ctx(FakePage(["library_with_songs.html"])), song=song, output_dir=tmp_path, download_format="mp3"
        )
    )

    action_only = FakePage(
        ["library_with_songs.html"],
        selectors={SONG_MORE_MENU_SELECTORS.selectors[0], SONG_DOWNLOAD_ACTION_SELECTORS.selectors[0]},
    )
    no_mp3_result = asyncio.run(
        _download_generated_song_format(make_ctx(action_only), song=song, output_dir=tmp_path, download_format="mp3")
    )

    assert no_menu_result.outcome == "failed"
    assert no_menu_result.error == "Song download menu not found"
    assert no_mp3_result.outcome == "failed"
    assert no_mp3_result.error == "MP3 download action not found"


def test_download_generated_song_format_classifies_pro_timeout(tmp_path: Path) -> None:
    """A timeout on a Pro-labeled action should become a blocked result."""

    selectors = {
        SONG_MORE_MENU_SELECTORS.selectors[0],
        SONG_DOWNLOAD_ACTION_SELECTORS.selectors[0],
        SONG_DOWNLOAD_MP3_SELECTORS.selectors[0],
    }
    page = FakePage(["library_with_songs.html"], selectors=selectors)
    page.locator_texts[(SONG_DOWNLOAD_MP3_SELECTORS.selectors[0], 0)] = "Download MP3 Pro"
    page.expect_download_raises = steps_module.PlaywrightTimeoutError("timeout")
    ctx = make_ctx(page)
    song = GeneratedSongLink(title="Song", url="https://suno.com/song/song_abc", song_id="song_abc")

    result = asyncio.run(_download_generated_song_format(ctx, song=song, output_dir=tmp_path, download_format="mp3"))

    assert result.outcome == "blocked"
    assert result.error == "blocked:mp3_requires_pro"
    assert _download_timeout_reason(download_format="wav", button_text=None) == "WAV download did not start"


def test_open_song_download_menu_dismisses_failed_candidates() -> None:
    """Menu probing should dismiss overlays when no download submenu appears."""

    page = FakePage(["library_with_songs.html"], selectors={SONG_MORE_MENU_SELECTORS.selectors[0]})
    ctx = make_ctx(page)

    opened = asyncio.run(_open_song_download_menu(ctx))

    assert opened is False
    assert page.keyboard_presses == ["Escape"]
    assert page.mouse_clicks == []


def test_open_song_download_menu_clicks_download_action() -> None:
    """Menu probing should click the nested download action when it appears."""

    page = FakePage(
        ["library_with_songs.html"],
        selectors={SONG_MORE_MENU_SELECTORS.selectors[0], SONG_DOWNLOAD_ACTION_SELECTORS.selectors[0]},
    )
    ctx = make_ctx(page)

    opened = asyncio.run(_open_song_download_menu(ctx))

    assert opened is True
    assert page.clicks == [SONG_MORE_MENU_SELECTORS.selectors[0], SONG_DOWNLOAD_ACTION_SELECTORS.selectors[0]]


def test_ranked_song_menu_candidates_scores_visible_boxes() -> None:
    """Candidate ranking should deduplicate by box and prefer main-song controls."""

    selector = SONG_MORE_MENU_SELECTORS.selectors[0]
    page = FakePage(
        ["library_with_songs.html"], selectors={selector}, selector_counts={selector: 3}, viewport_size={"width": 1000}
    )
    page.bounding_boxes[(selector, 0)] = {"x": 820, "y": 50, "width": 10, "height": 10}
    page.bounding_boxes[(selector, 1)] = {"x": 50, "y": 70, "width": 10, "height": 10}
    page.bounding_boxes[(selector, 2)] = {"x": 50, "y": 70, "width": 10, "height": 10}
    page.locator_evaluate_values[(selector, 0)] = ["Cover of Example"]
    page.locator_evaluate_values[(selector, 1)] = ["Main song"]

    candidates = asyncio.run(_ranked_song_menu_candidates(page))

    assert [(candidate.selector, candidate.index) for candidate in candidates] == [(selector, 1), (selector, 0)]


def test_rename_generated_song_handles_auth_input_and_enter_paths() -> None:
    """Direct rename helper should cover blocked, missing-input, and Enter-save branches."""

    rename = SongRenameRequest(url="https://suno.com/song/song_abc", title="New Title")

    blocked = asyncio.run(
        steps_module._rename_generated_song(
            make_ctx(FakePage(["library_unauthenticated.html"], selectors={AUTH_REQUIRED_SELECTORS.selectors[0]})),
            rename,
        )
    )
    missing_input = asyncio.run(
        steps_module._rename_generated_song(
            make_ctx(FakePage(["library_with_songs.html"], selectors={SONG_TITLE_EDIT_SELECTORS.selectors[0]})),
            rename,
        )
    )
    page = FakePage(["library_with_songs.html"], selectors={SONG_TITLE_INPUT_SELECTORS.selectors[0]})
    renamed = asyncio.run(steps_module._rename_generated_song(make_ctx(page), rename))

    assert blocked.outcome == "failed"
    assert blocked.error == "blocked:auth_required"
    assert missing_input.error == "Song title edit control not found"
    assert renamed.outcome == "renamed"
    assert page.keyboard_presses == ["Enter"]


def test_open_song_title_editor_supports_more_menu_path() -> None:
    """The title editor can be opened through the song menu fallback."""

    page = FakePage(
        ["library_with_songs.html"],
        selectors={
            SONG_MORE_MENU_SELECTORS.selectors[0],
            SONG_TITLE_EDIT_SELECTORS.selectors[0],
            SONG_TITLE_INPUT_SELECTORS.selectors[0],
        },
    )

    assert asyncio.run(_open_song_title_editor(make_ctx(page))) is True


def test_small_page_and_locator_helpers() -> None:
    """Small defensive helpers should handle absent APIs and conversion failures."""

    page = FakePage(["library_with_songs.html"], evaluate_values=[720, "bad"], evaluate_error=False)
    assert asyncio.run(_page_viewport_width(page)) == 720.0
    assert asyncio.run(_page_scroll_height(page)) == 0
    assert asyncio.run(_page_viewport_width(FakePage(["library_with_songs.html"], evaluate_error=True))) is None
    assert asyncio.run(_page_scroll_height(FakePage(["library_with_songs.html"], evaluate_error=True))) == 0
    assert asyncio.run(_locator_text(FakeLocator(FakePage(["library_with_songs.html"]), "missing"))) is None


def test_unique_download_output_path_adds_suffixes(tmp_path: Path) -> None:
    """Duplicate suggested filenames should get song-id and attempt suffixes."""

    (tmp_path / "song.mp3").write_bytes(b"one")
    (tmp_path / "song [abcdef12].mp3").write_bytes(b"two")

    path = _unique_download_output_path(
        output_dir=tmp_path,
        suggested_filename="song.mp3",
        song_id="abcdef12-0000-0000-0000-000000000000",
    )

    assert path == tmp_path / "song [abcdef12-2].mp3"


def test_click_and_dismiss_helpers_tolerate_missing_controls() -> None:
    """Optional low-level UI helpers should return false or swallow UI cleanup errors."""

    page = FakePage(["library_with_songs.html"])

    async def raise_press(_key: str) -> None:
        raise RuntimeError("keyboard unavailable")

    async def raise_click(_x: float, _y: float) -> None:
        raise RuntimeError("mouse unavailable")

    page.keyboard = SimpleNamespace(press=raise_press)
    page.mouse = SimpleNamespace(click=raise_click)

    assert asyncio.run(_click_first_available(page, ("missing",))) is False
    asyncio.run(_dismiss_song_overlay(make_ctx(page)))


def test_wait_for_song_page_interactive_observes_visible_control() -> None:
    """The interactive wait should stop once a song control appears."""

    ctx = make_ctx(FakePage(["library_with_songs.html"], selectors={SONG_MORE_MENU_SELECTORS.selectors[0]}))
    delattr(ctx, "_skip_gentle_pause")

    asyncio.run(_wait_for_song_page_interactive(ctx, timeout_seconds=0.1))

    assert ctx.page.load_state_calls == [("networkidle", 10000)]

"""Tests for Suno generation visit steps."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from suno_assistant.requests import SongRequest
from suno_assistant.selectors import (
    ADVANCED_TAB_SELECTORS,
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
    STYLE_INFLUENCE_SLIDER_SELECTORS,
    STYLE_INPUT_SELECTORS,
    TITLE_INPUT_SELECTORS,
    WEIRDNESS_SLIDER_SELECTORS,
)
from suno_assistant.steps import (
    FillSunoRequest,
    SelectAdvancedMode,
    SubmitGeneration,
    VerifyCreatePageFillable,
    VerifyCreatePageReady,
    WaitForGenerationResult,
    _fill_first_available,
    _first_locator,
    classify_generation_outcome,
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

    async def click(self) -> None:
        self.page.clicks.append(self.selector)

    async def is_visible(self) -> bool:
        if (self.selector, self.index) in self.page.hidden_selector_indexes:
            return False
        return self.selector not in self.page.hidden_selectors

    async def focus(self) -> None:
        self.page.focuses.append(self.selector)

    async def get_attribute(self, name: str) -> str | None:
        if name != "aria-valuenow" or self.selector in self.page.no_value_selectors:
            return None
        return "50"

    async def bounding_box(self) -> dict[str, float] | None:
        if self.selector not in self.page.available_selectors:
            return None
        if self.selector in self.page.no_box_selectors:
            return None
        return {"x": 10.0, "y": 20.0, "width": 100.0, "height": 10.0}


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
    ) -> None:
        self.fixture_names = fixture_names
        self.available_selectors = selectors or set()
        self.selector_counts = selector_counts or {}
        self.no_box_selectors = no_box_selectors or set()
        self.no_value_selectors = no_value_selectors or set()
        self.hidden_selectors = hidden_selectors or set()
        self.hidden_selector_indexes = hidden_selector_indexes or set()
        self.content_calls = 0
        self.fills: list[tuple[str, str]] = []
        self.fill_indexes: list[tuple[str, int]] = []
        self.clicks: list[str] = []
        self.focuses: list[str] = []
        self.mouse_clicks: list[tuple[float, float]] = []
        self.mouse = SimpleNamespace(click=self._mouse_click)
        self.keyboard_presses: list[str] = []
        self.keyboard = SimpleNamespace(press=self._keyboard_press)

    async def content(self) -> str:
        index = min(self.content_calls, len(self.fixture_names) - 1)
        self.content_calls += 1
        return (FIXTURE_DIR / self.fixture_names[index]).read_text(encoding="utf-8")

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    async def _mouse_click(self, x: float, y: float) -> None:
        self.mouse_clicks.append((x, y))

    async def _keyboard_press(self, key: str) -> None:
        self.keyboard_presses.append(key)


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


def test_select_advanced_mode_requires_tab_selector() -> None:
    """Advanced mode should fail clearly when the tab cannot be found."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))
    request = SongRequest.from_mapping({"prompt": "An original song about missing advanced mode.", "advanced_mode": True})

    result = asyncio.run(SelectAdvancedMode(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Advanced tab selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"


def test_fill_suno_request_fills_prompt_and_required_lyrics() -> None:
    """The fill step should apply request fields through selector fallbacks."""
    request = SongRequest.from_mapping(
        {
            "prompt": "An original song about careful launches.",
            "lyrics": "We launch when the sky is clear",
            "custom_mode": True,
        }
    )
    selectors = {
        PROMPT_INPUT_SELECTORS.selectors[0],
        LYRICS_INPUT_SELECTORS.selectors[0],
    }
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=selectors))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.generations_requested": 1, "suno.requests_loaded": 1}
    assert ctx.sink.events[0][0] == "request_loaded"
    assert ctx.sink.events[0][1]["prompt"] == "An original song about careful launches."
    assert ctx.sink.events[0][1]["request_id"]
    assert ctx.page.fills == [
        (PROMPT_INPUT_SELECTORS.selectors[0], "An original song about careful launches."),
        (LYRICS_INPUT_SELECTORS.selectors[0], "We launch when the sky is clear"),
    ]


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
    assert ctx.sink.events[0][0] == "request_loaded"
    assert ctx.sink.events[0][1]["advanced_mode"] is True


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
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))
    request = SongRequest.from_prompt("An original song about a missing submit selector.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Create button selector not found"
    assert ctx.sink.events[0][0] == "generation_failed"


def test_submit_generation_clicks_create_button_and_records_event() -> None:
    """Submitting should click one create control and emit a traceable event."""
    ctx = make_ctx(FakePage(["create_ready.html"], selectors={CREATE_BUTTON_SELECTORS.selectors[0]}))
    request = SongRequest.from_prompt("An original song about submitting once.")

    result = asyncio.run(SubmitGeneration(request).execute(ctx))

    assert result.outcome == "ok"
    assert ctx.counters == {"suno.requests_submitted": 1}
    assert ctx.page.clicks == [CREATE_BUTTON_SELECTORS.selectors[0]]
    assert ctx.sink.events[0][0] == "generation_submitted"
    assert ctx.sink.events[0][1]["attempt"] == 1
    assert ctx.sink.events[0][1]["request_id"]


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


def test_wait_for_generation_result_times_out() -> None:
    """Bounded waiting should fail instead of looping indefinitely."""
    ctx = make_ctx(FakePage(["create_ready.html"]))
    request = SongRequest.from_prompt("An original song that times out.")

    result = asyncio.run(WaitForGenerationResult(request, timeout_seconds=0.1, poll_interval_seconds=0).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Timed out waiting for generation result"
    assert ctx.sink.events[0][0] == "generation_failed"
    assert ctx.sink.events[0][1]["phase"] == "wait_for_generation_result"
    assert classify_generation_outcome([result]) == "failed"

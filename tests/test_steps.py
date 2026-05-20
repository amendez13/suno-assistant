"""Tests for Suno generation visit steps."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from suno_assistant.requests import SongRequest
from suno_assistant.selectors import CREATE_BUTTON_SELECTORS, LYRICS_INPUT_SELECTORS, PROMPT_INPUT_SELECTORS
from suno_assistant.steps import (
    FillSunoRequest,
    SubmitGeneration,
    VerifyCreatePageReady,
    WaitForGenerationResult,
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

    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    async def count(self) -> int:
        return 1 if self.selector in self.page.available_selectors else 0

    def first(self) -> "FakeLocator":
        return self

    async def fill(self, value: str) -> None:
        self.page.fills.append((self.selector, value))

    async def click(self) -> None:
        self.page.clicks.append(self.selector)


class FakePage:
    """Minimal Playwright page fake backed by fixture HTML."""

    def __init__(self, fixture_names: list[str], *, selectors: set[str] | None = None) -> None:
        self.fixture_names = fixture_names
        self.available_selectors = selectors or set()
        self.content_calls = 0
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []

    async def content(self) -> str:
        index = min(self.content_calls, len(self.fixture_names) - 1)
        self.content_calls += 1
        return (FIXTURE_DIR / self.fixture_names[index]).read_text(encoding="utf-8")

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)


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
    return FakeContext(page=page, counters={}, extracted={}, sink=FakeSink())


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


def test_fill_suno_request_requires_prompt_selector() -> None:
    """The generation plan must not submit if the prompt field is missing."""
    request = SongRequest.from_prompt("An original song about missing controls.")
    ctx = make_ctx(FakePage(["create_ready.html"], selectors=set()))

    result = asyncio.run(FillSunoRequest(request).execute(ctx))

    assert result.outcome == "fail"
    assert result.error == "Prompt input selector not found"


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

"""Main entry point for Suno Assistant."""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import sys
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import gsv
from gsv.browser import BrowserManager
from gsv.config import SiteConfig, VisitorConfig
from gsv.config.loader import load_config
from gsv.observability import RunRef, SessionRecorder
from gsv.pacing import build_pacing
from gsv.visit import VisitContext, VisitResult, VisitRunner

from .logging_config import configure_logging
from .release_info import get_release_info
from .requests import SongRequest, SongRequestError, load_song_request
from .visit import build_plan as build_create_plan

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectSummary:
    """Human-readable description of the Suno Assistant project boundary."""

    name: str = "Suno Assistant"
    site_name: str = "suno"
    target_site: str = "suno.com"
    create_url: str = "https://suno.com/create"
    config_path: str = "config/config.yaml"
    framework_package: str = "gentle-site-visitor"
    framework_import: str = "gsv"


@dataclass(frozen=True)
class ResolvedRunConfig:
    """Resolved runtime config for one create-page smoke visit."""

    visitor: VisitorConfig
    site: SiteConfig


def describe_project() -> ProjectSummary:
    """Return the project identity and framework dependency boundary."""
    return ProjectSummary()


def dependency_summary() -> str:
    """Return a short dependency summary used by smoke tests and startup logs."""
    summary = describe_project()
    gsv_name = getattr(gsv, "__name__", summary.framework_import)
    return f"{summary.name} visits {summary.target_site} using {gsv_name} from {summary.framework_package}."


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the local create-page smoke run."""
    summary = describe_project()
    parser = argparse.ArgumentParser(description="Run a bounded Suno create-page smoke visit.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(summary.config_path),
        help="Path to the gsv-compatible YAML config file.",
    )
    parser.add_argument("--headed", action="store_true", help="Run the smoke visit in a visible browser window.")
    parser.add_argument(
        "--keep-open",
        action="store_true",
        help="Keep the headed browser open after the create-page visit until you close the window or interrupt the run.",
    )
    request_group = parser.add_mutually_exclusive_group()
    request_group.add_argument("--request", type=Path, help="Path to a YAML song request file.")
    request_group.add_argument("--prompt", help="One-line original song prompt for a quick request.")
    parser.add_argument("--summary-only", action="store_true", help="Print the dependency summary and exit.")
    return parser.parse_args(argv)


def resolve_song_request(args: argparse.Namespace) -> SongRequest | None:
    """Resolve an optional song request from parsed CLI arguments."""
    if args.request is not None:
        return load_song_request(args.request)
    if args.prompt is not None:
        return SongRequest.from_prompt(args.prompt)
    return None


def load_runtime_config(config_path: Path, *, headed: bool = False) -> ResolvedRunConfig:
    """Load the Suno site config and apply any local CLI overrides."""
    summary = describe_project()
    visitor, site = load_config(config_path, summary.site_name)
    if headed:
        visitor = replace(visitor, headless=False)
    return ResolvedRunConfig(visitor=visitor, site=site)


def open_session_recorder(visitor: VisitorConfig, site: SiteConfig, browser: BrowserManager) -> SessionRecorder | None:
    """Open an observability session recorder when the active config enables it."""
    return SessionRecorder.open(
        sessions_dir=Path(visitor.observability.sessions_dir).expanduser() / site.name,
        mode=visitor.observability.mode,
        run=RunRef(
            id=f"suno-create-{uuid.uuid4().hex[:8]}",
            plan_name=f"{site.name}:create-smoke",
            parameters={"source": "suno_assistant.main"},
            site=site.name,
        ),
        browser_meta_provider=browser.get_browser_metadata,
    )


async def finalize_recording(
    browser: BrowserManager,
    recorder: SessionRecorder | None,
    visit_result: VisitResult | None,
) -> None:
    """Flush browser artifacts and finalize the session manifest."""
    if recorder is None:
        return
    await browser.stop_tracing()
    await browser.finalize_har()
    browser.finalize_video()
    outcome = visit_result.outcome if visit_result is not None else "failed"
    error = visit_result.error if visit_result is not None else None
    recorder.finalize(outcome=outcome, error=error)


async def keep_browser_open(page: Any) -> None:
    """Keep the headed browser session open for manual inspection."""
    LOGGER.info("Keeping headed browser open for inspection; close the window or press Ctrl+C to finish the run.")
    while not page.is_closed():
        await asyncio.sleep(0.5)


async def run_create_visit(
    config_path: Path,
    *,
    headed: bool = False,
    keep_open: bool = False,
    song_request: SongRequest | None = None,
) -> VisitResult:
    """Run a single Suno create-page visit through the gsv runtime."""
    resolved = load_runtime_config(config_path, headed=headed)
    browser = BrowserManager(resolved.visitor, resolved.site, rng=random.Random())
    recorder = open_session_recorder(resolved.visitor, resolved.site, browser)
    visit_result: VisitResult | None = None

    try:
        browser.attach_recorder(recorder)
        await browser.start()
        await browser.enable_har_for_session()
        await browser.start_tracing()
        page = await browser.new_page()
        pacing = build_pacing(resolved.visitor, resolved.site, browser.rate_limiter, rng=random.Random())
        visit_ctx = VisitContext(
            page=page,
            pacing=pacing,
            config=resolved.visitor,
            site=resolved.site,
            rng=random.Random(),
            recorder=recorder,
        )
        visit_result = await VisitRunner(visit_ctx).run(build_create_plan(song_request=song_request))
        if keep_open:
            await keep_browser_open(page)
        return visit_result
    finally:
        await browser.save_session()
        await finalize_recording(browser, recorder, visit_result)
        await browser.close()


def main(argv: list[str] | None = None) -> int:
    """Run the local CLI."""
    args = parse_args(argv)
    configure_logging()
    LOGGER.info(
        "Application startup",
        extra={"event": "startup", "release": get_release_info()},
    )

    print(dependency_summary())
    if args.summary_only:
        return 0
    try:
        song_request = resolve_song_request(args)
    except SongRequestError as exc:
        LOGGER.error("Invalid song request", extra={"event": "song_request_invalid", "error": str(exc)})
        print(f"Invalid song request: {exc}", file=sys.stderr)
        return 2

    result = asyncio.run(
        run_create_visit(args.config, headed=args.headed, keep_open=args.keep_open, song_request=song_request)
    )
    print(f"Run {result.outcome}: {describe_project().site_name}")
    return 0 if result.outcome == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

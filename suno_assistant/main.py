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
from gsv.session import Session
from gsv.visit import VisitContext, VisitResult, VisitRunner
from gsv.visit.plan import StepResult

from .auth import AUTH_REQUIRED_MESSAGE, build_suno_auth_adapter
from .logging_config import configure_logging
from .release_info import get_release_info
from .requests import SongRequest, SongRequestError, load_song_request
from .song_downloads import SongDownloadFormat, resolve_song_download_formats
from .song_links import SongLinkFormat
from .song_renames import SongRenameRequest, load_song_rename_requests
from .visit import SUNO_LIBRARY_URL
from .visit import build_plan as build_create_plan
from .visit import build_song_collection_plan, build_song_download_plan, build_song_rename_plan

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
    parser.add_argument(
        "--login",
        action="store_true",
        help="Run the headed manual Suno login bootstrap and persist local browser storage state.",
    )
    parser.add_argument(
        "--fill-only",
        action="store_true",
        help="Fill a validated song request into the create page without clicking create/generate.",
    )
    parser.add_argument(
        "--confirm-submit",
        action="store_true",
        help=("Fill a validated song request, record pre-submit diagnostics, and stop before clicking create/generate."),
    )
    parser.add_argument(
        "--collect-songs",
        type=Path,
        metavar="OUTPUT",
        help="Collect visible generated-song titles and links from Suno and write them to OUTPUT.",
    )
    parser.add_argument(
        "--songs-url",
        default=SUNO_LIBRARY_URL,
        help="Suno page to inspect when collecting generated-song links.",
    )
    parser.add_argument(
        "--songs-format",
        choices=("json", "jsonl", "markdown"),
        default=None,
        help="Output format for --collect-songs. Defaults to the output file extension.",
    )
    parser.add_argument(
        "--rename-songs",
        type=Path,
        metavar="PLAN",
        help="Rename generated songs from a JSON plan containing URL/title pairs.",
    )
    parser.add_argument(
        "--rename-results",
        type=Path,
        metavar="OUTPUT",
        help="Write generated-song rename results to OUTPUT. Defaults beside the rename plan.",
    )
    parser.add_argument(
        "--download-songs",
        type=Path,
        metavar="DIR",
        help="Download MP3 and/or WAV audio from a Suno playlist page or single song into DIR.",
    )
    parser.add_argument(
        "--download-formats",
        choices=("mp3", "wav", "both"),
        default="mp3",
        help="Audio formats for --download-songs. Defaults to mp3.",
    )
    parser.add_argument(
        "--download-results",
        type=Path,
        metavar="OUTPUT",
        help="Write generated-song download results to OUTPUT. Defaults inside the download directory.",
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


def build_auth_required_result(error: str = AUTH_REQUIRED_MESSAGE) -> VisitResult:
    """Build a blocked visit result for missing or expired Suno auth."""
    return VisitResult(
        outcome="blocked",
        error=error,
        counters={"auth_required": 1},
        extracted={},
        step_results=[StepResult(name="verify_suno_auth", outcome="fail", error=error)],
    )


def build_login_result(*, authenticated: bool) -> VisitResult:
    """Build a synthetic result for the manual login bootstrap path."""
    if authenticated:
        return VisitResult(
            outcome="completed",
            error=None,
            counters={"auth_bootstrap_completed": 1},
            extracted={},
            step_results=[StepResult(name="suno_login_bootstrap", outcome="ok")],
        )
    return build_auth_required_result("Suno login did not reach the authenticated create page before timeout.")


async def run_create_visit(
    config_path: Path,
    *,
    headed: bool = False,
    keep_open: bool = False,
    login: bool = False,
    song_request: SongRequest | None = None,
    fill_only: bool = False,
    confirm_submit: bool = False,
) -> VisitResult:
    """Run a single Suno create-page visit through the gsv runtime."""
    resolved = load_runtime_config(config_path, headed=headed)
    browser = BrowserManager(resolved.visitor, resolved.site, rng=random.Random())
    recorder = open_session_recorder(resolved.visitor, resolved.site, browser)
    session = Session(browser, build_suno_auth_adapter(resolved.site), resolved.visitor, rng=random.Random())
    visit_result: VisitResult | None = None

    try:
        browser.attach_recorder(recorder)
        authenticated = await session.login() if login else await session.start()
        if not authenticated:
            visit_result = build_login_result(authenticated=False) if login else build_auth_required_result()
            return visit_result
        if login:
            visit_result = build_login_result(authenticated=True)
            if keep_open:
                page = await browser.new_page()
                await keep_browser_open(page)
            return visit_result
        post_login_warmup = getattr(session, "post_login_warmup", None)
        if callable(post_login_warmup):
            await post_login_warmup()
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
        visit_result = await VisitRunner(visit_ctx).run(
            build_create_plan(song_request=song_request, fill_only=fill_only, confirm_submit=confirm_submit)
        )
        if keep_open:
            await keep_browser_open(page)
        return visit_result
    finally:
        if session.is_authenticated:
            await browser.save_session()
        await finalize_recording(browser, recorder, visit_result)
        await browser.close()


async def run_song_collection_visit(
    config_path: Path,
    *,
    output_path: Path,
    output_format: SongLinkFormat | None = None,
    source_url: str = SUNO_LIBRARY_URL,
    headed: bool = False,
    keep_open: bool = False,
) -> VisitResult:
    """Run a bounded Suno song-link collection visit through the gsv runtime."""

    resolved = load_runtime_config(config_path, headed=headed)
    browser = BrowserManager(resolved.visitor, resolved.site, rng=random.Random())
    recorder = open_session_recorder(resolved.visitor, resolved.site, browser)
    session = Session(browser, build_suno_auth_adapter(resolved.site), resolved.visitor, rng=random.Random())
    visit_result: VisitResult | None = None

    try:
        browser.attach_recorder(recorder)
        authenticated = await session.start()
        if not authenticated:
            visit_result = build_auth_required_result()
            return visit_result
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
        plan = build_song_collection_plan(
            output_path=output_path,
            output_format=output_format,
            source_url=source_url,
        )
        visit_result = await VisitRunner(visit_ctx).run(plan)
        if keep_open:
            await keep_browser_open(page)
        return visit_result
    finally:
        if session.is_authenticated:
            await browser.save_session()
        await finalize_recording(browser, recorder, visit_result)
        await browser.close()


async def run_song_rename_visit(
    config_path: Path,
    *,
    renames: list[SongRenameRequest],
    output_path: Path,
    headed: bool = False,
    keep_open: bool = False,
) -> VisitResult:
    """Run a bounded generated-song rename visit through the gsv runtime."""

    resolved = load_runtime_config(config_path, headed=headed)
    browser = BrowserManager(resolved.visitor, resolved.site, rng=random.Random())
    recorder = open_session_recorder(resolved.visitor, resolved.site, browser)
    session = Session(browser, build_suno_auth_adapter(resolved.site), resolved.visitor, rng=random.Random())
    visit_result: VisitResult | None = None

    try:
        browser.attach_recorder(recorder)
        authenticated = await session.start()
        if not authenticated:
            visit_result = build_auth_required_result()
            return visit_result
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
        plan = build_song_rename_plan(renames=renames, output_path=output_path)
        visit_result = await VisitRunner(visit_ctx).run(plan)
        if keep_open:
            await keep_browser_open(page)
        return visit_result
    finally:
        if session.is_authenticated:
            await browser.save_session()
        await finalize_recording(browser, recorder, visit_result)
        await browser.close()


async def run_song_download_visit(
    config_path: Path,
    *,
    source_url: str,
    output_dir: Path,
    output_path: Path,
    download_formats: tuple[SongDownloadFormat, ...],
    headed: bool = False,
    keep_open: bool = False,
) -> VisitResult:
    """Run a bounded generated-song audio download visit through the gsv runtime."""

    resolved = load_runtime_config(config_path, headed=headed)
    browser = BrowserManager(resolved.visitor, resolved.site, rng=random.Random())
    recorder = open_session_recorder(resolved.visitor, resolved.site, browser)
    session = Session(browser, build_suno_auth_adapter(resolved.site), resolved.visitor, rng=random.Random())
    visit_result: VisitResult | None = None

    try:
        browser.attach_recorder(recorder)
        authenticated = await session.start()
        if not authenticated:
            visit_result = build_auth_required_result()
            return visit_result
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
        plan = build_song_download_plan(
            source_url=source_url,
            output_dir=output_dir,
            output_path=output_path,
            download_formats=download_formats,
        )
        visit_result = await VisitRunner(visit_ctx).run(plan)
        if keep_open:
            await keep_browser_open(page)
        return visit_result
    finally:
        if session.is_authenticated:
            await browser.save_session()
        await finalize_recording(browser, recorder, visit_result)
        await browser.close()


def _run_song_collection_mode(args: argparse.Namespace) -> int:
    if _collect_songs_conflicts(args):
        print(
            "Invalid song collection request: use --collect-songs without "
            "--login, --fill-only, --confirm-submit, --prompt, --request, or --rename-songs.",
            file=sys.stderr,
        )
        return 2
    result = asyncio.run(
        run_song_collection_visit(
            args.config,
            output_path=args.collect_songs,
            output_format=args.songs_format,
            source_url=args.songs_url,
            headed=args.headed,
            keep_open=args.keep_open,
        )
    )
    count = result.counters.get("suno.song_links_collected", 0)
    print(f"Collected {count} song link(s): {args.collect_songs}")
    print(f"Run {result.outcome}: {describe_project().site_name}")
    return 0 if result.outcome == "completed" else 1


def _run_song_rename_mode(args: argparse.Namespace) -> int:
    if _rename_songs_conflicts(args):
        print(
            "Invalid song rename request: use --rename-songs without --login, --fill-only, --confirm-submit, "
            "--prompt, or --request.",
            file=sys.stderr,
        )
        return 2
    try:
        renames = load_song_rename_requests(args.rename_songs)
    except (OSError, ValueError) as exc:
        print(f"Invalid song rename plan: {exc}", file=sys.stderr)
        return 2
    output_path = args.rename_results or args.rename_songs.with_name(f"{args.rename_songs.stem}.results.json")
    result = asyncio.run(
        run_song_rename_visit(
            args.config,
            renames=renames,
            output_path=output_path,
            headed=args.headed,
            keep_open=args.keep_open,
        )
    )
    renamed = result.counters.get("suno.song_titles_renamed", 0)
    failed = result.counters.get("suno.song_title_renames_failed", 0)
    print(f"Renamed {renamed} song title(s), {failed} failed: {output_path}")
    print(f"Run {result.outcome}: {describe_project().site_name}")
    return 0 if result.outcome == "completed" else 1


def _run_song_download_mode(args: argparse.Namespace) -> int:
    if _download_songs_conflicts(args):
        print(
            "Invalid song download request: use --download-songs without --login, --fill-only, --confirm-submit, "
            "--prompt, --request, --collect-songs, or --rename-songs.",
            file=sys.stderr,
        )
        return 2
    try:
        download_formats = resolve_song_download_formats(args.download_formats)
    except ValueError as exc:
        print(f"Invalid song download request: {exc}", file=sys.stderr)
        return 2
    output_path = args.download_results or args.download_songs / "song-downloads.json"
    result = asyncio.run(
        run_song_download_visit(
            args.config,
            source_url=args.songs_url,
            output_dir=args.download_songs,
            output_path=output_path,
            download_formats=download_formats,
            headed=args.headed,
            keep_open=args.keep_open,
        )
    )
    downloaded = result.counters.get("suno.song_audio_downloaded", 0)
    blocked = result.counters.get("suno.song_audio_downloads_blocked", 0)
    failed = result.counters.get("suno.song_audio_downloads_failed", 0)
    print(f"Downloaded {downloaded} audio file(s), {blocked} blocked, {failed} failed: {output_path}")
    print(f"Run {result.outcome}: {describe_project().site_name}")
    return 0 if result.outcome == "completed" else 1


def _collect_songs_conflicts(args: argparse.Namespace) -> bool:
    return bool(
        args.login
        or args.fill_only
        or args.confirm_submit
        or args.request is not None
        or args.prompt is not None
        or args.rename_songs is not None
        or args.download_songs is not None
    )


def _rename_songs_conflicts(args: argparse.Namespace) -> bool:
    return bool(
        args.login
        or args.fill_only
        or args.confirm_submit
        or args.request is not None
        or args.prompt is not None
        or args.collect_songs is not None
        or args.download_songs is not None
    )


def _download_songs_conflicts(args: argparse.Namespace) -> bool:
    return bool(
        args.login
        or args.fill_only
        or args.confirm_submit
        or args.request is not None
        or args.prompt is not None
        or args.collect_songs is not None
        or args.rename_songs is not None
    )


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - CLI mode dispatch is intentionally centralized here.
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
    if args.login and not args.headed:
        print("Invalid login request: use --headed --login for manual Suno login bootstrap.", file=sys.stderr)
        return 2
    if args.rename_results is not None and args.rename_songs is None:
        print("Invalid song rename request: use --rename-results together with --rename-songs.", file=sys.stderr)
        return 2
    if args.download_results is not None and args.download_songs is None:
        print("Invalid song download request: use --download-results together with --download-songs.", file=sys.stderr)
        return 2
    if args.collect_songs is not None:
        return _run_song_collection_mode(args)
    if args.rename_songs is not None:
        return _run_song_rename_mode(args)
    if args.download_songs is not None:
        return _run_song_download_mode(args)
    try:
        song_request = resolve_song_request(args)
    except SongRequestError as exc:
        LOGGER.error("Invalid song request", extra={"event": "song_request_invalid", "error": str(exc)})
        print(f"Invalid song request: {exc}", file=sys.stderr)
        return 2
    if args.fill_only and song_request is None:
        print("Invalid fill-only request: use --prompt or --request with --fill-only.", file=sys.stderr)
        return 2
    if args.confirm_submit and song_request is None:
        print("Invalid confirm-submit request: use --prompt or --request with --confirm-submit.", file=sys.stderr)
        return 2
    if args.confirm_submit and args.fill_only:
        print("Invalid create request: use either --confirm-submit or --fill-only, not both.", file=sys.stderr)
        return 2

    result = asyncio.run(
        run_create_visit(
            args.config,
            headed=args.headed,
            keep_open=args.keep_open,
            login=args.login,
            song_request=song_request,
            fill_only=args.fill_only,
            confirm_submit=args.confirm_submit,
        )
    )
    print(f"Run {result.outcome}: {describe_project().site_name}")
    return 0 if result.outcome == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

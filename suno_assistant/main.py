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
from urllib.parse import urlparse

import gsv
from gsv.browser import BrowserManager
from gsv.browser.fingerprint import build_viewport
from gsv.browser.primitives import STEALTH_LAUNCH_ARGS, WEBDRIVER_INIT_SCRIPT
from gsv.browser.rate_limit import RateLimiter
from gsv.config import SiteConfig, VisitorConfig
from gsv.config.loader import load_config
from gsv.config.model import RateLimitConfig
from gsv.observability import RunRef, SessionRecorder
from gsv.pacing import build_pacing
from gsv.session import Session
from gsv.session.warmup import post_login_warmup as run_post_login_warmup
from gsv.visit import VisitContext, VisitResult, VisitRunner
from gsv.visit.plan import StepResult
from playwright.async_api import BrowserContext, async_playwright

from .auth import AUTH_REQUIRED_MESSAGE, build_suno_auth_adapter
from .extractors import CreatePageState, extract_create_page_state
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
        "--skip-recording-context-rotation",
        action="store_true",
        help=(
            "Run the create workflow without recreating the browser context for HAR/video recording. "
            "Use this only to diagnose session-continuity issues."
        ),
    )
    parser.add_argument(
        "--persistent-profile-check",
        type=Path,
        metavar="DIR",
        help=(
            "Open Suno with a Playwright persistent profile directory and report auth/challenge state without "
            "filling or submitting."
        ),
    )
    parser.add_argument(
        "--persistent-profile",
        type=Path,
        metavar="DIR",
        help=(
            "Run the create workflow through a persistent browser profile directory instead of ephemeral "
            "storage state. Warmup, fill, and submit all run in the same context with no pre-submit context "
            "rotation, preserving device/session continuity across runs."
        ),
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


def build_persistent_profile_result(*, state: CreatePageState, final_url: str, profile_dir: Path) -> VisitResult:
    """Build a diagnostic result for a persistent-profile auth check."""
    blocked_reason = state.blocked_reason
    authenticated = bool(state.authenticated and blocked_reason is None)
    outcome = "completed" if authenticated else "blocked"
    error = f"blocked:{blocked_reason}" if blocked_reason is not None else None
    if not authenticated and error is None:
        error = "blocked:auth_unconfirmed"
    extracted = {
        "profile_auth_diagnostics": {
            "profile_dir": str(profile_dir),
            "url_path": _safe_url_path(final_url),
            "authenticated": state.authenticated,
            "blocked_reason": blocked_reason,
            "prompt_input_visible": state.prompt_input_visible,
            "create_button_visible": state.create_button_visible,
            "create_button_enabled": state.create_button_enabled,
            "manual_verification_visible": state.diagnostics.get("manual_verification_visible", False),
        }
    }
    return VisitResult(
        outcome=outcome,
        error=error,
        counters={"persistent_profile_auth_check": 1},
        extracted=extracted,
        step_results=[
            StepResult(
                name="persistent_profile_auth_check",
                outcome="ok" if authenticated else "fail",
                error=error,
                extracted=extracted["profile_auth_diagnostics"],
            )
        ],
    )


def _safe_url_path(url: str) -> str:
    """Return a URL path without query parameters or fragments."""
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.path or "/"


async def run_persistent_profile_auth_check(
    config_path: Path,
    *,
    profile_dir: Path,
    headed: bool = False,
    keep_open: bool = False,
) -> VisitResult:
    """Check Suno auth state with a real persistent browser profile."""
    resolved = load_runtime_config(config_path, headed=headed)
    adapter = build_suno_auth_adapter(resolved.site)
    profile_dir = profile_dir.expanduser()
    rng = random.Random()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=resolved.visitor.headless,
            args=STEALTH_LAUNCH_ARGS,
            viewport=build_viewport(
                rng,
                resolved.visitor.fingerprint.viewport_width_range,
                resolved.visitor.fingerprint.viewport_height_range,
            ),
            locale=resolved.site.locale,
            timezone_id=resolved.site.timezone_id,
        )
        await context.add_init_script(WEBDRIVER_INIT_SCRIPT)
        context.set_default_timeout(resolved.site.page_timeout_seconds * 1000)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(adapter.auth_marker_url, wait_until="domcontentloaded")
            state = await extract_create_page_state(page)
            result = build_persistent_profile_result(state=state, final_url=str(page.url), profile_dir=profile_dir)
            if keep_open:
                await keep_browser_open(page)
            return result
        finally:
            await context.close()


def _effective_rate_limit(visitor: VisitorConfig, site: SiteConfig) -> RateLimitConfig:
    """Return the per-site override or visitor-level default rate limit."""
    if site.rate_limit is not None:
        return site.rate_limit
    return RateLimitConfig(requests_per_hour=visitor.pacing.rate_limit_per_hour)


def _build_persistent_har_kwargs(
    *,
    visitor: VisitorConfig,
    site: SiteConfig,
    session_dir: Path | None,
) -> tuple[dict[str, Any], str | None, Path | None]:
    """Build launch kwargs that enable HAR/video recording at context creation."""
    obs = visitor.observability
    kwargs: dict[str, Any] = {}
    if session_dir is None or obs.mode == "off":
        return kwargs, None, None
    har_path: str | None = None
    if obs.har:
        har_path = str(session_dir / "network.har")
        kwargs["record_har_path"] = har_path
        if site.allowed_host_globs:
            kwargs["record_har_url_filter"] = site.allowed_host_globs[0]
        if obs.har_content == "omit":
            kwargs["record_har_content"] = "omit"
    video_dir: Path | None = None
    if obs.video:
        video_dir = session_dir / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)
        kwargs["record_video_dir"] = str(video_dir)
        kwargs["record_video_size"] = {"width": 1280, "height": 800}
    return kwargs, har_path, video_dir


async def _finalize_persistent_artifacts(
    *,
    recorder: SessionRecorder | None,
    har_path: str | None,
    video_dir: Path | None,
) -> None:
    """Register HAR/video artifacts flushed when the persistent context closed."""
    if recorder is None:
        return
    if har_path is not None and Path(har_path).exists():
        recorder.register_artifact("har", har_path)
        LOGGER.info("HAR finalized: %s", har_path)
    if video_dir is not None and video_dir.exists():
        videos = sorted(video_dir.glob("*.webm"))
        if videos:
            primary = recorder.session_dir / "video.webm"
            videos[0].replace(primary)
            for extra_index, extra in enumerate(videos[1:], start=1):
                extra.replace(recorder.session_dir / f"video_{extra_index}.webm")
            recorder.register_artifact("video", str(primary))
        try:
            video_dir.rmdir()
        except OSError:
            LOGGER.debug("Video temp directory not empty: %s", video_dir)


async def run_persistent_create_visit(  # noqa: C901 - keep the persistent create flow together.
    config_path: Path,
    *,
    profile_dir: Path,
    headed: bool = False,
    keep_open: bool = False,
    login: bool = False,
    song_request: SongRequest | None = None,
    fill_only: bool = False,
    confirm_submit: bool = False,
) -> VisitResult:
    """Run the create workflow through a persistent profile with no context rotation.

    Warmup, fill, and submit all run in the same persistent browser context so the
    high-value generation action is not the first action in a freshly created
    context, and device/session continuity is preserved across runs. This is a
    continuity-hardening path, not a CAPTCHA/manual-verification bypass.
    """
    resolved = load_runtime_config(config_path, headed=headed)
    adapter = build_suno_auth_adapter(resolved.site)
    profile_dir = profile_dir.expanduser()
    rng = random.Random()
    viewport = build_viewport(
        rng,
        resolved.visitor.fingerprint.viewport_width_range,
        resolved.visitor.fingerprint.viewport_height_range,
    )

    def browser_meta() -> dict[str, Any]:
        return {
            "headless": resolved.visitor.headless,
            "viewport": dict(viewport),
            "locale": resolved.site.locale,
            "timezone_id": resolved.site.timezone_id,
            "profile": "persistent",
        }

    recorder = SessionRecorder.open(
        sessions_dir=Path(resolved.visitor.observability.sessions_dir).expanduser() / resolved.site.name,
        mode=resolved.visitor.observability.mode,
        run=RunRef(
            id=f"suno-create-{uuid.uuid4().hex[:8]}",
            plan_name=f"{resolved.site.name}:create-persistent",
            parameters={"source": "suno_assistant.main", "profile": "persistent"},
            site=resolved.site.name,
        ),
        browser_meta_provider=browser_meta,
    )
    obs = resolved.visitor.observability
    har_kwargs, har_path, video_dir = _build_persistent_har_kwargs(
        visitor=resolved.visitor,
        site=resolved.site,
        session_dir=recorder.session_dir if recorder is not None else None,
    )

    visit_result: VisitResult | None = None
    tracing_active = False
    context: BrowserContext | None = None
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=resolved.visitor.headless,
            args=STEALTH_LAUNCH_ARGS,
            viewport=viewport,
            locale=resolved.site.locale,
            timezone_id=resolved.site.timezone_id,
            **har_kwargs,
        )
        try:
            await context.add_init_script(WEBDRIVER_INIT_SCRIPT)
            for script in adapter.extra_init_scripts:
                await context.add_init_script(script)
            context.set_default_timeout(resolved.site.page_timeout_seconds * 1000)
            if recorder is not None and obs.mode != "off" and obs.trace:
                await context.tracing.start(screenshots=True, snapshots=True, sources=False)
                tracing_active = True
            page = context.pages[0] if context.pages else await context.new_page()

            await page.goto(adapter.auth_marker_url, wait_until="domcontentloaded")
            authenticated = adapter.is_authenticated_url(str(page.url))
            if login:
                if not authenticated and keep_open:
                    await keep_browser_open(page)
                    authenticated = adapter.is_authenticated_url(str(page.url))
                visit_result = build_login_result(authenticated=authenticated)
                return visit_result
            if not authenticated:
                visit_result = build_auth_required_result()
                return visit_result

            if resolved.visitor.pacing.post_login_warmup and adapter.warmup_url is not None:
                await run_post_login_warmup(page, adapter.warmup_url, rng=rng)

            rate_limiter = RateLimiter(config=_effective_rate_limit(resolved.visitor, resolved.site))
            pacing = build_pacing(resolved.visitor, resolved.site, rate_limiter, rng=rng)
            visit_ctx = VisitContext(
                page=page,
                pacing=pacing,
                config=resolved.visitor,
                site=resolved.site,
                rng=rng,
                recorder=recorder,
            )
            visit_result = await VisitRunner(visit_ctx).run(
                build_create_plan(song_request=song_request, fill_only=fill_only, confirm_submit=confirm_submit)
            )
            if keep_open:
                await keep_browser_open(page)
            return visit_result
        finally:
            if tracing_active and recorder is not None:
                trace_path = recorder.session_dir / "trace.zip"
                try:
                    await context.tracing.stop(path=str(trace_path))
                    recorder.register_artifact("trace", trace_path)
                except Exception:
                    LOGGER.warning("Failed to stop Playwright tracing", exc_info=True)
            await context.close()
            await _finalize_persistent_artifacts(recorder=recorder, har_path=har_path, video_dir=video_dir)
            if recorder is not None:
                outcome = visit_result.outcome if visit_result is not None else "failed"
                error = visit_result.error if visit_result is not None else None
                recorder.finalize(outcome=outcome, error=error)


async def run_create_visit(
    config_path: Path,
    *,
    headed: bool = False,
    keep_open: bool = False,
    login: bool = False,
    song_request: SongRequest | None = None,
    fill_only: bool = False,
    confirm_submit: bool = False,
    skip_recording_context_rotation: bool = False,
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
        if not skip_recording_context_rotation:
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
        or getattr(args, "skip_recording_context_rotation", False)
        or getattr(args, "persistent_profile_check", None) is not None
        or getattr(args, "persistent_profile", None) is not None
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
        or getattr(args, "skip_recording_context_rotation", False)
        or getattr(args, "persistent_profile_check", None) is not None
        or getattr(args, "persistent_profile", None) is not None
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
        or getattr(args, "skip_recording_context_rotation", False)
        or getattr(args, "persistent_profile_check", None) is not None
        or getattr(args, "persistent_profile", None) is not None
        or args.request is not None
        or args.prompt is not None
        or args.collect_songs is not None
        or args.rename_songs is not None
    )


def _persistent_profile_conflicts(args: argparse.Namespace) -> bool:
    return bool(
        args.login
        or args.fill_only
        or args.confirm_submit
        or getattr(args, "skip_recording_context_rotation", False)
        or args.request is not None
        or args.prompt is not None
        or args.collect_songs is not None
        or args.rename_songs is not None
        or args.download_songs is not None
    )


def _run_persistent_profile_check_mode(args: argparse.Namespace) -> int:
    if _persistent_profile_conflicts(args):
        print(
            "Invalid persistent-profile check: use --persistent-profile-check without create, login, collection, "
            "rename, download, or recording-rotation options.",
            file=sys.stderr,
        )
        return 2
    result = asyncio.run(
        run_persistent_profile_auth_check(
            args.config,
            profile_dir=args.persistent_profile_check,
            headed=args.headed,
            keep_open=args.keep_open,
        )
    )
    diagnostics = result.extracted.get("profile_auth_diagnostics", {})
    reason = diagnostics.get("blocked_reason") or (result.error.removeprefix("blocked:") if result.error else "none")
    print(f"Persistent profile auth {result.outcome}: {describe_project().site_name} ({reason})")
    return 0 if result.outcome == "completed" else 1


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
    if args.persistent_profile_check is not None:
        return _run_persistent_profile_check_mode(args)
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
    if args.persistent_profile is not None and args.skip_recording_context_rotation:
        print(
            "Invalid create request: --persistent-profile already avoids context rotation; "
            "do not combine it with --skip-recording-context-rotation.",
            file=sys.stderr,
        )
        return 2

    if args.persistent_profile is not None:
        result = asyncio.run(
            run_persistent_create_visit(
                args.config,
                profile_dir=args.persistent_profile,
                headed=args.headed,
                keep_open=args.keep_open,
                login=args.login,
                song_request=song_request,
                fill_only=args.fill_only,
                confirm_submit=args.confirm_submit,
            )
        )
    else:
        result = asyncio.run(
            run_create_visit(
                args.config,
                headed=args.headed,
                keep_open=args.keep_open,
                login=args.login,
                song_request=song_request,
                fill_only=args.fill_only,
                confirm_submit=args.confirm_submit,
                skip_recording_context_rotation=args.skip_recording_context_rotation,
            )
        )
    print(f"Run {result.outcome}: {describe_project().site_name}")
    return 0 if result.outcome == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

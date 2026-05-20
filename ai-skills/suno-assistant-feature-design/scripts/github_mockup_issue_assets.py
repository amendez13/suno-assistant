#!/usr/bin/env python3
"""Capture mockup screenshots and upload them into a GitHub issue or PR."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

COMMENT_TEXTAREA_SELECTOR = 'textarea[placeholder="Use Markdown to format your comment"]'
ATTACHMENT_URL_RE = re.compile(r"https://github\.com/user-attachments/assets/[0-9a-fA-F-]+")
DEFAULT_AUTH_STATE = Path(".playwright-mcp/auth/github-storage-state.json")
DEFAULT_BROWSER_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


@dataclass(frozen=True)
class SelectorSpec:
    """Describe one screenshot to capture from the mockup page."""

    slug: str
    selector: str


@dataclass(frozen=True)
class CapturedImage:
    """Represent one captured image and its metadata."""

    slug: str
    selector: str
    path: Path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Capture selector-based mockup screenshots and upload them to a GitHub issue or pull request."
    )
    parser.add_argument("--repo", required=True, help="Repository in owner/name form")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--issue", type=int, help="GitHub issue number")
    target_group.add_argument("--pr", type=int, help="GitHub pull request number")
    parser.add_argument("--mockup-url", required=True, help="Local file:// URL or HTTP URL for the mockup")
    parser.add_argument(
        "--selectors",
        required=True,
        help="Path to a newline-separated selector list file. Supports optional slug=selector lines.",
    )
    parser.add_argument(
        "--auth-state",
        default=str(DEFAULT_AUTH_STATE),
        help="Playwright storage state with an authenticated GitHub session",
    )
    parser.add_argument("--output", required=True, help="Output directory for screenshots and metadata")
    parser.add_argument(
        "--browser-path",
        default=str(DEFAULT_BROWSER_PATH),
        help="Preferred browser executable path. Falls back to Playwright Chromium when absent.",
    )
    parser.add_argument("--headless", action="store_true", help="Run the browser headlessly")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="Timeout for upload completion and selector waits",
    )
    return parser.parse_args()


def build_target_url(repo: str, issue: int | None, pr: int | None) -> str:
    """Build the GitHub target URL."""
    if issue is not None:
        return f"https://github.com/{repo}/issues/{issue}"
    if pr is not None:
        return f"https://github.com/{repo}/pull/{pr}"
    raise ValueError("Either issue or pr must be provided.")


def normalize_slug(raw: str) -> str:
    """Normalize free-form text into a filesystem-safe slug."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw.strip()).strip("-").lower()
    if not slug:
        raise ValueError(f"Could not derive a slug from {raw!r}.")
    return slug


def derive_slug_from_selector(selector: str, index: int) -> str:
    """Derive a stable slug when the selector file does not provide one."""
    tokens = [token for token in re.split(r"[^a-zA-Z0-9]+", selector) if token]
    if tokens:
        joined = "-".join(tokens[:4])
        return normalize_slug(f"{index:02d}-{joined}")
    return f"{index:02d}-shot"


def parse_selector_line(raw_line: str, index: int) -> SelectorSpec | None:
    """Parse one selector file line into a selector spec."""
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    explicit_slug_match = re.match(r"^(?P<slug>[A-Za-z0-9_-]+)=(?P<selector>.+)$", line)
    if explicit_slug_match:
        slug = normalize_slug(explicit_slug_match.group("slug"))
        selector = explicit_slug_match.group("selector").strip()
        selector = selector.strip()
        if not selector:
            raise ValueError(f"Missing selector for line: {raw_line!r}")
        return SelectorSpec(slug=slug, selector=selector)
    return SelectorSpec(slug=derive_slug_from_selector(line, index), selector=line)


def load_selectors(selector_file: Path) -> list[SelectorSpec]:
    """Load selector specs from disk."""
    specs: list[SelectorSpec] = []
    for index, raw_line in enumerate(selector_file.read_text(encoding="utf-8").splitlines(), start=1):
        spec = parse_selector_line(raw_line, index)
        if spec is not None:
            specs.append(spec)
    if not specs:
        raise ValueError(f"No selectors found in {selector_file}.")
    return specs


def render_snippet(images: Sequence[CapturedImage], asset_urls: Sequence[str]) -> str:
    """Render the Markdown snippet to embed into an issue or PR body."""
    lines = ["## Visual Guide", ""]
    for image, asset_url in zip(images, asset_urls):
        lines.append(f"### `{image.slug}`")
        lines.append(f"Selector: `{image.selector}`")
        lines.append("")
        lines.append(f"![{image.slug}]({asset_url})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def capture_screenshots(
    page: Any,
    mockup_url: str,
    selectors: Sequence[SelectorSpec],
    output_dir: Path,
) -> list[CapturedImage]:
    """Capture one screenshot per selector."""
    page.goto(mockup_url, wait_until="networkidle")
    captured: list[CapturedImage] = []
    for selector_spec in selectors:
        locator = page.locator(selector_spec.selector).first
        locator.wait_for(state="visible", timeout=30_000)
        image_path = output_dir / f"{selector_spec.slug}.png"
        locator.screenshot(path=str(image_path))
        captured.append(CapturedImage(slug=selector_spec.slug, selector=selector_spec.selector, path=image_path))
    return captured


def upload_images(page: Any, target_url: str, images: Sequence[CapturedImage], timeout_seconds: int) -> list[str]:
    """Upload images via the GitHub comment form and return attachment URLs."""
    page.goto(target_url, wait_until="domcontentloaded")
    textarea = page.locator(COMMENT_TEXTAREA_SELECTOR).first
    textarea.wait_for(state="visible", timeout=30_000)
    textarea.scroll_into_view_if_needed()
    textarea.click()

    with page.expect_file_chooser() as file_chooser_info:
        page.get_by_role("button", name=re.compile("add files", re.IGNORECASE)).click()
    file_chooser = file_chooser_info.value
    file_chooser.set_files([str(image.path) for image in images])

    deadline = time.time() + timeout_seconds
    last_value = ""
    while time.time() < deadline:
        last_value = textarea.input_value()
        urls = ATTACHMENT_URL_RE.findall(last_value)
        if len(urls) >= len(images):
            return urls[: len(images)]
        page.wait_for_timeout(1_000)

    raise RuntimeError(
        "Timed out waiting for GitHub attachment URLs to appear in the comment form. " f"Last textarea value: {last_value!r}"
    )


def write_outputs(
    output_dir: Path,
    target_url: str,
    mockup_url: str,
    images: Sequence[CapturedImage],
    asset_urls: Sequence[str],
) -> None:
    """Write the manifest and Markdown snippet."""
    snippet_path = output_dir / "snippet.md"
    manifest_path = output_dir / "manifest.json"
    snippet = render_snippet(images, asset_urls)
    manifest = {
        "target_url": target_url,
        "mockup_url": mockup_url,
        "images": [
            {
                "slug": image.slug,
                "selector": image.selector,
                "png_path": str(image.path),
                "uploaded_url": asset_url,
            }
            for image, asset_url in zip(images, asset_urls)
        ],
    }
    snippet_path.write_text(snippet, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def run_browser_flow(
    args: argparse.Namespace,
    selectors: Sequence[SelectorSpec],
    output_dir: Path,
) -> tuple[list[CapturedImage], list[str]]:
    """Run the Playwright flow and return captured images and uploaded URLs."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required to run this helper. Install it in your active Python environment.") from exc

    browser_path = Path(args.browser_path).expanduser().resolve()
    launch_kwargs: dict[str, Any] = {"headless": args.headless}
    if browser_path.exists():
        launch_kwargs["executable_path"] = str(browser_path)

    auth_state = Path(args.auth_state).expanduser().resolve()
    if not auth_state.exists():
        raise FileNotFoundError(f"Missing Playwright auth state: {auth_state}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**launch_kwargs)
        context = browser.new_context(storage_state=str(auth_state), viewport={"width": 1600, "height": 1200})
        page = context.new_page()
        images = capture_screenshots(page, args.mockup_url, selectors, output_dir)
        asset_urls = upload_images(page, build_target_url(args.repo, args.issue, args.pr), images, args.timeout_seconds)
        context.close()
        browser.close()
    return images, asset_urls


def main() -> int:
    """Run the CLI."""
    args = parse_args()
    output_dir = Path(args.output).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    selector_file = Path(args.selectors).expanduser().resolve()
    if not selector_file.exists():
        print(f"Selector file does not exist: {selector_file}", file=sys.stderr)
        return 2

    try:
        selectors = load_selectors(selector_file)
        target_url = build_target_url(args.repo, args.issue, args.pr)
        images, asset_urls = run_browser_flow(args, selectors, output_dir)
        write_outputs(output_dir, target_url, args.mockup_url, images, asset_urls)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Uploaded {len(asset_urls)} image(s) to {target_url}")
    print(f"Saved snippet to {output_dir / 'snippet.md'}")
    print(f"Saved manifest to {output_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

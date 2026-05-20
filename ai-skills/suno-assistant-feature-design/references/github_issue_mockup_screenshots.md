# GitHub Issue Mockup Screenshots

Use this workflow when a feature-design task needs local HTML or CSS mockups turned into screenshots and then embedded into a GitHub issue or pull request.

## When to use this

Use it when:
- a visual guide is useful, but browser automation cannot reliably click, type, or upload files
- you already have a local prototype and want a repeatable upload path using authenticated GitHub browser state
- the issue or PR should contain uploaded screenshots instead of raw mockup source

## Preconditions

- Run from the repository root.
- Use a Python environment that has Playwright available.
- GitHub browser auth state should exist at `.playwright-mcp/auth/github-storage-state.json` unless you pass a different `--auth-state`.

## Preferred helper

Use:

```bash
python ai-skills/suno-assistant-feature-design/scripts/github_mockup_issue_assets.py \
  --repo owner/name \
  --issue 123 \
  --mockup-url file:///absolute/path/to/mockup.html \
  --selectors selectors.txt \
  --output .playwright-mcp/issue-123-assets
```

What the helper does:
- opens the local mockup
- captures one PNG per selector
- opens the target GitHub issue or PR
- uploads the PNGs through the GitHub comment form
- extracts the generated `https://github.com/user-attachments/assets/...` URLs
- writes:
  - `<output>/manifest.json`
  - `<output>/snippet.md`

`selectors.txt` should contain one CSS selector per line.
Blank lines and lines starting with `#` are ignored.
If a line is written as `slug=selector`, the slug is used for the output filename.

## Reliable GitHub selectors

The most reliable selectors are:
- comment textarea: `textarea[placeholder="Use Markdown to format your comment"]`
- upload trigger: button with accessible name matching `Add files`

Important behavior:
- after upload, GitHub inserts HTML `<img>` tags into the textarea, not Markdown image syntax
- the durable part is the `src` URL under `https://github.com/user-attachments/assets/...`
- use those asset URLs in the main issue body or PR description

## Recommended post-upload step

After the helper writes `snippet.md`, update the main issue or PR body so the screenshots are the source of truth:
- keep the design narrative and implementation plan
- remove raw prototype HTML or CSS blocks from the body
- replace them with the generated image section and short captions

Typical CLI pattern:

```bash
tmp_body="$(mktemp)"
gh issue view 123 --json body -q .body > "$tmp_body"
# Edit the body file to replace the mockup-source section with the generated Markdown.
gh issue edit 123 --body-file "$tmp_body"
```

## Manifest pattern

The helper records:
- the target URL
- the original mockup URL
- each selector
- the local PNG path
- the uploaded asset URL

That manifest makes it easy to audit which screenshot maps to which selector and uploaded image.

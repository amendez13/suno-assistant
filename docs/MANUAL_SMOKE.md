# Manual Smoke Checks

Use this guide before relying on Suno Assistant for live prompt-to-song runs.
The goal is to verify the MVP path with a low-impact, original request while
keeping account use, generated content, and local artifacts under operator
control.

## Boundaries

- Use only the operator's own Suno account.
- Keep smoke prompts original, low-volume, and low-impact.
- Do not ask the automation to evade quotas, moderation, CAPTCHA, MFA, login
  flows, or other platform controls.
- Do not ask for restricted-artist imitation, copyrighted-work imitation, or
  voice imitation.
- Treat `data/browser/` and `data/sessions/` as sensitive local artifacts.
- Do not paste cookies, storage state, HARs, traces, prompts, generated result
  URLs, or private account details into issues or pull requests.

Live generation can consume account credits or quota. Run the checklist in a
headed browser first so the operator can see the page state before and after the
single submit action.

## 1. Install And Configure

Set up the project and local configuration:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config/config.example.yaml config/config.yaml
```

Confirm the CLI is available:

```bash
python -m suno_assistant.main --help
python -m suno_assistant.main --summary-only
```

## 2. Bootstrap Login

Open a headed browser and complete Suno login manually:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --login
```

Complete any login, MFA, CAPTCHA, consent, or verification step yourself in the
browser. Suno Assistant does not enter credentials, solve challenges, or bypass
platform controls. A successful bootstrap saves local browser state under
`data/browser/suno/state.json`.

If a later run exits with an auth-required blocked result, repeat this bootstrap
command.

## 3. Prepare A Request

For a quick smoke request, prefer a short original prompt:

```bash
python -m suno_assistant.main \
  --prompt "A warm original acoustic pop song about writing a careful checklist before launch."
```

For a structured request, start from the sample:

```bash
cp examples/song-request.yaml /tmp/suno-smoke-request.yaml
```

Use only supported fields:

```yaml
prompt: "A warm original acoustic pop song about writing a careful checklist before launch."
title: "Checklist Morning"
style: "acoustic pop, gentle percussion, bright chorus"
lyrics: "Optional user-provided lyrics"
instrumental: false
custom_mode: false
count: 1
tags:
  - smoke
notes: "Local operator note; stored in request evidence."
```

There is no separate dry-run flag in the MVP CLI. `--prompt` and `--request`
are validated before browser startup, so malformed YAML, unsupported fields,
empty prompts, lyrics on instrumental requests, and restricted imitation prompts
fail before Suno is opened.

## 4. Run The Headed Smoke

Run the bounded generation path in a visible browser:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --request /tmp/suno-smoke-request.yaml
```

Expected behavior:

- The browser opens `https://suno.com/create`.
- The saved session is recognized, or the run exits with an auth-required
  blocked result before filling or submitting anything.
- The prompt and supported optional fields are filled from the request.
- The run performs exactly one create/generate submit action.
- The run waits within the configured timeout for visible results or a known
  blocked state.
- The run does not download audio or retry around quota, policy, CAPTCHA, MFA,
  or other platform controls.

If you need to inspect the page without submitting a request, run the create-page
smoke path without `--prompt` or `--request`:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --keep-open
```

If you need to populate the create box for inspection without submitting, use
fill-only mode:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --keep-open \
  --fill-only \
  --request /tmp/suno-smoke-request.yaml
```

Expected fill-only behavior:

- The browser opens the authenticated create page.
- Supported request fields are filled.
- The run never clicks create/generate.
- The headed browser stays open when `--keep-open` is provided.
- If quota blocks submission but the prompt input is visible, the run can still
  fill the prompt for operator inspection.

To capture submit readiness diagnostics without clicking Create, use
confirm-submit mode:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --keep-open \
  --confirm-submit \
  --request /tmp/suno-smoke-request.yaml
```

Expected confirm-submit behavior:

- The browser opens the authenticated create page.
- Supported request fields are filled.
- A `generation_pre_submit` evidence event records safe page state, button
  readiness, challenge visibility, and timing since request fill.
- The run never clicks create/generate.
- If a CAPTCHA or manual verification challenge is visible, it is recorded as
  `manual_verification_required` and the run stops.

To inspect Advanced mode, use the advanced example request:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --keep-open \
  --fill-only \
  --request examples/advanced-song-request.yaml
```

Expected Advanced fill behavior:

- The Advanced tab is selected.
- Lyrics, Styles, Song Title, Exclude styles, vocal gender, style mode,
  Weirdness, and Style Influence are populated when the matching request fields
  are present.
- More Options remains expanded when `exclude_styles`, `vocal_gender`,
  `style_mode`, `weirdness`, or `style_influence` is requested.
- Weirdness and Style Influence are set from their current slider values to the
  requested percentages.
- Audio, Voice, Inspo, saved style chips, random/generative helper buttons, and
  workspace selectors are left untouched.

For the detailed create-page UI contract, including how hidden duplicate inputs,
More Options, and sliders are handled, see [CREATE_BOX.md](CREATE_BOX.md).

## 5. Inspect Evidence

Find the newest session bundle:

```bash
ls -td data/sessions/suno/* | head -n 1
```

Inspect the manifest and Suno evidence:

```bash
SESSION_DIR="$(ls -td data/sessions/suno/* | head -n 1)"
cat "$SESSION_DIR/manifest.json"
tail -n 50 "$SESSION_DIR/evidence.jsonl"
```

For a successful request-aware smoke run, expect:

- `request_loaded`
- `generation_pre_submit`
- `generation_submitted`
- one terminal event such as `generation_completed`, `generation_blocked`, or
  `generation_failed`

Blocked quota, auth, manual verification, policy, disabled-control, or
prompt-rejection outcomes are valid smoke results when they are explicit,
bounded, and recorded in evidence. Do not add loops or bypass behavior to turn
those states into success.

## 6. Check Git Safety

Confirm no sensitive local artifacts are staged:

```bash
git status --short
git status --short --ignored data config/config.yaml
```

`data/` and `config/config.yaml` should remain ignored. If artifact files are
visible as staged or untracked normal files, stop and fix ignore rules before
opening a pull request.

## 7. Retain Or Purge Artifacts

Keep `data/sessions/` only as long as the evidence, trace, HAR, or video files
are useful for local review. They can include prompts, visible result metadata,
page traces, network metadata, and browser diagnostics.

To purge local session artifacts after review:

```bash
rm -rf data/sessions/suno
```

To clear saved browser login state on this machine:

```bash
rm -f data/browser/suno/state.json
```

Clearing browser state means the next authenticated run will require another
headed login bootstrap.

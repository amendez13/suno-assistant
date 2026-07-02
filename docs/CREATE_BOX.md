# Suno Create Box

This document describes how Suno Assistant treats the Suno create UI from the
operator's point of view. It is intentionally about supported UI behavior, not
about bypassing platform limits or automating account verification.

## Operating Modes

Suno Assistant supports two create-box modes:

1. **Basic fill** uses the default create prompt box and optional supported
   custom-mode fields.
2. **Advanced fill** switches the create page to Suno's Advanced tab and fills
   deterministic controls from a structured request file.

Both modes can run with or without submission:

- Normal request-aware runs fill the supported fields, submit one create action,
  and wait within the configured timeout for visible results or a known blocked
  state.
- `--fill-only` fills supported fields and stops before clicking
  Create/Generate. Use it for headed inspection and manual confirmation.
- `--confirm-submit` fills supported fields, records pre-submit diagnostics,
  and stops before clicking Create/Generate. Use it when diagnosing first-submit
  challenge behavior without spending a generation attempt.

## Request-To-UI Mapping

The request file is the source of truth. Suno Assistant validates it before
browser startup, so unsupported fields, malformed YAML, empty prompts, invalid
slider values, and restricted imitation requests fail before opening Suno.

Basic request fields:

| Request field | UI behavior |
| --- | --- |
| `prompt` | Fills the visible Basic prompt textarea. |
| `style` | Fills the supported style field when present. |
| `lyrics` | Fills the supported lyrics field when present. |
| `instrumental` | Clicks the instrumental control when requested. |
| `custom_mode` | Enables the supported custom-mode control when requested. |
| `count` | Records requested count in evidence; generation submission remains bounded. |
| `tags`, `notes` | Stored in local evidence only; not entered into Suno. |

Advanced request fields:

| Request field | UI behavior |
| --- | --- |
| `advanced_mode` | Selects the Advanced tab before filling fields. |
| `lyrics` | Fills the Advanced lyrics textarea. |
| `style` | Fills the Advanced Styles text area. |
| `title` | Fills the visible Song Title input. |
| `exclude_styles` | Expands More Options when needed, then fills Exclude styles. |
| `vocal_gender` | Clicks Male or Female when requested. |
| `style_mode` | Clicks Manual or Auto when requested. |
| `weirdness` | Sets the Weirdness slider to the requested 0-100 value. |
| `style_influence` | Sets the Style Influence slider to the requested 0-100 value. |
| `instrumental` | Clicks the instrumental control when requested. |

The included example uses Advanced fill-only inspection:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --keep-open \
  --fill-only \
  --request examples/advanced-song-request.yaml
```

For pre-submit diagnostics without an automatic Create click:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --keep-open \
  --confirm-submit \
  --request examples/advanced-song-request.yaml
```

## Advanced UI Behavior

The Advanced tab renders several controls that matter for reliable automation:

- Suno may keep hidden duplicate controls in the DOM. For example, the Song
  Title input can exist once in a hidden header area and once in the visible
  create panel. Suno Assistant iterates matching controls and fills the first
  visible one.
- The More Options controls can remain present in the DOM even while the panel
  is collapsed. Visibility checks are not enough. Suno Assistant reads the
  More Options `aria-expanded` state and clicks the expander only when Suno
  reports the panel as collapsed.
- Text fields are filled through the editable control itself and read back
  before the request is treated as loaded. The lyrics field prefers the visible
  "Start writing lyrics..." textarea so hover-sensitive AI lyric helper prompts
  are not opened by accident.
- Weirdness and Style Influence are slider controls with `aria-valuenow`.
  Coordinate clicks do not reliably change them in the live UI. Suno Assistant
  focuses the visible slider, reads its current value, and gently nudges it with
  keyboard arrow presses until it reaches the requested value. The requested
  value must read back from the slider before the request is treated as loaded.

These details are covered by unit tests and a headed fill-only smoke path. They
also explain why the app treats Advanced controls as deterministic UI controls,
not as free-form page scraping.

## Unsupported Advanced Controls

Suno Assistant intentionally leaves these controls untouched:

- Audio, Voice, and Inspo asset pickers
- saved style chips
- random style or prompt buttons
- lyrics generation or enhancement buttons
- workspace selection
- account, billing, quota, CAPTCHA, MFA, or login controls

Those controls either depend on account-local assets, can invoke additional
generation helpers, or belong to platform/account state. Operators can use them
manually in the headed browser after `--fill-only` leaves the page open.

## Gentle Behavior

Create-box actions stay bounded and paced:

- The app verifies the saved authenticated session before create-page work.
- Request-aware create runs use the framework post-login warmup before the
  create plan starts.
- Request validation happens before browser startup.
- Fill-only mode never clicks Create/Generate.
- Confirm-submit mode records submit-readiness diagnostics and then stops before
  Create/Generate.
- Submission mode performs one create action and waits within a bounded timeout.
- Before the Create action, the app compares visible song results against the
  pre-fill baseline. If generation activity is already visible, it skips Create
  and fails closed instead of risking a second submit.
- Text entry uses direct editable-control fill plus readback verification.
- Clicks and Advanced field actions prefer visible controls, Playwright locator
  actionability, and short human-cadence pauses.
- Slider changes use focused keyboard nudges instead of rapid direct DOM
  mutation.
- Known auth, manual verification, quota, disabled-control, and policy states
  are recorded as explicit blocked/failed outcomes instead of being retried
  around.

Session artifacts can include prompts, traces, HARs, visible result metadata,
and storage-state diagnostics. Keep `data/` local and untracked.

# Observability

This template ships a generic observability pattern that separates service health from run-level debugging.

## Two Layers

### Platform layer

Use the platform layer for service-level visibility:

`journald -> Promtail -> Loki -> Grafana`

This layer answers questions such as:
- Did the unit start?
- Is the service failing repeatedly?
- Are multiple services showing the same error pattern?

### App layer

Use the app layer for run- or task-level debugging:
- structured JSONL logs
- optional session artifact directories
- manifest metadata for a specific run

This layer answers questions such as:
- What happened in this specific task?
- Which phase failed?
- Which structured payloads were emitted during the run?

## When To Use Which Layer

- Service state, startup failures, timer execution, or cross-service history: use the platform layer first.
- One task, one session, one pipeline run, or one batch execution: use the app layer.
- If you do not know whether the process ran at all: start with `systemctl` and `journalctl`, then drill into app-level artifacts if the unit did run.

## Structured Logging Pattern

The template includes `suno_assistant/logging_config.py` with:
- human-readable stderr logging by default
- optional JSONL file output for machine-readable run logs
- `contextvars` correlation fields for `session_id`, `task_id`, and `phase`

Recommended pattern:
1. Call `configure_logging()` at startup.
2. Set correlation fields once at the start of a task or session with `set_log_context(...)`.
3. Attach structured payloads with `extra={...}`.
4. Reset or replace the context when the task boundary changes.

Example:

```python
import logging

from suno_assistant.logging_config import configure_logging, set_log_context

logger = logging.getLogger(__name__)

configure_logging(jsonl_path="data/sessions/run-1/worker.jsonl")
set_log_context(session_id="run-1", task_id="job-42", phase="fetch")
logger.info("Task started", extra={"event": "task_started", "queue": "default"})
```

## Loki Label Conventions

When shipping logs to a shared Loki stack, prefer a stable component label:

```text
component="suno-assistant"
```

That keeps queries predictable across projects:

```logql
{component="suno-assistant"}
```

## systemd Unit Naming

Use unit names that match the component label and the job role:
- `suno-assistant.service`
- `suno-assistant-<job>.service`
- `suno-assistant-<job>.timer`

This keeps service names, Syslog identifiers, and Loki queries aligned.

For long-running jobs, increase `TimeoutStopSec=` beyond the default so in-flight work has time to finalize cleanly before systemd escalates to `SIGKILL`.

## Health Endpoint Pattern

Projects with an HTTP surface should expose a basic liveness endpoint:

### `GET /health`

Recommended payload shape:

```json
{
  "status": "ok",
  "release": {
    "tag": "v1.2.3",
    "commit": "abc123456789",
    "short_commit": "abc1234",
    "source": "env"
  }
}
```

Use `suno_assistant/release_info.py` to populate the release metadata.

### `GET /pipeline/health`

For queue- or pipeline-driven projects, expose richer execution state:

```json
{
  "status": "ok",
  "queue_counts": {
    "pending": 3,
    "processing": 1,
    "failed": 0,
    "completed": 18
  },
  "running_jobs": 1,
  "last_triggered_at": "2026-04-27T08:15:00Z",
  "last_loop_error": null,
  "stale_claim_reconciliation": {
    "status": "ok",
    "requeued": 0
  }
}
```

The purpose is to distinguish queue-empty from queue-blocked, blocked-by-running-work, and broken-loop states.

## Operator Runbook

- Did the unit run?
  `journalctl -u suno-assistant.service -n 100 --no-pager -q`
- What is the current unit state?
  `systemctl status suno-assistant.service --no-pager`
- Need cross-service search or a longer time window?
  Use Loki or Grafana.
- Need to inspect one specific run?
  Use the app-layer JSONL log or session artifacts when the project adopts that pattern.

## Suno Auth Outcomes

Suno Assistant verifies the saved browser session before running create-page
workflows. Missing or expired auth returns a blocked run result with:

- outcome: `blocked`
- counter: `auth_required=1`
- step: `verify_suno_auth`

The operator action is to rerun the headed login bootstrap:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --login
```

The storage state at `data/browser/suno/state.json` is sensitive local data. Do
not commit it, copy it into issue threads, or include it in PR artifacts.

For session-continuity diagnostics, `--persistent-profile-check DIR` writes a
full browser profile to the chosen directory and reports a compact
`profile_auth_diagnostics` payload in the CLI result. That profile directory is
also sensitive local data because it can contain cookies, cache, IndexedDB,
service-worker state, and challenge-provider state.

For context-rotation diagnostics, `--skip-recording-context-rotation` avoids the
post-auth HAR/video context recreation. Expect less network/video evidence for
that run; the point is to compare page state with fewer browser-context
transitions.

## Suno Generation Evidence

Request-aware generation runs write Suno-specific events through the active GSV
evidence sink. With the default session recorder, inspect:

```bash
ls data/sessions/suno/
tail -n 20 data/sessions/suno/<session-id>/evidence.jsonl
```

Current event types:

- `visit_step_started`: step name, safe page object id, URL path, and timestamp.
- `visit_step_finished`: step name, outcome, error summary, duration, safe page object id, URL path, and timestamp.
- `request_loaded`: request id, prompt, prompt hash, title/style flags, count, mode flags, and tags.
- `ui_click`: semantic click source, selector group, selected selector, selector index, click method, bounding box, click point, safe page object id, URL path, and outcome.
- `generation_pre_submit`: request id, field summary, compact page state, button readiness, challenge visibility, challenge-frame provider counts, URL path, and timing diagnostics recorded before the official Create click.
- `create_click_attempted`: request id, official submit phase, source, semantic click metadata, and pre-submit diagnostics.
- `create_click_skipped`: request id, official submit phase, skip reason, compact page state, and diagnostics.
- `generation_submitted`: request id, submit attempt, timestamp, field summary, and pre-submit diagnostics.
- `generation_completed`: request id, visible result count, titles, IDs, and URLs when present.
- `generation_blocked`: request id, phase, block reason, safe visible message, and compact page state.
- `generation_failed`: request id, phase, error summary, and compact page state when available.

Manifest counters use Suno-specific names:

- `suno.requests_loaded`
- `suno.requests_submitted`
- `suno.generations_requested`
- `suno.generations_detected`
- `suno.blocked_states_detected`
- `suno.manual_verification_blocks_detected`
- `suno.policy_blocks_detected`

Evidence does not store cookies/storage state, but it can include
operator-supplied prompt text, visible result metadata, and local audio
download result paths. Treat `data/sessions/` as sensitive local run history.

### Create-Click And Challenge Diagnostics

When investigating first-submit manual verification, use evidence in this order:

1. Compare `visit_step_started` and `visit_step_finished` to confirm which step
   was running when the page state changed. The runner records step lifecycle
   even when an earlier step fails and the plan continues.
2. Inspect `ui_click` events before `submit_generation`. Each event records the
   semantic source, selector group, selected selector, target index, bounding
   box, click point, and safe page object id. This is the primary way to detect
   whether an Advanced-mode helper clicked an unintended target before the
   official Create step.
3. Inspect `create_click_skipped` and `create_click_attempted`. A safe blocked
   run should have `create_click_skipped` with a reason such as
   `blocked:manual_verification_required`, `create_button_disabled`, or
   `create_button_selector_not_found`. A real automated submit attempt should
   have `create_click_attempted` followed by `generation_submitted`.
4. Compare `generation_pre_submit.diagnostics.challenge_frame_count`,
   `visible_challenge_frame_count`, and `challenge_frame_providers` with the
   broader `page_state.diagnostics.manual_verification_visible` flag. The frame
   counts are derived from visible challenge-provider iframes and do not include
   frame URLs or tokens.
5. Use trace network metadata, not HAR content, when HAR capture omits
   challenge-provider or API calls. Do not paste cookies, storage state, HAR
   headers, request bodies, or challenge URLs into issues or PRs.

The diagnostics are for attribution only. They must not be used to solve,
bypass, retry around, or otherwise weaken CAPTCHA/manual verification controls.

### Artifact Review Checklist

After a headed smoke run, inspect the newest session bundle:

```bash
SESSION_DIR="$(ls -td data/sessions/suno/* | head -n 1)"
cat "$SESSION_DIR/manifest.json"
tail -n 50 "$SESSION_DIR/evidence.jsonl"
```

Confirm that request-aware submit runs have `request_loaded`,
`generation_pre_submit`, `generation_submitted`, and one terminal generation
event. Confirm-submit inspection runs should have `request_loaded` and
`generation_pre_submit` but no `generation_submitted`. Then decide whether to
keep or purge the local artifacts. Use [MANUAL_SMOKE.md](MANUAL_SMOKE.md) for
the full live smoke checklist and cleanup commands.

## Verifying Loki Ingestion

Start with journald:

```bash
journalctl -u suno-assistant.service -n 50 --no-pager -q
```

Then verify the stream is queryable in Loki:

```bash
curl -G "$LOKI_URL/loki/api/v1/query_range" \
  --data-urlencode 'query={component="suno-assistant"}' \
  --data-urlencode "limit=20"
```

## Useful LogQL Queries

```logql
{component="suno-assistant"}
{component="suno-assistant"} |= "ERROR"
{component="suno-assistant"} |~ "task.*completed|task.*failed"
{component="suno-assistant"} |= "startup"
```

## Optional Session Artifact Pattern

Projects with long-running tasks, workers, or batch jobs may store per-run artifacts under:

```text
data/sessions/<timestamp>_<task-id>/
```

Typical contents:
- `manifest.json`
- `worker.jsonl`
- `trace.zip`
- `network.har`
- other tool-specific artifacts

### Manifest Shape

```json
{
  "session_id": "2026-04-27T081500Z_job-42",
  "started_at": "2026-04-27T08:15:00Z",
  "finished_at": "2026-04-27T08:20:30Z",
  "duration_seconds": 330,
  "outcome": "completed",
  "task": {
    "id": "job-42",
    "kind": "sync"
  },
  "results": {
    "processed": 18
  },
  "error": null
}
```

### Lifecycle

Use a `finally` block so cleanup and manifest writing still happen on failures:
1. Initialize the session directory.
2. Set log context.
3. Run the task.
4. Finalize artifacts and manifest.
5. Detach the JSONL handler if one was created.

### Retention

Recommended knobs:
- `retention_days`
- `max_sessions`

Run cleanup before starting a new session so the artifact store stays bounded.

### Cleanup-On-Success Modes

- `off`: never delete heavy artifacts automatically
- `failures`: keep heavy artifacts only for failed or cancelled runs
- `always`: always clean heavy artifacts after finalization

### Optional Archive Sink

Projects that need durable artifact retention can add a pluggable archive sink such as S3. This template documents the pattern only; it does not implement an archive backend.

# suno-assistant Song Generation

Use this skill to turn a user's song idea and iterative feedback into a
validated Suno Assistant request file, then run the project create workflow.

## Core Workflow

1. Read `AGENTS.md`, `README.md`, and `docs/CREATE_BOX.md` before changing or
   running anything when the context is not already fresh.
2. Convert the user's idea into an original-song request YAML.
3. Validate the request with the project loader before opening Suno:
   ```bash
   venv/bin/python - <<'PY'
   from suno_assistant.requests import load_song_request
   req = load_song_request("/path/to/request.yaml")
   print(req.title, req.weirdness, req.style_influence, req.uses_advanced_controls)
   PY
   ```
4. Run a headed fill-only preview unless the user explicitly asks to submit or
   says to create/hit Create:
   ```bash
   venv/bin/python -m suno_assistant.main \
     --config config/config.yaml \
     --headed \
     --keep-open \
     --fill-only \
     --request /path/to/request.yaml
   ```
5. When the user explicitly approves submission, run one bounded create action:
   ```bash
   venv/bin/python -m suno_assistant.main \
     --config config/config.yaml \
     --headed \
     --request /path/to/request.yaml
   ```
6. Monitor the process until it exits. Do not leave `suno_assistant.main`
   running.
7. Inspect the latest session evidence and, when useful, extract a late video
   frame for visual verification:
   ```bash
   SESSION_DIR="$(ls -td data/sessions/suno/* | head -n 1)"
   tail -n 80 "$SESSION_DIR/evidence.jsonl"
   ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 "$SESSION_DIR/video.webm"
   ffmpeg -y -ss 00:01:10 -i "$SESSION_DIR/video.webm" -frames:v 1 /tmp/suno-check.png
   ```
8. Report what was submitted, visible results, and any blocked/failed states.

## Request File Practice

- Use a temporary request path under `/tmp/` during live iteration unless the
  user asks to save the request in the repo.
- Add reusable examples under `examples/` only when the user asks for a
  committed example.
- Prefer Advanced mode for controlled song creation:
  ```yaml
  prompt: "Original creative brief..."
  advanced_mode: true
  title: "Song Title"
  lyrics: |
    Verse and chorus lyrics...
  style: "genre, vocal tone, tempo, instrumentation, arrangement"
  exclude_styles: "artist imitation, named-artist voice imitation, unwanted traits"
  vocal_gender: female
  style_mode: manual
  weirdness: 50
  style_influence: 85
  instrumental: false
  count: 1
  tags:
    - live-request
  notes: "Local note; not entered into Suno."
  ```
- Keep `count: 1` for live runs unless the user explicitly asks otherwise.
- Use `style_influence` to make Suno follow style wording more strongly.
- Use `weirdness` for surprise and character; keep tempo and vocal constraints
  explicit when increasing weirdness.
- Put negative constraints in `exclude_styles`, especially after user feedback.

## Safe Artist And Voice References

Do not ask Suno to imitate a named artist, a named song, or a specific voice.
When the user gives an artist or song as a direction, translate the reference
into generic musical traits.

Examples:

- "similar to Elton John's Your Song" -> "warm intimate piano-led pop ballad,
  sincere melody, gentle arrangement, conversational lyrics".
- "like Adele or Amy Winehouse" -> "mature soulful female alto vocal, smoky
  warm tone, adult contemporary piano-soul, bluesy phrasing, restrained
  vibrato".
- "too teen/poppy" -> add `teen pop`, `bubblegum pop`, `girlish vocal`, and
  `childish vocal` to `exclude_styles`.

Explain briefly when you transform a restricted reference into generic traits.

## Iteration Patterns

When the user says the result is:

- Too fast: add a BPM target such as `relaxed 74 BPM`, exclude `fast tempo`,
  `frantic drums`, and `dance beat`, and reduce "anthem" or "energetic" wording.
- Too boring: add tasteful energy such as `inspiring bridge`, `handclaps`,
  `playful chord changes`, or `surprising melodic turns`; increase weirdness
  moderately.
- Too teen/poppy: steer toward `mature alto`, `adult contemporary`,
  `restrained vibrato`, `soulful phrasing`, `warm upright bass`, and
  `subtle organ`; exclude teen-pop vocal terms.
- Too generic: add concrete details from the user's story and strengthen title,
  hook, arrangement, and exclude styles.

## Live Run Interpretation

The current blocked-state detector can falsely classify successful runs as
`quota_unavailable` when it sees persistent sidebar copy such as "Upgrade to
Premier". If evidence shows `generation_submitted` but then says
`blocked:quota_unavailable`, verify visually from the video or open browser
before reporting failure.

Use video frames or screenshots to confirm whether new tracks appeared. In the
final response, distinguish:

- The automation's evidence label.
- What the live UI visibly produced.

## Guardrails

- Never automate credentials, MFA, CAPTCHA, billing, quota workarounds, or
  platform-control bypasses.
- Do not retry around real moderation, quota, or auth blocks.
- Treat `data/`, browser storage state, HARs, traces, videos, prompts, and
  generated result metadata as sensitive local artifacts.
- Keep generated request YAMLs in `/tmp/` unless the user asks to persist them.
- Do not stage or commit `data/` artifacts.

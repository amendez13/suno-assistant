# Suno Buddy Song Iteration

Use this skill for end-to-end Suno Buddy iteration work: one song run, many
request versions, live Suno submission through Suno Assistant, output-note
capture, and tracker deployment.

Also use `suno-assistant-song-generation` when changing request content or
running Suno Assistant; it contains the lower-level create workflow and
platform guardrails.

## Repos And Paths

- Automation repo: `/Users/alex3m6/Dropbox/projects/automation`
- Suno Assistant repo: `/Users/alex3m6/Dropbox/projects/suno-assistant`
- Suno Buddy component: `components/suno_buddy`
- Project workspaces: `components/suno_buddy/projects/<project>/`
- Requests: `components/suno_buddy/projects/<project>/requests/`
- Output notes: `components/suno_buddy/projects/<project>/outputs/`
- Production tracker: `http://100.84.173.75:8092/`
- Hetzner playbook: `infra/hetzner/suno_buddy_setup.yml`

Before editing, check both repos:

```bash
git status --short --branch
```

Do not stage or commit Suno Assistant `data/` artifacts. Only summarize their
paths and extracted links in Suno Buddy output notes.

## Iteration Workflow

1. Identify the active project and latest request.
   - List `requests/` and use the highest numeric prefix.
   - Create the next request as `<NNN>-<slug>.yaml`.
   - Use a versioned Suno-facing `title` for every submitted generation:
     `<Base Title> -v<N>`.
   - Increment `<N>` per base song within the project, ignoring the global
     request number. For a new song, start at `-v1`; for another iteration of
     an existing song, inspect prior request titles and use the next version.
   - Preserve the stable base title in `tags` and `notes` so the tracker and
     final report can still identify the underlying song even when the Suno
     title is versioned.
   - Preserve parameters unless the user explicitly changes them.
   - For the Borges/Snorri run, current defaults have been `weirdness: 80`,
     `style_influence: 50`, `count: 1`, Advanced mode, male vocal.

2. Apply the requested prompt change narrowly.
   - Update only the fields implied by user feedback: usually `style`,
     `lyrics`, `exclude_styles`, `weirdness`, `style_influence`, or tempo.
   - Keep previous successful constraints unless contradicted.
   - Put unwanted traits in `exclude_styles`.
   - If the user gives a named artist or song reference, translate it into
     generic musical traits; do not request imitation of a named artist, named
     song, or specific voice.

3. Validate the request in the Suno Assistant repo:

```bash
cd /Users/alex3m6/Dropbox/projects/suno-assistant
venv/bin/python - <<'PY'
from suno_assistant.requests import load_song_request
req = load_song_request("/abs/path/to/request.yaml")
print(req.title, req.weirdness, req.style_influence, req.uses_advanced_controls)
PY
```

4. Submit only when the user asks to run/create/submit. Use the Suno Buddy
   wrapper from the automation repo:

```bash
cd /Users/alex3m6/Dropbox/projects/automation
components/suno_buddy/venv/bin/python -m components.suno_buddy.main \
  --config components/suno_buddy/config.yaml \
  run \
  --project <project> \
  --request requests/<NNN>-<slug>.yaml \
  --submit \
  --no-keep-open
```

For preview-only work, omit `--submit`; that runs fill-only mode.

5. Monitor until the process exits. Do not leave `suno_assistant.main`
   running. Note the session directory printed by Suno Assistant, for example:

```text
data/sessions/suno/2026-05-21T144211Z_run-suno-create-4d4b8090
```

6. Inspect evidence. The known detector can report `quota_unavailable` because
   of persistent upgrade/sidebar text even after a successful click. Treat
   `generation_submitted` as proof the create button was clicked once, then
   verify visible outputs separately:

```bash
cd /Users/alex3m6/Dropbox/projects/suno-assistant
tail -n 120 data/sessions/suno/<session>/evidence.jsonl
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 \
  data/sessions/suno/<session>/video.webm
ffmpeg -y -ss 00:01:30 -i data/sessions/suno/<session>/video.webm \
  -frames:v 1 /tmp/suno-<project>-<NNN>-check.png
```

7. Collect visible generated-song links from the create page:

```bash
cd /Users/alex3m6/Dropbox/projects/suno-assistant
venv/bin/python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --collect-songs data/song-links/<project>-<NNN>-create.json \
  --songs-url https://suno.com/create
```

Read the first entries and compare with the previous collection. New outputs
usually appear at the top:

```bash
venv/bin/python - <<'PY'
import json
from pathlib import Path
data = json.loads(Path("data/song-links/<project>-<NNN>-create.json").read_text())
print(data["count"], data["collected_at"])
for song in data["songs"][:8]:
    print(song.get("title"), song.get("url"))
PY
```

Do not download audio or bypass auth, CAPTCHA, billing, moderation, or quota
controls.

8. Disambiguate duplicate generated titles when possible.
   - Suno usually creates two songs from one submitted request, and both start
     with the same requested title.
   - After collecting links, if both newest outputs have the same title, try to
     rename at least one visible output when the Suno UI or available tooling
     exposes a normal title-edit action. Use suffixes such as
     `<Base Title> -v<N>-a` and `<Base Title> -v<N>-b`, or leave the first as
     `<Base Title> -v<N>` and rename the second `<Base Title> -v<N>-b`.
   - If no supported rename action is available, do not hack around Suno or use
     unsupported requests. Record the duplicate title state and the desired
     rename in the output note.

## Output Notes

Create one Markdown note under `outputs/` for every submitted request:

```text
components/suno_buddy/projects/<project>/outputs/YYYY-MM-DD-<NNN>-<slug>.md
```

Include:

- request file, title, date, and mode
- concise changes from the prior iteration
- generation session path, evidence file, video file, and screenshot path
- song-link collector output file and collector session
- first two newest visible Suno links, when available
- generated titles as collected, plus any successful rename or desired rename
  when duplicate titles could not be changed
- outcome that separates automation classification from visible results
- note that no audio files were downloaded

If the run was submitted but the collector does not show new links, say that
clearly and do not invent output links.

## Tracker Validation And Deploy

After adding request/output files, run tests from the automation repo:

```bash
components/suno_buddy/venv/bin/python -m pytest components/suno_buddy/tests -q
```

Commit and push Suno Buddy tracker data when the user is actively iterating in
the production tracker or has asked for production updates:

```bash
git add components/suno_buddy/projects/<project>/requests/<NNN>-<slug>.yaml \
  components/suno_buddy/projects/<project>/outputs/YYYY-MM-DD-<NNN>-<slug>.md
git commit -m "feat: add <short> suno iteration"
git push origin main
```

Deploy production from the automation repo:

```bash
cd /Users/alex3m6/Dropbox/projects/automation/infra/hetzner
ansible-playbook -i inventory.local.ini suno_buddy_setup.yml
```

Verify:

```bash
curl -s 'http://100.84.173.75:8092/api/projects/<project>/runs/<run-slug>?ts=1' \
  | /Users/alex3m6/Dropbox/projects/automation/components/suno_buddy/venv/bin/python \
  -c 'import json,sys; data=json.load(sys.stdin); print(data["run"]["iteration_count"]); print([i["id"] for i in data["iterations"][:4]])'

ansible hetzner_vps -i inventory.local.ini -m command \
  -a "bash -lc 'cd /home/admin/projects/automation && git rev-parse --short HEAD && systemctl is-active suno-buddy'"
```

The tracker orders newest iterations first. Confirm the new iteration is at the
top and the output note is attached.

## Reporting

In the final response, include:

- the new request filename and the exact requested change
- the versioned Suno title used for this generation
- whether Suno Assistant submitted once
- the two newest Suno links, if collected
- whether duplicate generated titles were renamed or only noted
- any blocked classifier result, separated from visible outputs
- test result, commit hash, and deployment status when applicable

Keep the response short. Mention local sensitive artifacts only as paths, not
contents.

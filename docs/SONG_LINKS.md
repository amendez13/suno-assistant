# Generated Song Link Export

Suno Assistant can collect visible generated-song titles and links from the
operator's authenticated Suno account and write them to a local file. This is a
metadata export only: it does not download audio, bypass access controls, or
interact with hidden APIs.

## Command

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --collect-songs data/song-links/latest.json
```

By default the collector visits:

```text
https://suno.com/library
```

Use `--songs-url` to inspect another Suno page that shows song cards:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --collect-songs data/song-links/create-results.md \
  --songs-url https://suno.com/create
```

## Output Formats

The output format is inferred from the file extension:

- `.json` writes one JSON document with source metadata and a `songs` array.
- `.jsonl` writes one JSON object per song.
- `.md` or `.markdown` writes a Markdown table.

You can also set the format explicitly:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --collect-songs data/song-links/latest.md \
  --songs-format markdown
```

JSON output shape:

```json
{
  "source_url": "https://suno.com/library",
  "collected_at": "2026-05-21T10:00:00+00:00",
  "count": 2,
  "songs": [
    {
      "title": "Secondhand Stars",
      "url": "https://suno.com/song/song_abc",
      "song_id": "song_abc"
    }
  ]
}
```

## Behavior

The collector:

- starts from the saved Suno browser session
- navigates to the configured Suno page
- reads visible song-card metadata from the loaded page
- normalizes relative Suno song links to absolute URLs
- writes the output file locally
- records a `song_links_collected` evidence event in the GSV session bundle

If the saved session is expired, the run exits as blocked with
`auth_required`. Run the normal headed login bootstrap before collecting again:

```bash
python -m suno_assistant.main --config config/config.yaml --headed --login
```

## Scope

This feature intentionally does not:

- download audio or stems
- click share/download menus
- bypass login, quota, moderation, CAPTCHA, MFA, or other platform controls
- rely on private Suno APIs

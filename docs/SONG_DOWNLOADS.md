# Suno Song Downloads

This workflow downloads audio files through Suno's visible song-page download
controls using the operator's own authenticated session. It supports either:

- a playlist or other song-listing page that exposes visible song cards
- a single song URL such as `https://suno.com/song/<song-id>`

It does not bypass auth, plan gating, quota, CAPTCHA, or other platform
controls. If a requested format is blocked, Suno Assistant records that result
in the JSON report instead of retrying around it.

## Usage

Download MP3 files from a playlist:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --download-songs data/song-downloads/borges2 \
  --songs-url https://suno.com/playlist/a7b2f1b0-a3fb-42f0-a36a-0564109be81e \
  --download-formats mp3
```

Download both MP3 and WAV from a single song:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --download-songs data/song-downloads/camden \
  --songs-url https://suno.com/song/37b5b931-1701-44c8-8d9f-b68a94ef7e6e \
  --download-formats both
```

Write the result report to a custom path:

```bash
python -m suno_assistant.main \
  --config config/config.yaml \
  --headed \
  --download-songs data/song-downloads/borges2 \
  --download-results data/song-downloads/borges2-results.json \
  --songs-url https://suno.com/playlist/a7b2f1b0-a3fb-42f0-a36a-0564109be81e \
  --download-formats mp3
```

## Behavior

- `--songs-url` accepts a playlist, library/create page with visible song cards,
  or a single song URL.
- Playlist and listing pages are resolved into song URLs from the visible DOM.
- Single-song URLs are downloaded directly without a preliminary link-export step.
- For each song, Suno Assistant visits the song page and uses `More -> Download`
  with the requested format actions.
- Files are renamed into title-based filenames after download, using the
  visible Suno song title when available instead of trusting Suno's suggested
  browser filename.
- If two different songs resolve to the same title-based filename, Suno
  Assistant appends a short song-id suffix instead of overwriting silently.
- MP3 downloads also get their embedded `title` tag rewritten to match the
  final local filename stem when `ffmpeg` is available on the operator machine.
- A JSON report is written to `song-downloads.json` inside the output directory
  unless `--download-results` overrides it.

## Result Report

The JSON report includes:

- `source_url`
- `output_dir`
- `requested_formats`
- `downloaded_at`
- one result row per requested song-format pair

Each result row records:

- `url`
- `title`
- `song_id`
- `download_format`
- `outcome`: `downloaded`, `blocked`, or `failed`
- `output_path` when a file was saved
- `suggested_filename` when Suno started a browser download
- `error` when a requested format did not download

## Constraints

This workflow intentionally does not:

- automate login, MFA, CAPTCHA, or billing actions
- bypass plan gating for WAV/video downloads
- scrape hidden/private APIs when the visible UI blocks a format
- persist cookies or storage state in evidence

Session evidence still records local result paths and source URLs. Treat
`data/sessions/` and download reports as sensitive local artifacts.

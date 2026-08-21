# API v2

`/api/v2` is the ownership-aware API for new clients. It uses the same downloader queue and the same API keys as the legacy routes, so migrating a client does not create a second task system.

## Authentication

All v2 endpoints except `GET /api/v2/health` require:

```http
X-API-Key: <api key>
```

Existing permission names are reused:

- `get_video`
- `get_audio`
- `get_info`
- `get_live_video`
- `get_live_audio`

A key may read only tasks it created. Access to another key's task or file is returned as `404` rather than `403`, so task existence is not disclosed.

## Error format

All authenticated v2 routes use one error shape:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "URL is required"
  }
}
```

Current codes:

| Code | HTTP | Meaning |
|---|---:|---|
| `unauthorized` | 401 | missing or invalid `X-API-Key` |
| `forbidden` | 403 | key exists but lacks the task permission |
| `not_found` | 404 | task/file does not exist or belongs to another key |
| `rate_limited` | 429 | rolling request limit exceeded |
| `invalid_request` | 400 | invalid JSON, task type, URL, selector, time or filename |

## Health

### `GET /api/v2/health`

No authentication is required.

```bash
curl http://localhost:5000/api/v2/health
```

Example:

```json
{
  "status": "ok",
  "version": "2.0.0",
  "yt_dlp_version": "2026.08.XX...",
  "storage_backend": "sqlite"
}
```

`yt_dlp_version` is especially useful after the daily production rebuild: `yt-dlp` is deliberately rolling/nightly while the rest of the application dependencies remain pinned.

## Create task

### `POST /api/v2/tasks`

Headers:

```http
X-API-Key: <api key>
Content-Type: application/json
```

Every request requires:

| Field | Type | Description |
|---|---|---|
| `type` | string | task type listed below |
| `url` | string | public `http://` or `https://` media URL |

Supported task types:

| `type` | Required permission | Result |
|---|---|---|
| `get_video` | `get_video` | downloaded video/media file |
| `get_audio` | `get_audio` | downloaded/extracted audio file |
| `get_info` | `get_info` | `info.json` containing sanitized yt-dlp metadata |
| `get_live_video` | `get_live_video` | live video segment/recording |
| `get_live_audio` | `get_live_audio` | live audio segment/recording |

Successful creation returns `202 Accepted`:

```json
{
  "id": "J86u...",
  "status": "waiting",
  "status_url": "/api/v2/tasks/J86u..."
}
```

### Common task fields

The following optional fields are accepted. Fields irrelevant to a specific task type are harmless but normally should be omitted by new clients.

| Field | Type | Default | Description |
|---|---|---|---|
| `video_format` | string | `bestvideo` | yt-dlp video format selector |
| `audio_format` | string/null | `bestaudio` | yt-dlp audio selector; `"none"`/`"null"` disables audio for video tasks |
| `output_format` | string | unset | output container/codec requested through ffmpeg, e.g. `mp4`, `mkv`, `webm`, `mp3`, `m4a` |
| `output_filename` | string | generated stem | sanitized basename, maximum 120 chars; directories are discarded |
| `start_time` | number or time string | unset | VOD range start; seconds or `HH:MM:SS`/`MM:SS` |
| `end_time` | number or time string | unset | VOD range end; must be greater than start |
| `force_keyframes` | boolean | `false` | request keyframes at ffmpeg cuts |
| `start` | number | `0` | live-relative range start in seconds |
| `duration` | number | unset | live segment length in seconds; must be greater than zero |

Format selectors are passed to yt-dlp rather than interpreted by the API. The API limits selector length/control characters but otherwise keeps yt-dlp syntax available.

Private/loopback literal IP URLs and localhost names are rejected by default to reduce SSRF risk. `ALLOW_PRIVATE_URLS=true` disables that guard for trusted deployments.

### Video example

```bash
curl -X POST http://localhost:5000/api/v2/tasks \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "get_video",
    "url": "https://www.youtube.com/watch?v=...",
    "video_format": "bestvideo[height<=1080]",
    "audio_format": "bestaudio",
    "output_format": "mp4",
    "output_filename": "example-video"
  }'
```

For video without audio:

```json
{
  "type": "get_video",
  "url": "https://example.invalid/media",
  "video_format": "bestvideo",
  "audio_format": "none"
}
```

### Audio example

```bash
curl -X POST http://localhost:5000/api/v2/tasks \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "get_audio",
    "url": "https://www.youtube.com/watch?v=...",
    "audio_format": "bestaudio",
    "output_format": "mp3"
  }'
```

### VOD section example

```json
{
  "type": "get_video",
  "url": "https://www.youtube.com/watch?v=...",
  "output_format": "mp4",
  "start_time": "00:01:30",
  "end_time": "00:02:00",
  "force_keyframes": false
}
```

`start_time` and `end_time` are media-timeline positions, not Unix timestamps.

### Metadata example

```bash
curl -X POST http://localhost:5000/api/v2/tasks \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "get_info",
    "url": "https://www.youtube.com/watch?v=..."
  }'
```

The completed task points to `/api/v2/files/<task-id>/info.json`.

### Live example

```json
{
  "type": "get_live_video",
  "url": "https://...",
  "start": 0,
  "duration": 120,
  "video_format": "bestvideo",
  "audio_format": "bestaudio",
  "output_format": "mp4"
}
```

For live tasks, `start` is a relative offset and `duration` is the requested recording length. The server does not reinterpret `start` as an epoch timestamp.

## Read task status

### `GET /api/v2/tasks/<task_id>`

```bash
curl -H "X-API-Key: $API_KEY" \
  http://localhost:5000/api/v2/tasks/$TASK_ID
```

Possible `status` values:

- `waiting`
- `processing`
- `completed`
- `error`

Waiting/processing example:

```json
{
  "id": "J86u...",
  "type": "get_video",
  "status": "processing",
  "created_at": "2026-08-21T21:00:00+00:00",
  "completed_at": null,
  "attempts": 1
}
```

Completed example:

```json
{
  "id": "J86u...",
  "type": "get_video",
  "status": "completed",
  "created_at": "2026-08-21T21:00:00+00:00",
  "completed_at": "2026-08-21T21:00:20+00:00",
  "attempts": 1,
  "file": "/api/v2/files/J86u.../video.mp4"
}
```

Failed example:

```json
{
  "id": "J86u...",
  "type": "get_video",
  "status": "error",
  "created_at": "2026-08-21T21:00:00+00:00",
  "completed_at": "2026-08-21T21:00:05+00:00",
  "attempts": 1,
  "error": "yt-dlp/ffmpeg error text"
}
```

`attempts` increments when a worker claims/reclaims the job. Workers use leases; if a worker disappears, an expired task can be claimed again instead of remaining permanently in `processing`.

## Download task file

### `GET /api/v2/files/<task_id>/<filename>`

Use the exact `file` value returned by task status:

```bash
FILE=$(curl -sS \
  -H "X-API-Key: $API_KEY" \
  "http://localhost:5000/api/v2/tasks/$TASK_ID" | jq -r .file)

curl -f \
  -H "X-API-Key: $API_KEY" \
  "http://localhost:5000$FILE" \
  -o result.bin
```

Flask/Werkzeug conditional file serving supports byte-range requests, so clients can request ranges such as:

```http
Range: bytes=0-1048575
```

The API resolves files only inside the known task directory and checks task ownership before serving them.

## Polling pattern

A minimal shell loop:

```bash
while true; do
  BODY=$(curl -fsS -H "X-API-Key: $API_KEY" \
    "http://localhost:5000/api/v2/tasks/$TASK_ID") || exit 1
  STATUS=$(printf '%s' "$BODY" | jq -r .status)
  printf '%s\n' "$BODY" | jq
  case "$STATUS" in
    completed|error) break ;;
  esac
  sleep 1
done
```

Do not assume a fixed completion time. A task can remain `waiting` while all downloader slots are occupied.

## v2 versus legacy API

The APIs are adapters over the same state backend and worker queue:

```text
legacy /get_video ─┐
                   ├─> state backend ─> worker ─> yt-dlp/ffmpeg
v2 /api/v2/tasks ──┘
```

The legacy API keeps historical response shapes such as `{"status":"waiting","task_id":"..."}`. V2 uses `id`, consistent structured errors and ownership-protected status/files.

The legacy API is documented separately in [`legacy-api.md`](legacy-api.md).

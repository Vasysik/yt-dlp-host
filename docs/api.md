# API reference

This document is the complete HTTP API reference for `yt-dlp-host`.

The modernized service deliberately keeps the established `/get_*`, `/status`, `/files`, and key-management routes as the primary API. Existing clients continue to work, while new clients use the same endpoints and may opt into newer optional fields and stricter status/file authentication. The internal implementation is now an API process plus a durable state backend and a separate downloader worker.

## Table of contents

1. [API surface and compatibility](#api-surface-and-compatibility)
2. [Base URL](#base-url)
3. [`GET /health`](#get-health)
4. [Authentication](#authentication)
5. [Permissions](#permissions)
6. [Rate limiting and quotas](#rate-limiting-and-quotas)
7. [Task lifecycle](#task-lifecycle)
8. [Download endpoints](#download-endpoints)
   - [`POST /get_video`](#post-get_video)
   - [`POST /get_audio`](#post-get_audio)
   - [`POST /get_info`](#post-get_info)
   - [`POST /get_live_video`](#post-get_live_video)
   - [`POST /get_live_audio`](#post-get_live_audio)
9. [Task status](#task-status)
   - [`GET /status/<task_id>`](#get-statustask_id)
10. [File delivery](#file-delivery)
   - [`GET /files/<path:filename>`](#get-filespathfilename)
   - [`info.json` filtering](#infojson-filtering)
   - [`qualities` output](#qualities-output)
   - [Range requests](#range-requests)
11. [API-key management](#api-key-management)
    - [`POST /create_key`](#post-create_key)
    - [`DELETE /delete_key/<name>`](#delete-delete_keyname)
    - [`GET /get_key/<name>`](#get-get_keyname)
    - [`GET /get_keys`](#get-get_keys)
    - [`POST /check_permissions`](#post-check_permissions)
12. [Validation and compatibility hardening](#validation-and-compatibility-hardening)
13. [Error responses](#error-responses)
14. [Complete client examples](#complete-client-examples)
15. [Live JSON compatibility mode](#live-json-compatibility-mode)
16. [Migration notes](#migration-notes)

---

## API surface and compatibility

The following routes are the supported public API:

| Method | Route | Permission | Purpose |
|---|---|---|---|
| `POST` | `/get_video` | `get_video` | enqueue a VOD/video download |
| `POST` | `/get_audio` | `get_audio` | enqueue a VOD/audio download |
| `POST` | `/get_info` | `get_info` | enqueue metadata extraction |
| `POST` | `/get_live_video` | `get_live_video` | enqueue a live video recording |
| `POST` | `/get_live_audio` | `get_live_audio` | enqueue a live audio recording |
| `GET` | `/status/<task_id>` | none by default | read task status/result in the established response shape |
| `GET` | `/files/<path:filename>` | none by default | read a task output file |
| `POST` | `/create_key` | `create_key` | create/replace a named API key |
| `DELETE` | `/delete_key/<name>` | `delete_key` | delete a named API key |
| `GET` | `/get_key/<name>` | `get_key` | retrieve a plaintext key by name |
| `GET` | `/get_keys` | `get_keys` | list all keys and compatibility metadata |
| `POST` | `/check_permissions` | valid key only | check a set of permissions |
| `GET` | `/health` | none | health, app version, yt-dlp version, active state backend |

The downloader internals are no longer the original background-thread implementation. The HTTP routes are thin adapters into one durable queue and one worker implementation.

```text
HTTP request
    │
    ▼
API route
    │
    ▼
shared task/state backend
    │
    ▼
separate downloader worker
    │
    ▼
yt-dlp + ffmpeg
```

---

## Base URL

Examples in this document use:

```text
http://localhost:5000
```

In production, replace it with the public/reverse-proxy URL, for example:

```text
https://download.example.com
```

A convenient shell setup is:

```bash
export BASE_URL='https://download.example.com'
export API_KEY='your-api-key'
```

---

## `GET /health`

Public health/readiness information for the running API process. This route is intentionally outside the task/key permission model and is useful for reverse-proxy checks, deployments, and verifying the rolling yt-dlp build.

### Request

```http
GET /health
```

```bash
curl -fsS "$BASE_URL/health" | jq
```

### Successful response

```http
HTTP/1.1 200 OK
```

```json
{
  "status": "ok",
  "version": "2.0.0",
  "yt_dlp_version": "2026....",
  "storage_backend": "json"
}
```

Fields:

| Field | Meaning |
|---|---|
| `status` | `ok` when the application initialized successfully |
| `version` | yt-dlp-host application version; this is not an API-version prefix |
| `yt_dlp_version` | exact yt-dlp version/nightly currently running |
| `storage_backend` | active state backend: `json` or `sqlite` |

The `version` value is the application release, not an API namespace. The project exposes one HTTP API surface; application releases can evolve internally while keeping these routes backward compatible.

---

## Authentication

Task creation and key-management endpoints authenticate using the historical header:

```http
X-API-Key: <api key>
```

Example:

```bash
curl -X POST "$BASE_URL/get_info" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=..."}'
```

If the header is missing:

```http
HTTP/1.1 401 Unauthorized
```

```json
{
  "error": "No API key provided"
}
```

If the secret is unknown:

```http
HTTP/1.1 401 Unauthorized
```

```json
{
  "error": "Invalid API key"
}
```

### Public status/files compatibility behavior

Historically, `/status/<task_id>` and `/files/<path>` were capability-style public routes. That behavior is preserved by default:

```env
LEGACY_PUBLIC_STATUS=true
LEGACY_PUBLIC_FILES=true
```

With those defaults, knowing the random task ID/file URL is sufficient to access them and no `X-API-Key` is required.

For a stricter deployment:

```env
LEGACY_PUBLIC_STATUS=false
LEGACY_PUBLIC_FILES=false
```

Then an API key is required and the key must own the task. This changes historical behavior, so only enable it after checking old clients.

---

## Permissions

The established permission names are unchanged:

- `get_video`
- `get_audio`
- `get_info`
- `get_live_video`
- `get_live_audio`
- `create_key`
- `delete_key`
- `get_key`
- `get_keys`

A key can have any subset.

Example key entry in live JSON mode:

```json
{
  "client": {
    "key": "secret-value",
    "permissions": [
      "get_video",
      "get_audio",
      "get_info"
    ],
    "memory_quota": 5368709120,
    "memory_usage": [],
    "last_access": "2026-08-21T22:15:23+00:00"
  }
}
```

If the key is valid but lacks the route permission:

```http
HTTP/1.1 403 Forbidden
```

```json
{
  "error": "Insufficient permissions"
}
```

`/check_permissions` has its own historical response format; see that endpoint below.

---

## Rate limiting and quotas

### Request rate limit

Authenticated task-creation and key-management routes use a true rolling request window.

Defaults:

```env
REQUEST_LIMIT=60
REQUEST_WINDOW_MINUTES=10
```

When exceeded:

```http
HTTP/1.1 429 Too Many Requests
```

```json
{
  "error": "Rate limit exceeded. Max 60 per 10 min"
}
```

Polling routes are intentionally not charged against this task-creation rate limit:

- `/status/<task_id>`
- `/files/...`
- authenticated status/files when `LEGACY_PUBLIC_STATUS=false` or `LEGACY_PUBLIC_FILES=false`

`/check_permissions` also keeps its simple historical authentication behavior and does not consume the normal route limiter.

### Download quota

Each key has a rolling byte quota and the server also has a global rolling byte quota.

Typical defaults:

```env
DEFAULT_QUOTA_BYTES=5368709120
SERVER_QUOTA_BYTES=21474836480
QUOTA_WINDOW_MINUTES=10
```

The modern worker reserves quota while a download is active and adjusts the reservation from yt-dlp progress and actual on-disk growth. This prevents several concurrent workers from all assuming the same bytes are free.

`get_info` creates an `info.json` metadata file and does not use the media-download reservation path.

---

## Task lifecycle

All download/info creation routes are asynchronous.

A successful request does **not** return the media immediately. It returns a task ID:

```json
{
  "status": "waiting",
  "task_id": "XQwXrnCo5FiU44YJ"
}
```

The lifecycle is:

```text
waiting
   │
   ▼
processing
   │
   ├────────► completed
   │
   └────────► error
```

The worker uses a lease/heartbeat internally. If a worker disappears, an expired job can be reclaimed instead of remaining permanently stuck in `processing`.

Clients should poll `/status/<task_id>` until `completed` or `error`.

---

# Download endpoints

## `POST /get_video`

Enqueues a VOD/video download.

### Permission

```text
get_video
```

### Headers

```http
X-API-Key: <api key>
Content-Type: application/json
```

### Minimal request

```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

### Full example

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "video_format": "bestvideo[height<=1080]",
  "audio_format": "bestaudio[abr<=129]",
  "output_format": "mp4",
  "output_filename": "my-video",
  "start_time": "00:00:30",
  "end_time": "00:01:00",
  "force_keyframes": false
}
```

### Parameters

| Field | Required | Type | Default | Meaning |
|---|---|---|---|---|
| `url` | yes | string | — | public `http://` or `https://` media URL |
| `video_format` | no | string | `bestvideo` | yt-dlp video format selector |
| `audio_format` | no | string/null | `bestaudio` | yt-dlp audio selector; `null`, `"none"`, or `"null"` disables audio for video tasks |
| `output_format` | no | string | source/merge result | requested output container, e.g. `mp4`, `mkv`, `webm` |
| `output_filename` | no | string | `video` | desired basename/stem; directories are removed and unsafe characters are sanitized |
| `start_time` | no | number/string | unset | VOD start position in seconds, `SS`, `MM:SS`, or `HH:MM:SS` form |
| `end_time` | no | number/string | unset | VOD end position; must be greater than start |
| `force_keyframes` | no | boolean-ish | `false` | passed as a boolean request for accurate ffmpeg cuts |

Format selectors are passed to yt-dlp. They may use normal yt-dlp selector syntax, up to the service's validation limits.

Examples:

```text
bestvideo
bestvideo[height<=1080]
bestvideo[vcodec^=avc1][height<=720]
```

Video without audio:

```json
{
  "url": "https://...",
  "video_format": "bestvideo",
  "audio_format": "none"
}
```

### Output-format behavior

When `output_format` is supplied for a video task, the worker uses ffmpeg postprocessing/remuxing rather than only changing a filename extension.

For example:

```json
{
  "output_format": "mp4"
}
```

requests an actual MP4 output path after yt-dlp/ffmpeg processing.

### Successful response

HTTP `200`:

```json
{
  "status": "waiting",
  "task_id": "XQwXrnCo5FiU44YJ"
}
```

### curl example

```bash
RESP=$(curl -fsS -X POST "$BASE_URL/get_video" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "url": "https://www.youtube.com/watch?v=...",
    "video_format": "bestvideo[height<=720]",
    "audio_format": "bestaudio",
    "output_format": "mp4",
    "start_time": 0,
    "end_time": 20
  }')

echo "$RESP" | jq
TASK_ID=$(echo "$RESP" | jq -r .task_id)
```

---

## `POST /get_audio`

Enqueues an audio download/extraction.

### Permission

```text
get_audio
```

### Minimal request

```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

### Full example

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "audio_format": "bestaudio[abr<=129]",
  "output_format": "mp3",
  "output_filename": "track",
  "start_time": "00:00:30",
  "end_time": "00:01:00",
  "force_keyframes": false
}
```

### Parameters

| Field | Required | Type | Default | Meaning |
|---|---|---|---|---|
| `url` | yes | string | — | media URL |
| `audio_format` | no | string | `bestaudio` | yt-dlp audio format selector |
| `output_format` | no | string | source format | ffmpeg extraction codec/container, e.g. `mp3`, `m4a`, `opus`, `aac` |
| `output_filename` | no | string | `audio` | sanitized output stem |
| `start_time` | no | number/string | unset | VOD start position |
| `end_time` | no | number/string | unset | VOD end position |
| `force_keyframes` | no | boolean-ish | `false` | forwarded to range-cut processing |

When `output_format` is supplied, audio is actually processed through yt-dlp's ffmpeg audio postprocessor.

### Successful response

HTTP `200`:

```json
{
  "status": "waiting",
  "task_id": "jd5nnwyNSQplQrEB"
}
```

### curl example

```bash
curl -X POST "$BASE_URL/get_audio" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "url":"https://www.youtube.com/watch?v=...",
    "audio_format":"bestaudio",
    "output_format":"mp3",
    "start_time":0,
    "end_time":20
  }'
```

---

## `POST /get_info`

Enqueues metadata extraction with yt-dlp.

### Permission

```text
get_info
```

### Request

```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

The compatibility validator may preserve default task fields in `/status` even though format/range fields are not used by `get_info`.

### Successful response

HTTP `200`:

```json
{
  "status": "waiting",
  "task_id": "XQwXrnCo5FiU44YJ"
}
```

When complete, the task's `file` points to:

```text
/files/<task_id>/info.json
```

The file contains `yt-dlp`'s sanitized metadata representation.

### curl example

```bash
RESP=$(curl -fsS -X POST "$BASE_URL/get_info" \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=..."}')

TASK_ID=$(echo "$RESP" | jq -r .task_id)
```

---

## `POST /get_live_video`

Enqueues live-video recording.

### Permission

```text
get_live_video
```

### Example request

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "start": 0,
  "duration": 300,
  "video_format": "bestvideo[height<=1080]",
  "audio_format": "bestaudio",
  "output_format": "mp4",
  "output_filename": "live-recording",
  "force_keyframes": false
}
```

### Parameters

| Field | Required | Type | Default | Meaning |
|---|---|---|---|---|
| `url` | yes | string | — | live-stream URL |
| `start` | no | number | `0` | relative start offset in seconds |
| `duration` | no* | positive number | unset | recording duration in seconds |
| `video_format` | no | string | `bestvideo` | yt-dlp video selector |
| `audio_format` | no | string/null | `bestaudio` | yt-dlp audio selector |
| `output_format` | no | string | source/merge result | e.g. `mp4`, `mkv`, `webm` |
| `output_filename` | no | string | `live_video` | sanitized output stem |
| `force_keyframes` | no | boolean-ish | `false` | cut processing option |

`duration` is accepted as optional by the compatibility layer because old data may omit it, but new callers should provide it for bounded live recordings. With a live source and no duration, yt-dlp can continue until the stream ends or the task is interrupted.

### Important time semantics

`start` is a **relative stream offset**, not a Unix timestamp.

The old implementation had incorrect epoch conversion behavior in this area; the modern worker intentionally treats it as the relative value supplied by the API.

### Successful response

```json
{
  "status": "waiting",
  "task_id": "..."
}
```

---

## `POST /get_live_audio`

Enqueues live-audio recording.

### Permission

```text
get_live_audio
```

### Example request

```json
{
  "url": "https://www.youtube.com/watch?v=...",
  "audio_format": "bestaudio",
  "output_format": "mp3",
  "output_filename": "live-audio",
  "start": 0,
  "duration": 300
}
```

### Parameters

| Field | Required | Type | Default | Meaning |
|---|---|---|---|---|
| `url` | yes | string | — | live-stream URL |
| `audio_format` | no | string | `bestaudio` | yt-dlp selector |
| `output_format` | no | string | source format | e.g. `mp3`, `m4a`, `opus` |
| `output_filename` | no | string | `live_audio` | sanitized output stem |
| `start` | no | number | `0` | relative start offset in seconds |
| `duration` | no* | positive number | unset | recording duration |

As with live video, new callers should normally supply `duration`.

### Successful response

```json
{
  "status": "waiting",
  "task_id": "..."
}
```

---

# Task status

## `GET /status/<task_id>`

Returns the established task response object for the specified ID.

### Authentication

Default compatibility mode:

```env
LEGACY_PUBLIC_STATUS=true
```

No API key is required.

Strict mode:

```env
LEGACY_PUBLIC_STATUS=false
```

then `X-API-Key` is required and must belong to the task owner.

### Waiting example

```json
{
  "key_name": "client",
  "status": "waiting",
  "task_type": "get_video",
  "url": "https://www.youtube.com/watch?v=...",
  "video_format": "bestvideo[height<=720]",
  "audio_format": "bestaudio",
  "force_keyframes": false,
  "start": 0,
  "output_format": "mp4"
}
```

### Processing example

```json
{
  "key_name": "client",
  "status": "processing",
  "task_type": "get_audio",
  "url": "https://www.youtube.com/watch?v=...",
  "video_format": "bestvideo",
  "audio_format": "bestaudio",
  "force_keyframes": false,
  "start": 0,
  "output_format": "mp3"
}
```

### Completed example

```json
{
  "key_name": "client",
  "status": "completed",
  "task_type": "get_audio",
  "url": "https://www.youtube.com/watch?v=...",
  "video_format": "bestvideo",
  "audio_format": "bestaudio",
  "force_keyframes": false,
  "start": 0,
  "output_format": "mp3",
  "completed_time": "2026-08-21T22:15:29+00:00",
  "file": "/files/jd5nnwyNSQplQrEB/audio.mp3"
}
```

### Error example

```json
{
  "key_name": "client",
  "status": "error",
  "task_type": "get_video",
  "url": "https://...",
  "video_format": "bestvideo",
  "audio_format": "bestaudio",
  "force_keyframes": false,
  "start": 0,
  "error": "yt-dlp/ffmpeg error text",
  "completed_time": "2026-08-21T22:15:29+00:00"
}
```

### Unknown task

HTTP `404`:

```json
{
  "status": "error",
  "message": "Task not found"
}
```

### Recommended polling loop

```bash
while true; do
  BODY=$(curl -fsS "$BASE_URL/status/$TASK_ID") || exit 1
  STATUS=$(printf '%s' "$BODY" | jq -r .status)
  printf '%s\n' "$BODY" | jq

  case "$STATUS" in
    completed|error) break ;;
  esac

  sleep 1
done
```

Do not assume a fixed processing time. A task can remain in `waiting` while all worker slots are occupied.

---

# File delivery

## `GET /files/<path:filename>`

Serves a file inside a known task directory.

Typical completed status value:

```json
{
  "file": "/files/jd5nnwyNSQplQrEB/audio.mp3"
}
```

Use that value directly:

```bash
FILE=$(curl -fsS "$BASE_URL/status/$TASK_ID" | jq -r .file)
curl -f "$BASE_URL$FILE" -o result.bin
```

### Authentication

Default compatibility mode:

```env
LEGACY_PUBLIC_FILES=true
```

No key is required.

Strict mode:

```env
LEGACY_PUBLIC_FILES=false
```

requires an API key that owns the task.

### Path safety

The modern compatibility implementation only serves files that:

1. belong to an existing task ID;
2. resolve inside that task's download directory;
3. exist as a regular file.

Traversal such as `../` cannot escape the task directory.

### Cache/range headers

Regular task output files include:

```http
Accept-Ranges: bytes
Cache-Control: public, max-age=3600
```

### Historical `raw=true` behavior

The old implementation named the query parameter `raw`, but its actual behavior was unusual and is preserved:

```text
?raw=true
```

results in an `inline` content-disposition header rather than forcing a conventional attachment download.

New clients should not rely on the parameter name to infer attachment behavior; simply download the URL normally if they need the bytes.

---

## `info.json` filtering

If the requested file is named `info.json`, it is returned as JSON rather than a generic file response.

### Full metadata

```bash
curl "$BASE_URL/files/$TASK_ID/info.json" | jq
```

With no query parameters, the complete sanitized yt-dlp metadata object is returned.

### Select fields

The **presence** of a query parameter selects the corresponding top-level metadata key. The parameter value itself is not important.

Example:

```bash
curl "$BASE_URL/files/$TASK_ID/info.json?title&thumbnail&duration&language" | jq
```

Possible response:

```json
{
  "title": "Example title",
  "thumbnail": "https://...",
  "duration": 123.4,
  "language": "en"
}
```

The style used by old clients is also accepted:

```text
?qualities&title&thumbnail&is_live&duration&language&
```

If at least one requested key is present, only matching values are returned.

If none of the requested keys match and `qualities` was not requested:

```http
HTTP/1.1 404 Not Found
```

```json
{
  "error": "No matching parameters"
}
```

If the file cannot be parsed as JSON:

```http
HTTP/1.1 500 Internal Server Error
```

```json
{
  "error": "Invalid info file"
}
```

---

## `qualities` output

The special query parameter:

```text
qualities
```

builds a simplified map from the `formats` array in `info.json`.

Request:

```bash
curl "$BASE_URL/files/$TASK_ID/info.json?qualities" | jq
```

Shape:

```json
{
  "qualities": {
    "audio": {
      "251": {
        "abr": 128,
        "acodec": "opus",
        "audio_channels": 2,
        "language": "en",
        "filesize": 1234567
      }
    },
    "video": {
      "137": {
        "height": 1080,
        "width": 1920,
        "fps": 30,
        "vcodec": "avc1.640028",
        "format_note": "1080p",
        "dynamic_range": "SDR",
        "filesize": 12345678
      }
    }
  }
}
```

Audio formats are ordered by bitrate (`abr`). Video formats are ordered by `(height, fps)`.

Formats marked as `unknown` or `storyboard` are ignored. Missing/unknown size becomes `0` after considering `filesize` and `filesize_approx`.

---

## Range requests

Regular task files can be requested by byte range.

Example:

```bash
curl -D /tmp/headers \
  -H 'Range: bytes=0-1023' \
  "$BASE_URL/files/$TASK_ID/audio.mp3" \
  -o /tmp/range.bin

cat /tmp/headers
wc -c /tmp/range.bin
```

For a sufficiently large file, expect a `206 Partial Content` response and an appropriate `Content-Range`.

This allows media clients to seek/stream without downloading the whole file first.

---

# API-key management

These endpoints exist for compatibility and intentionally expose plaintext secrets just like the old API. Do not expose them to untrusted users unless their permissions are tightly controlled.

## `POST /create_key`

Creates or replaces a named API key.

### Permission

```text
create_key
```

### Request

```json
{
  "name": "user_key",
  "permissions": [
    "get_video",
    "get_audio",
    "get_info"
  ]
}
```

`name` must be a non-empty string after trimming. `permissions` must be a non-empty list of non-empty strings.

The compatibility route does not maintain a hard-coded permission-name whitelist; callers with `create_key` should only assign permissions the application understands.

### Response

HTTP `201`:

```json
{
  "message": "API key created",
  "name": "user_key",
  "key": "new-plaintext-secret"
}
```

### Duplicate name behavior

Creating a key with an existing name replaces that named entry and generates a new secret. This preserves the practical overwrite semantics of the original JSON storage.

---

## `DELETE /delete_key/<name>`

Deletes a key by name.

### Permission

```text
delete_key
```

### Success

HTTP `200`:

```json
{
  "message": "API key deleted",
  "name": "user_key"
}
```

### Missing key

HTTP `404`:

```json
{
  "error": "Key not found"
}
```

---

## `GET /get_key/<name>`

Returns the plaintext secret for a named key.

### Permission

```text
get_key
```

### Success

```json
{
  "name": "user_key",
  "key": "plaintext-secret"
}
```

### Missing key

```http
HTTP/1.1 404 Not Found
```

```json
{
  "error": "Key not found"
}
```

This endpoint is preserved only for compatibility. Treat callers with `get_key` as privileged administrators.

---

## `GET /get_keys`

Lists all keys in the old object-by-name format.

### Permission

```text
get_keys
```

### Example response

```json
{
  "admin": {
    "key": "admin-secret",
    "permissions": [
      "create_key",
      "delete_key",
      "get_key",
      "get_keys",
      "get_video",
      "get_audio",
      "get_live_video",
      "get_live_audio",
      "get_info"
    ],
    "memory_quota": 5368709120,
    "memory_usage": [],
    "last_access": "2026-08-21T22:15:23+00:00"
  },
  "client": {
    "key": "client-secret",
    "permissions": ["get_info", "get_audio"],
    "memory_quota": 5368709120,
    "memory_usage": [
      {
        "task_id": "jd5nnwyNSQplQrEB",
        "size": 1234567,
        "timestamp": 1787350529.0
      }
    ],
    "last_access": "2026-08-21T22:15:23+00:00"
  }
}
```

`memory_usage` represents finalized quota events still inside the configured quota window. Exact contents naturally change with time.

---

## `POST /check_permissions`

Checks whether the current key contains every requested permission.

### Authentication

A valid `X-API-Key` is required, but no additional permission is required.

### Request

```json
{
  "permissions": [
    "get_video",
    "get_audio"
  ]
}
```

### Granted

HTTP `200`:

```json
{
  "message": "Permissions granted"
}
```

### Missing one or more permissions

HTTP `403`:

```json
{
  "message": "Insufficient permissions"
}
```

If `permissions` is not a JSON list, the compatibility response is also `403 Insufficient permissions`.

---

# Validation and compatibility hardening

The modernized implementation preserves valid old requests while deliberately rejecting unsafe input that the original server accepted too freely.

## URLs

Requirements:

- must be a non-empty string;
- maximum accepted length is 4096 characters;
- only `http://` and `https://` schemes are accepted;
- control characters are rejected;
- `localhost`, `.local`, private/loopback/link-local/multicast/reserved literal IP addresses are blocked by default.

To allow internal URLs in a trusted deployment:

```env
ALLOW_PRIVATE_URLS=true
```

## Format selectors

`video_format` and `audio_format`:

- must be strings or `null`;
- are trimmed;
- are limited to 512 characters;
- cannot contain control characters;
- otherwise preserve normal yt-dlp selector syntax.

## `output_format`

If present, it must match the service's simple format-token validation: 1-24 characters consisting of letters, digits, `.`, `_`, `+`, or `-`.

The API does not promise every token is supported by ffmpeg/yt-dlp. Unsupported output formats fail later as task errors.

## `output_filename`

If present:

1. directories are discarded;
2. unsafe characters are replaced with `_`;
3. leading/trailing spaces and dots are stripped;
4. the value is limited to 120 characters;
5. the requested extension is treated as part of the desired name/stem, while the actual final extension comes from yt-dlp/postprocessing.

Example:

```text
../../hello: world.mp3
```

becomes a safe basename similar to:

```text
hello_ world.mp3
```

The worker then uses its stem for the output template.

## VOD time values

`start_time` and `end_time` accept:

- non-negative number of seconds;
- string containing one, two, or three colon-separated non-negative numeric parts.

Examples:

```text
15
"15"
"02:30"
"01:02:03"
```

If both resolve such that end is not greater than start, the task fails with:

```text
end_time must be greater than start_time
```

## Live numeric values

`start` and `duration` must be JSON numbers, not time strings. `start >= 0`; if `duration` is supplied it must be greater than zero.

## Request body size

The Flask application applies `MAX_REQUEST_BYTES` (default 1 MiB) as the maximum HTTP request body size.

---

# Error responses

The established endpoints intentionally keep several different historical error shapes.

| Situation | HTTP | Example |
|---|---:|---|
| missing API key | 401 | `{"error":"No API key provided"}` |
| invalid API key | 401 | `{"error":"Invalid API key"}` |
| missing permission | 403 | `{"error":"Insufficient permissions"}` |
| missing task URL | 400 | `{"status":"error","message":"URL is required"}` |
| invalid task parameter | 400 | `{"status":"error","message":"..."}` |
| unknown task | 404 | `{"status":"error","message":"Task not found"}` |
| unknown file | 404 | `{"error":"File not found"}` |
| no requested info fields found | 404 | `{"error":"No matching parameters"}` |
| rate limit | 429 | `{"error":"Rate limit exceeded. Max ..."}` |

A task that passes HTTP validation can still fail asynchronously because of extractor, network, cookies, quota, format-selection, ffmpeg, or upstream errors. In that case `/status/<task_id>` changes to `error` and includes an `error` string.

---

# Complete client examples

## Python: create task, poll, download

```python
import time
from pathlib import Path

import requests

BASE_URL = "https://download.example.com"
API_KEY = "your-api-key"

session = requests.Session()
session.headers["X-API-Key"] = API_KEY

create = session.post(
    f"{BASE_URL}/get_video",
    json={
        "url": "https://www.youtube.com/watch?v=...",
        "video_format": "bestvideo[height<=720]",
        "audio_format": "bestaudio",
        "output_format": "mp4",
    },
    timeout=30,
)
create.raise_for_status()
task_id = create.json()["task_id"]

while True:
    status_response = session.get(
        f"{BASE_URL}/status/{task_id}",
        timeout=30,
    )
    status_response.raise_for_status()
    task = status_response.json()

    if task["status"] == "completed":
        break
    if task["status"] == "error":
        raise RuntimeError(task.get("error", "unknown download error"))

    time.sleep(1)

file_url = BASE_URL + task["file"]
with session.get(file_url, stream=True, timeout=60) as response:
    response.raise_for_status()
    with Path("video.mp4").open("wb") as output:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                output.write(chunk)
```

## Python: metadata and qualities

```python
import time
import requests

BASE_URL = "https://download.example.com"
API_KEY = "your-api-key"
VIDEO_URL = "https://www.youtube.com/watch?v=..."

headers = {"X-API-Key": API_KEY}

created = requests.post(
    f"{BASE_URL}/get_info",
    headers=headers,
    json={"url": VIDEO_URL},
    timeout=30,
)
created.raise_for_status()
task_id = created.json()["task_id"]

while True:
    task = requests.get(
        f"{BASE_URL}/status/{task_id}",
        headers=headers,
        timeout=30,
    ).json()
    if task["status"] == "completed":
        break
    if task["status"] == "error":
        raise RuntimeError(task.get("error"))
    time.sleep(1)

info_url = BASE_URL + task["file"]

full_info = requests.get(info_url, headers=headers, timeout=30).json()
qualities = requests.get(
    info_url,
    headers=headers,
    params={"qualities": "", "title": "", "thumbnail": ""},
    timeout=30,
).json()

print(full_info["title"])
print(qualities)
```

---

# Live JSON compatibility mode

To keep the original JSON files as the **live** source of truth:

```env
STORAGE_BACKEND=json
LEGACY_KEYS_FILE=/app/jsons/api_keys.json
LEGACY_TASKS_FILE=/app/jsons/tasks.json
JSON_STATE_FILE=/app/jsons/.yt-dlp-host-state.json
```

The two compatibility files keep their original object structure:

```text
jsons/api_keys.json
jsons/tasks.json
```

Modern-only bookkeeping is stored in the sidecar:

```text
jsons/.yt-dlp-host-state.json
```

It contains internal lease/rate/quota metadata that old clients never had to understand.

The JSON backend uses a shared `flock` lock and atomic temporary-file replacement so the API and separate worker can update state without the original process-level race behavior.

Do **not** run the old pre-refactor service and the new JSON backend simultaneously against the same JSON files. The old process does not participate in the new lock protocol.

---

# Migration notes

For existing clients, the intended migration path is:

```text
old client
   │
   │ unchanged HTTP requests
   ▼
same established routes
   │
   ▼
new durable queue/worker
```

You can keep:

- old route names;
- `X-API-Key` authentication;
- old permission names;
- `task_id` response field;
- `/status/<task_id>` polling;
- `/files/...` output URLs;
- existing `api_keys.json` / `tasks.json` by selecting `STORAGE_BACKEND=json`.

New and existing clients use the same API routes. Backward-compatible optional fields can be added to existing task requests without creating a second API surface. For status/file ownership, set `LEGACY_PUBLIC_STATUS=false` and `LEGACY_PUBLIC_FILES=false`; those same `/status` and `/files` routes will then require the owning API key.

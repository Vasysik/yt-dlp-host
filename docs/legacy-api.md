# Legacy HTTP API contract

This document freezes the compatibility surface inherited from `Vasysik/yt-dlp-host`.
The implementation may change internally; these routes and the successful response shapes are the compatibility boundary.

## Authentication

Protected legacy routes read the API secret from `X-API-Key`.

- missing header: `401 {"error":"No API key provided"}`
- unknown secret: `401 {"error":"Invalid API key"}`
- missing permission: `403 {"error":"Insufficient permissions"}`
- request rate exceeded: `429 {"error":"Rate limit exceeded. Max ..."}`

`/status/<task_id>` and `/files/<path>` historically had no authentication. They therefore stay public by default. Set `LEGACY_PUBLIC_STATUS=false` and `LEGACY_PUBLIC_FILES=false` to harden them. `/api/v2/*` never relies on this legacy behavior.

## Task creation

All task creation routes accept a JSON object and return `200` with:

```json
{"status":"waiting","task_id":"..."}
```

A missing `url` returns `400`:

```json
{"status":"error","message":"URL is required"}
```

### `POST /get_video`

Permission: `get_video`.

Accepted fields: `url`, `video_format`, `audio_format`, `start_time`, `end_time`, `force_keyframes`, `output_format`. The cleaned implementation additionally accepts the backwards-compatible optional `output_filename` field proposed in PR #16.

### `POST /get_audio`

Permission: `get_audio`.

Accepted fields: `url`, `audio_format`, `start_time`, `end_time`, `force_keyframes`, `output_format`, and optional `output_filename`.

### `POST /get_info`

Permission: `get_info`.

Creates an asynchronous metadata task. Its completed file is `info.json` and remains addressable through the legacy `/files/...` URL.

### `POST /get_live_video`

Permission: `get_live_video`.

Accepted fields include `url`, `video_format`, `audio_format`, `start`, `duration`, `force_keyframes`, `output_format`, and optional `output_filename`.

### `POST /get_live_audio`

Permission: `get_live_audio`.

Accepted fields include `url`, `audio_format`, `start`, `duration`, `force_keyframes`, `output_format`, and optional `output_filename`.

## Task status

### `GET /status/<task_id>`

Returns the legacy task object. Stable keys include `key_name`, `status`, `task_type`, `url`, `video_format`, `audio_format`, `force_keyframes`, and `start`; optional fields appear when applicable. Completed tasks may include `completed_time` and `file`; failed tasks include `error`.

Unknown task:

```json
{"status":"error","message":"Task not found"}
```

with HTTP 404.

## Files and metadata

### `GET /files/<task_id>/<filename>`

Returns a task output file. `?raw=true` intentionally preserves the historical contradictory behavior: the response is forced inline even though the old code passed `as_attachment=true` first.

For `info.json`, query parameters select metadata fields. `?qualities=1` returns normalized `audio` and `video` format dictionaries. Unknown selections return `404 {"error":"No matching parameters"}`.

The cleaned implementation intentionally hardens traversal: a file must resolve inside an existing task directory.

## Key management

### `POST /create_key`

Permission: `create_key`.

Body:

```json
{"name":"client","permissions":["get_video","get_info"]}
```

Success: HTTP 201 with `message`, `name`, and plaintext `key`. Duplicate names retain legacy overwrite semantics.

### `DELETE /delete_key/<name>`

Permission: `delete_key`.

Returns 200 on deletion or `404 {"error":"Key not found"}`.

### `GET /get_key/<name>`

Permission: `get_key`.

Returns `{ "name": "...", "key": "..." }`. This plaintext-secret retrieval is kept only for compatibility.

### `GET /get_keys`

Permission: `get_keys`.

Returns the legacy object keyed by key name, including plaintext `key`, `permissions`, `memory_quota`, `memory_usage`, and `last_access`.

### `POST /check_permissions`

No route-level permission is required, but a valid `X-API-Key` is required. Body field `permissions` is checked as a subset of the key's permissions. Returns `200 {"message":"Permissions granted"}` or `403 {"message":"Insufficient permissions"}`.

## Compatibility policy

Successful requests that were valid under the old service should keep working. Deliberately unsafe or malformed inputs can now fail earlier: local/private literal URLs are blocked unless `ALLOW_PRIVATE_URLS=true`, output filenames are reduced to a basename, request bodies have a size limit, and file traversal is rejected.

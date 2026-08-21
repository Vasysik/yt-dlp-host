# yt-dlp-host — modernized, legacy-compatible

This is a ground-up cleanup of the original `Vasysik/yt-dlp-host` architecture while keeping its HTTP API routes alive.

## What changed

- **SQLite/WAL instead of shared JSON files.** Task claims, rate limits, API-key updates and quota reservations are transactional.
- **API and worker are separate processes.** Importing Flask no longer starts download threads. Gunicorn can safely run multiple web workers.
- **Durable queue with leases.** A task is atomically claimed once; crashed workers are recoverable after the lease expires.
- **Real rolling rate limits and quota reservations.** Quota grows from yt-dlp progress and an independent on-disk monitor rather than performing a second metadata request just to guess size.
- **Safe file resolution and cryptographically random task IDs.**
- **Current YouTube runtime requirements.** The Docker image includes Deno and installs `yt-dlp[default]` so the EJS challenge solver is available.
- **Cookies/proxy/impersonation are configuration, not source patches.**
- **Automatic one-time import** from legacy `jsons/api_keys.json` and `jsons/tasks.json`.
- **No framework rewrite for its own sake.** Flask remains the compatibility surface; internals are the part that was replaced.

## Compatibility

The following legacy routes are preserved:

`POST /get_video`, `/get_audio`, `/get_live_video`, `/get_live_audio`, `/get_info`, `/create_key`, `/check_permissions`

`GET /status/<task_id>`, `/files/<path>`, `/get_keys`, `/get_key/<name>`

`DELETE /delete_key/<name>`

Legacy response keys/status codes are intentionally kept where practical, including the historical plaintext key-return endpoints. New code should prefer `/api/v2/*`.

The frozen route-by-route compatibility contract is documented in [`docs/legacy-api.md`](docs/legacy-api.md).

Two historically unauthenticated capability-style routes remain public by default for compatibility: `/status/<task_id>` and `/files/<path>`. Task IDs are now generated with `secrets`, and paths are strictly scoped to a known task. Set `LEGACY_PUBLIC_STATUS=false` and `LEGACY_PUBLIC_FILES=false` to require an API key.

## Start

```bash
cp .env.example .env
# set ADMIN_API_KEY for deterministic production credentials (recommended)
docker compose up --build
```

The API is at `http://localhost:5000`; the worker is a separate Compose service.

## Cookies (fixes the repository's open YouTube bot/cookies problem)

Export a Netscape-format cookie file, mount it into `./cookies`, then set for example:

```env
YTDLP_COOKIES_FILE=/app/cookies/youtube.txt
```

Do not accept arbitrary cookie-file paths from API callers. Keep cookies server-side and read-only.

Optional central egress settings:

```env
YTDLP_PROXY=http://user:pass@proxy.example:8080
YTDLP_IMPERSONATE=chrome
```

## New API

Create a task:

```bash
curl -X POST http://localhost:5000/api/v2/tasks \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"type":"get_video","url":"https://www.youtube.com/watch?v=...","video_format":"bestvideo[height<=1080]","output_format":"mp4"}'
```

Read status with the same key:

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:5000/api/v2/tasks/<id>
```

V2 status/files enforce task ownership. Existing API keys still use the old permission names.

## Legacy migration

On first startup the service imports configured legacy JSON files once. Defaults inside Docker Compose are:

- `/app/jsons/api_keys.json`
- `/app/jsons/tasks.json`

The `jsons` mount is read-only because new state lives in SQLite. You can also run:

```bash
python scripts/migrate_legacy.py
```

## Important environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `DATABASE_PATH` | `/app/data/yt-dlp-host.sqlite3` | SQLite state |
| `DOWNLOAD_DIR` | `/app/downloads` | task output |
| `ADMIN_API_KEY` | generated if absent | deterministic admin bootstrap recommended; generated value is logged once |
| `PORT` | `5000` | web bind port (Cloud Run-friendly) |
| `MAX_WORKERS` | `4` | concurrent downloads in worker process |
| `REQUEST_LIMIT` | `60` | requests per rolling window |
| `REQUEST_WINDOW_MINUTES` | `10` | rate window |
| `DEFAULT_QUOTA_BYTES` | `5 GiB` | per-key rolling byte quota |
| `SERVER_QUOTA_BYTES` | `20 GiB` | global rolling byte quota |
| `QUOTA_WINDOW_MINUTES` | `10` | quota window |
| `INITIAL_QUOTA_RESERVATION_BYTES` | `64 MiB` | initial reservation for normal downloads; range/FFmpeg jobs conservatively reserve current headroom |
| `QUOTA_MONITOR_SECONDS` | `0.5` | on-disk quota observation interval |
| `TASK_RETENTION_MINUTES` | `10` | completed/error task retention |
| `YTDLP_COOKIES_FILE` | unset | server-side cookies |
| `YTDLP_PROXY` | unset | egress proxy |
| `YTDLP_IMPERSONATE` | unset | yt-dlp impersonation target |
| `ALLOW_PRIVATE_URLS` | `false` | SSRF safety switch |

## Why not Celery/Redis/FastAPI?

They do not solve the core problem by themselves. For this service, SQLite provides the required transactional state and queue semantics without forcing another daemon into a small deployment. If the service later needs multi-host scheduling at high throughput, the repository interfaces can be moved to PostgreSQL/Redis without changing the legacy HTTP adapters.

## Storage backends

The current implementation intentionally keeps **local storage** as the only built-in backend. Several forks experimented with R2/GCS; the useful lesson is to introduce a storage interface when remote object storage is actually needed, rather than baking one vendor into task logic. The API already stores task file references separately from queue state, so that migration is straightforward.

## Tests

```bash
pip install -r requirements.txt pytest
pytest -q
```

The tests cover transactional claims, true rolling limits/quota behavior, URL/filename validation and legacy HTTP response shapes. Add fixture-based yt-dlp integration tests in CI using stable public test URLs; do not make the core unit suite depend on YouTube availability.

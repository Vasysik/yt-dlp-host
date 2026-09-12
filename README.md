# yt-dlp-host

A self-hosted, Dockerized HTTP API for `yt-dlp`, built for reliable media downloading from your own server.

Use it from bots, applications, scripts, or other services to download video, audio, metadata, and live media through a simple API. `yt-dlp-host` provides a persistent task queue, dedicated workers, API keys, quotas, rate limits, FFmpeg processing, JSON or SQLite state, and automatic access to current `yt-dlp` fixes.

## Features

- Video, audio, metadata, and live-media downloads through a simple HTTP API.
- Persistent asynchronous task queue with dedicated download workers.
- API keys, permissions, rolling rate limits, and download quotas.
- FFmpeg processing for audio extraction, remuxing, clipping, and format conversion.
- SQLite or JSON state backends.
- Server-side cookies, proxy, and impersonation configuration.
- Docker-first production deployment with Gunicorn, Deno, and rolling `yt-dlp` nightly updates.
- Backward compatible with clients using the original `yt-dlp-host` API.

## Architecture and reliability

- **Pluggable state backend.** SQLite/WAL is the recommended default; the original `api_keys.json` + `tasks.json` mode remains a live legacy backend with process locking and atomic writes.
- **API and worker are separate processes.** Importing Flask no longer starts download threads. Gunicorn can safely run multiple web workers.
- **Durable queue with leases.** A task is atomically claimed once; crashed workers are recoverable after the lease expires.
- **Real rolling rate limits and quota reservations.** Quota grows from yt-dlp progress and an independent on-disk monitor rather than performing a second metadata request just to guess size.
- **Safe file resolution and cryptographically random task IDs.**
- **Current YouTube runtime requirements.** The Docker image includes Deno and deliberately installs the newest `yt-dlp` nightly on every uncached production rebuild, so YouTube extractor fixes reach production quickly.
- **Cookies/proxy/impersonation are configuration, not source patches.**
- **Legacy JSON stays usable.** SQLite can one-time import old files, or `STORAGE_BACKEND=json` can keep using them directly.
- **No framework rewrite for its own sake.** Flask remains the HTTP surface; internals are the part that was replaced.

## API compatibility

The established routes remain the supported API:

`POST /get_video`, `/get_audio`, `/get_live_video`, `/get_live_audio`, `/get_info`, `/create_key`, `/check_permissions`

`GET /status/<task_id>`, `/files/<path>`, `/get_keys`, `/get_key/<name>`, `/health`

`DELETE /delete_key/<name>`

Existing response keys and status codes are intentionally kept where practical, including the historical plaintext key-return endpoints. New clients use the same routes as existing clients; there is no second versioned API surface to keep in sync.

The complete route-by-route API reference is documented in [`docs/api.md`](docs/api.md). A production-oriented smoke/e2e checklist is in [`docs/testing.md`](docs/testing.md).

Two historically unauthenticated capability-style routes remain public by default for backward compatibility: `/status/<task_id>` and `/files/<path>`. Task IDs are now generated with `secrets`, and paths are strictly scoped to a known task. Set `LEGACY_PUBLIC_STATUS=false` and `LEGACY_PUBLIC_FILES=false` to require the owning API key on those same routes.

## Start

```bash
cp .env.example .env
# set ADMIN_API_KEY for deterministic production credentials (recommended)
docker compose up --build
```

The API is at `http://localhost:5000`; the worker is a separate Compose service. Both join the existing external `yt-dlp-net` network.

### Rolling yt-dlp in production

`yt-dlp` is intentionally **not pinned**. The Dockerfile upgrades it with `--pre`, which selects the current nightly build. Other application dependencies remain pinned. The bundled scheduler rebuilds and recreates `api` and `worker` every day at 03:00 with `--pull --no-cache`; the no-cache flag is required so a cached pip layer cannot leave yt-dlp stale.

The scheduler defaults to `/opt/yt-dlp-host`. If the checkout lives elsewhere, set `HOST_PROJECT_DIR` in `.env`. The project is mounted into the scheduler at the same absolute host path so Compose bind mounts continue to resolve correctly through `/var/run/docker.sock`.

After a rebuild, the deployed yt-dlp version is visible at `/health` as `yt_dlp_version`.

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

## API

There is one public HTTP API surface. Existing and new clients use the same `/get_video`, `/get_audio`, `/get_info`, `/get_live_*`, `/status`, `/files`, and key-management routes. The refactor changed the implementation behind those routes, not the client contract.

See [`docs/api.md`](docs/api.md) for authentication, permissions, every request field, polling, `info.json`, quality extraction, media/file delivery, Range requests, error shapes, key management, JSON mode, and complete client examples.

New optional capabilities are added to the existing routes when they can be introduced without breaking old clients. For example, `output_filename` is an optional request field. Stricter ownership for `/status` and `/files` is available through `LEGACY_PUBLIC_STATUS=false` and `LEGACY_PUBLIC_FILES=false` rather than through a second API namespace.

## State backends and legacy JSON mode

SQLite remains the recommended production default:

```env
STORAGE_BACKEND=sqlite
```

It uses `DATABASE_PATH` and performs a one-time import from the configured legacy `jsons/api_keys.json` and `jsons/tasks.json`. You can also invoke the import explicitly with:

```bash
python scripts/migrate_legacy.py
```

The original JSON files are also a fully live backend, not just an import source:

```env
STORAGE_BACKEND=json
```

In JSON mode, API-key and task state is read from and written back to:

- `LEGACY_KEYS_FILE` (default `/app/jsons/api_keys.json`)
- `LEGACY_TASKS_FILE` (default `/app/jsons/tasks.json`)

Those two files keep the old public object shape. Modern concurrency bookkeeping (worker leases, true rolling request events and transactional-style quota reservations) is stored separately in `JSON_STATE_FILE`, default `/app/jsons/.yt-dlp-host-state.json`. A single `flock` lock plus atomic `os.replace` writes prevents API and worker processes from clobbering each other's JSON updates.

This means an existing legacy installation can stop the old process, select `STORAGE_BACKEND=json`, and continue with its existing `api_keys.json` and `tasks.json` without first converting them to SQLite. SQLite is still preferred for heavier concurrency.

Do **not** run the original pre-refactor server and the new JSON backend against the same files at the same time: the old implementation does not participate in the new file lock and can overwrite concurrent changes. Stop the old containers before starting the new JSON-mode API/worker.

## Important environment variables

| Variable | Default | Purpose |
|---|---:|---|
| `HOST_PROJECT_DIR` | `/opt/yt-dlp-host` | host checkout path used by the auto-update scheduler |
| `STORAGE_BACKEND` | `sqlite` | `sqlite` (recommended) or live legacy `json` state |
| `DATABASE_PATH` | `/app/data/yt-dlp-host.sqlite3` | SQLite state path |
| `JSON_STATE_FILE` | `/app/jsons/.yt-dlp-host-state.json` | JSON-mode sidecar for leases/rate/quota metadata |
| `LEGACY_KEYS_FILE` | `/app/jsons/api_keys.json` | legacy/live JSON API keys |
| `LEGACY_TASKS_FILE` | `/app/jsons/tasks.json` | legacy/live JSON tasks |
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

## Download file storage

The state backend described above is separate from downloaded-file storage. The current implementation intentionally keeps **local downloaded-file storage** as the only built-in backend. Several forks experimented with R2/GCS; the useful lesson is to introduce a storage interface when remote object storage is actually needed, rather than baking one vendor into task logic. The API already stores task file references separately from queue state, so that migration is straightforward.

## Tests

```bash
pip install -r requirements.txt pytest
pytest -q
```

The tests cover the shared state contract on SQLite and live JSON, claims, rolling limits/quota behavior, URL/filename validation, established HTTP response shapes, optional status ownership, and the single API surface. Real yt-dlp/ffmpeg compatibility is intentionally checked separately because public extractors are network-dependent. See [`docs/testing.md`](docs/testing.md) and the helper `scripts/smoke_test.sh`.

## Hosted option

If you don’t want to self-host with Docker, [Vid Kraken](https://vidkraken.com) is a managed YouTube download API (info / mp3 / mp4 endpoints).

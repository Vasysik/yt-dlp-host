# Audit of Vasysik/yt-dlp-host and its GitHub network

Audit date: 2026-08-22.

## Baseline repository

The original service is small (~843 lines across `config.py` and `src/*.py`) but couples HTTP handling, authentication, rate limiting, quota accounting, queueing, worker lifecycle and persistence through shared JSON files and import-time background threads.

The key architectural risks found in the uploaded source were:

- non-atomic `json.load` / `json.dump` state shared by HTTP handlers and multiple worker threads;
- a Flask import starts a daemon queue thread and a `ThreadPoolExecutor`;
- WAITING jobs are submitted without an atomic claim, so the same job can be submitted more than once;
- Gunicorn/reloader/multiple containers multiply those background loops;
- "rate limiting" counts retained task records rather than requests in a time window;
- "memory quota" is a rolling size estimate stored in key JSON, and check/update is race-prone;
- pre-download size estimation performs a second yt-dlp extraction and fails the whole task when size cannot be guessed;
- API keys are plaintext, rescanned linearly, and the whole key file is rewritten on every authenticated call;
- task IDs use `random.choices` rather than a cryptographic/UUID generator;
- `/status/<task_id>` and `/files/<path>` are public in the actual implementation;
- file access uses string-prefix path validation and no task ownership checks;
- `extract_qualities` indexes optional fields such as `language`/`width` directly;
- live range math mixes wall-clock Unix time with media-relative ranges;
- downloaded output is selected with `os.listdir(...)[0]`;
- Flask's development server is the production Docker command;
- the container runs as root, `yt-dlp` is unpinned, and no current YouTube JS runtime is installed.

## Issues — complete inventory

There is one issue in the repository network's main issue tracker and no closed issues:

| Issue | State | Finding | Disposition |
|---|---|---|---|
| #14 `Cookies` | open | YouTube bot/login challenges need cookie support | Solved as server-side `YTDLP_COOKIES_FILE`; no arbitrary filesystem path is accepted from callers |

## Pull requests — complete inventory

| PR | State | Theme | Audit disposition |
|---:|---|---|---|
| #1 | merged | live endpoints | Preserve legacy endpoints; replace worker/range internals |
| #2 | merged | info optimization | Keep `/get_info`; sanitize/atomically write info JSON |
| #3 | merged | quality formats | Preserve format selectors and `?qualities` output |
| #4 | merged | memory quota/controller | Replace JSON accounting with transactional rolling byte reservations |
| #5 | merged | ranges | Preserve VOD range API; correct live range semantics |
| #6 | closed, unmerged | Google Cloud Run/GCS/cookies | Take stateless-deployment/storage lessons, not vendor-specific patch stack |
| #7 | open | Docker/Gunicorn/deployment, then auth removal | Reject as-is: removing auth/legacy behavior is incompatible; keep only production-server lesson |
| #8 | open | `PORT` env | Implement cleanly through Gunicorn config and direct-run fallback |
| #9 | merged | refactor/FastAPI experiment/revert | Strong signal not to rewrite frameworks for its own sake; fix state/lifecycle first |
| #10 | merged | output format | Preserve request field; use yt-dlp/FFmpeg processing rather than filename hacks |
| #11 | merged | language test | Make format metadata optional-safe |
| #12 | merged | GIF/start time experiments | Preserve numeric time support; do not resurrect brittle GIF special cases |
| #13 | merged | GIF fixes | Superseded by later removal; no special-case port |
| #15 | merged | audio/video fixes, GIF removal | Keep the cleanup direction; deterministic final-file discovery |
| #16 | open | custom filename, search, MP3 ID3 metadata | Port custom filename safely; search/metadata belong in v2 if needed, not a legacy mutation |
| #17 | open | Gunicorn | Intent is correct, PR content is malformed; implement clean Gunicorn config instead |

## Forks — complete network inventory (32)

### No materially unique implementation to port

These are identical to, behind, or effectively contained by the main repository for the audit's purposes:

1. `amosrazi/yt-dlp-host-md`
2. `ArtsiomKoptsiukh/yt-dlp-host`
3. `azrilamil/yt-dlp-host`
4. `deku0019523/yt-dlp-host`
5. `federico-00215/yt-dlp-host`
6. `hankol-eh/yt-dlp-api-service`
7. `iuranemo/yt-dlp-host`
8. `junior05577/yt-dlp-host`
9. `lupuionu187-max/yt-dlp-host`
10. `muhammadwaqas476074/yt-dlp-host`
11. `ocordeiro/yt-dlp-host`
12. `pedpontes/yt-dlp-host`
13. `ravi-oliveira/yt-dlp-host`
14. `Sirakawakyou/yt-dlp-host`
15. `TeeemuAI/yt-dlp-host`
16. `tixnz0/yt-dlp-host`
17. `xpomul/yt-dlp-host`

### Divergent forks and what they teach us

| Fork | Unique direction | What is worth keeping |
|---|---|---|
| `2-fly-4-ai/yt-dlp-host` | Cloudflare R2/storage work, env variables | Storage should be abstractable; do not couple queue state to local files |
| `adepanges/yt-dlp-host` | env config, admin key, cookies, curl-cffi/impersonation, estimator fallbacks/logging | Most useful operational fork: move config to env and support cookies/proxy/impersonation centrally; do not keep JSON/estimator workarounds |
| `bgizdov/yt-dlp-host` | custom filename, search, mutagen ID3, logging | Safe custom filename is useful; search/metadata should be explicit v2 features |
| `cayohrun/yt-dlp-host` | Gunicorn/deployment and later API/auth removal | Production server yes; auth removal no |
| `dwj0602/yt-dlp-host` | import/CMD/package startup fixes | Use a real package and stable module entrypoints |
| `jimeny-ent/yt-dlp-host` | Cloudflare bucket/storage synchronization experiments | Reinforces storage-backend separation |
| `llj0824/yt-clipping-service` | clipping/transcoding, cookies refresh, `noplaylist`, social-media output | `noplaylist=true` by default and clean postprocessing are useful; product-specific cookie scripts are not |
| `ndubs97/yt-dlp-host` | Gunicorn/start command, `src/__init__.py` | Production WSGI + valid Python package |
| `Nikki9619/yt-dlp-server` | deployment, ScraperAPI, audio language preference | Proxy and language preference can be future policy knobs; not a generic default |
| `OmarAmer33/yt-dlp-host` | deployment-oriented app/Procfile/Docker updates | Deployment ergonomics only; no need for another application architecture |
| `shashti-q8/yt-dlp-host` | auth/key-file customization | Do not commit/customize secrets as repository state |
| `shedenk/yt-dlp-host` | compose filename rename | No functional feature |
| `vuisme/yt-dlp-host` | GitHub Actions Docker build plus config tweaks | CI/image publishing is useful; secret-file changes are not |
| `yg774850/yt-dlp-host` | cookies from env text/temp files; size-estimate failure becomes `1` byte | Confirms cookie and estimation pain; use a mounted read-only cookie file and progress/final byte accounting instead |
| `Ziltosh/yt-dlp-host` | proxy configuration and route wiring | Central proxy configuration is useful; arbitrary per-request proxying should require explicit trust/policy |

## Architecture selected for the cleanup

### Keep Flask as the legacy adapter

Changing Flask to FastAPI does not fix JSON races, duplicate workers, quota accounting or lifecycle coupling. A previous PR already explored/reverted framework churn. The cleaned implementation therefore keeps Flask only at the HTTP edge.

### SQLite/WAL for local durable state

SQLite gives the small service transactions and atomic job claims without adding mandatory Redis/Celery infrastructure. It stores API keys, jobs, request events and rolling quota reservations. A later multi-host deployment can replace this repository layer with PostgreSQL/Redis while keeping HTTP compatibility.

### Separate API and worker processes

The web app never starts downloader threads on import. A separate `python -m yt_dlp_host.worker` process claims jobs atomically and maintains leases. Multiple API workers are safe; multiple download workers can also compete for jobs without submitting one WAITING task repeatedly.

### Legacy API adapter + `/api/v2`

Legacy paths and response shapes remain available. V2 adds ownership-checked task status/files and a consistent place for future features. Historical plaintext key retrieval remains only because strict legacy compatibility requires it; new APIs should never add more secret-retrieval surfaces.

### Quota based on observed bytes

Instead of a mandatory second metadata extraction and a fragile home-grown format parser, normal reservations expand from yt-dlp progress and an independent task-directory size monitor, then reconcile to actual output bytes. FFmpeg/range jobs conservatively reserve the task's currently available quota headroom up front because upstream progress hooks can be sparse or absent; this can serialize clipped jobs for one key, but avoids concurrent overcommit. Final reconciliation shrinks the reservation to actual output bytes.

### Current YouTube runtime

The Docker image includes Deno and `yt-dlp[default]`. Cookies, proxy, impersonation and extractor args are configuration, so they can be updated without editing downloader source.

## Compatibility/migration policy

- One-time import of old `jsons/api_keys.json` and `jsons/tasks.json` into SQLite.
- Same legacy permission strings.
- Same legacy task endpoint names and waiting/task-id response.
- Same default 10-minute retention, 60/10-minute limit, 5 GiB per-key and 20 GiB global rolling quota semantics, but implemented correctly.
- `/status` and `/files` remain public capability URLs by default because the old implementation actually behaved that way; both can be locked down with environment switches.
- `src.server:app` and top-level `config.py` compatibility shims remain.

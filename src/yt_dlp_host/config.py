from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int, minimum: int = 0) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _float(name: str, default: float, minimum: float = 0.0) -> float:
    value = float(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _optional_path(name: str) -> Path | None:
    value = os.getenv(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _json_object(name: str) -> dict[str, Any]:
    value = os.getenv(name)
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    download_dir: Path
    database_path: Path
    legacy_tasks_file: Path
    legacy_keys_file: Path

    cleanup_minutes: int
    request_limit: int
    request_window_minutes: int
    max_workers: int
    worker_poll_seconds: float
    worker_lease_seconds: int

    default_quota_bytes: int
    server_quota_bytes: int
    quota_window_minutes: int
    quota_size_buffer: float
    initial_quota_reservation_bytes: int
    quota_monitor_seconds: float

    admin_api_key: str | None
    cookies_file: Path | None
    proxy: str | None
    impersonate: str | None
    extractor_args: dict[str, Any]
    noplaylist: bool
    allow_private_urls: bool
    legacy_public_files: bool
    legacy_public_status: bool
    max_request_bytes: int
    socket_timeout_seconds: int
    retries: int
    fragment_retries: int
    concurrent_fragments: int
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        download_dir = Path(os.getenv("DOWNLOAD_DIR", "/app/downloads")).expanduser().resolve()
        database_path = Path(os.getenv("DATABASE_PATH", "/app/data/yt-dlp-host.sqlite3")).expanduser().resolve()
        settings = cls(
            download_dir=download_dir,
            database_path=database_path,
            legacy_tasks_file=Path(os.getenv("LEGACY_TASKS_FILE", "jsons/tasks.json")).expanduser().resolve(),
            legacy_keys_file=Path(os.getenv("LEGACY_KEYS_FILE", "jsons/api_keys.json")).expanduser().resolve(),
            cleanup_minutes=_int("TASK_RETENTION_MINUTES", 10, 1),
            request_limit=_int("REQUEST_LIMIT", 60, 1),
            request_window_minutes=_int("REQUEST_WINDOW_MINUTES", 10, 1),
            max_workers=_int("MAX_WORKERS", 4, 1),
            worker_poll_seconds=_float("WORKER_POLL_SECONDS", 0.5, 0.05),
            worker_lease_seconds=_int("WORKER_LEASE_SECONDS", 900, 30),
            default_quota_bytes=_int("DEFAULT_QUOTA_BYTES", 5 * 1024**3, 1),
            server_quota_bytes=_int("SERVER_QUOTA_BYTES", 20 * 1024**3, 1),
            quota_window_minutes=_int("QUOTA_WINDOW_MINUTES", 10, 1),
            quota_size_buffer=_float("QUOTA_SIZE_BUFFER", 1.10, 1.0),
            initial_quota_reservation_bytes=_int("INITIAL_QUOTA_RESERVATION_BYTES", 64 * 1024**2, 1),
            quota_monitor_seconds=_float("QUOTA_MONITOR_SECONDS", 0.5, 0.1),
            admin_api_key=os.getenv("ADMIN_API_KEY") or None,
            cookies_file=_optional_path("YTDLP_COOKIES_FILE"),
            proxy=os.getenv("YTDLP_PROXY") or None,
            impersonate=os.getenv("YTDLP_IMPERSONATE") or None,
            extractor_args=_json_object("YTDLP_EXTRACTOR_ARGS_JSON"),
            noplaylist=_bool("YTDLP_NOPLAYLIST", True),
            allow_private_urls=_bool("ALLOW_PRIVATE_URLS", False),
            legacy_public_files=_bool("LEGACY_PUBLIC_FILES", True),
            legacy_public_status=_bool("LEGACY_PUBLIC_STATUS", True),
            max_request_bytes=_int("MAX_REQUEST_BYTES", 1024 * 1024, 1024),
            socket_timeout_seconds=_int("YTDLP_SOCKET_TIMEOUT", 30, 1),
            retries=_int("YTDLP_RETRIES", 5, 0),
            fragment_retries=_int("YTDLP_FRAGMENT_RETRIES", 10, 0),
            concurrent_fragments=_int("YTDLP_CONCURRENT_FRAGMENTS", 1, 1),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
        settings.ensure_directories()
        return settings

    def ensure_directories(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()

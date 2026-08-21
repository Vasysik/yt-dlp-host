"""Legacy compatibility module.

The new implementation is configured with environment variables. This file keeps
old `import config` deployments from failing while exposing the most familiar
attributes.
"""
from dataclasses import dataclass
from typing import Final

from yt_dlp_host.config import settings


@dataclass(frozen=True)
class StorageConfig:
    DOWNLOAD_DIR: Final[str] = str(settings.download_dir)
    TASKS_FILE: Final[str] = str(settings.legacy_tasks_file)
    KEYS_FILE: Final[str] = str(settings.legacy_keys_file)


@dataclass(frozen=True)
class TaskConfig:
    CLEANUP_TIME_MINUTES: Final[int] = settings.cleanup_minutes
    REQUEST_LIMIT: Final[int] = settings.request_limit
    MAX_WORKERS: Final[int] = settings.max_workers


@dataclass(frozen=True)
class MemoryConfig:
    DEFAULT_QUOTA_GB: Final[int] = settings.default_quota_bytes // 1024**3
    DEFAULT_QUOTA_BYTES: Final[int] = settings.default_quota_bytes
    QUOTA_RATE_MINUTES: Final[int] = settings.quota_window_minutes
    SIZE_BUFFER: Final[float] = settings.quota_size_buffer
    AVAILABLE_BYTES: Final[int] = settings.server_quota_bytes


storage = StorageConfig()
task = TaskConfig()
memory = MemoryConfig()

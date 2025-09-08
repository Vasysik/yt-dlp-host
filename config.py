from dataclasses import dataclass
from typing import Final

@dataclass
class StorageConfig:
    DOWNLOAD_DIR: Final[str] = '/app/downloads'
    TASKS_FILE: Final[str] = 'jsons/tasks.json'
    KEYS_FILE: Final[str] = 'jsons/api_keys.json'

@dataclass
class TaskConfig:
    CLEANUP_TIME_MINUTES: Final[int] = 10
    REQUEST_LIMIT: Final[int] = 60
    MAX_WORKERS: Final[int] = 4

@dataclass
class MemoryConfig:
    DEFAULT_QUOTA_GB: Final[int] = 5
    DEFAULT_QUOTA_BYTES: Final[int] = 5 * 1024 * 1024 * 1024
    QUOTA_RATE_MINUTES: Final[int] = 10
    SIZE_BUFFER: Final[float] = 1.10
    AVAILABLE_BYTES: Final[int] = 20 * 1024 * 1024 * 1024

storage = StorageConfig()
task = TaskConfig()
memory = MemoryConfig()

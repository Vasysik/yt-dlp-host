from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional, List

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "yt-dlp-fastapi"
    API_V1_STR: str = "/api/v1"

    # Database
    SQLALCHEMY_DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR / 'yt_dlp_app.db'}"

    # File system
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"
    
    # Task management
    TASK_CLEANUP_TIME_MINUTES: int = 10
    REQUEST_LIMIT_PER_CLEANUP_TIME: int = 60 
    MAX_WORKERS: int = 4 # For ThreadPoolExecutor

    # API key settings
    DEFAULT_MEMORY_QUOTA_BYTES: int = 5 * 1024 * 1024 * 1024  # 5GB
    DEFAULT_MEMORY_QUOTA_RATE_MINUTES: int = 10
    INITIAL_ADMIN_KEY_NAME: str = "admin"
    INITIAL_ADMIN_KEY_VALUE: Optional[str] = None # Генерируется, если не задан в env

    # Memory control
    SIZE_ESTIMATION_BUFFER_FACTOR: float = 1.10
    AVAILABLE_SERVER_MEMORY_BYTES: int = 20 * 1024 * 1024 * 1024  # 20GB

    # Permissions
    PERM_GET_VIDEO: str = "get_video"
    PERM_GET_AUDIO: str = "get_audio"
    PERM_GET_LIVE_VIDEO: str = "get_live_video"
    PERM_GET_LIVE_AUDIO: str = "get_live_audio"
    PERM_GET_INFO: str = "get_info"
    PERM_CREATE_KEY: str = "create_key"
    PERM_DELETE_KEY: str = "delete_key"
    PERM_GET_KEY: str = "get_key"
    PERM_LIST_KEYS: str = "get_keys"

    @property
    def ALL_PERMISSIONS(self) -> List[str]:
        return [
            self.PERM_GET_VIDEO, self.PERM_GET_AUDIO, self.PERM_GET_LIVE_VIDEO, self.PERM_GET_LIVE_AUDIO,
            self.PERM_GET_INFO, self.PERM_CREATE_KEY, self.PERM_DELETE_KEY, self.PERM_GET_KEY, self.PERM_LIST_KEYS,
        ]

    @property
    def VALID_PERMISSIONS_SET(self) -> set[str]:
        return set(self.ALL_PERMISSIONS)

    model_config = SettingsConfigDict(case_sensitive=True, env_file=str(BASE_DIR / ".env"), extra='ignore')


settings = Settings()

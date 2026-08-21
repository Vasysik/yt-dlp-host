from __future__ import annotations

from enum import StrEnum


class TaskStatus(StrEnum):
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class TaskType(StrEnum):
    GET_VIDEO = "get_video"
    GET_AUDIO = "get_audio"
    GET_INFO = "get_info"
    GET_LIVE_VIDEO = "get_live_video"
    GET_LIVE_AUDIO = "get_live_audio"


LEGACY_TASK_PERMISSIONS = {item.value for item in TaskType}
ADMIN_PERMISSIONS = {
    "create_key",
    "delete_key",
    "get_key",
    "get_keys",
    *LEGACY_TASK_PERMISSIONS,
}

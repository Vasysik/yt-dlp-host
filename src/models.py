from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum

class TaskStatus(Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class TaskType(Enum):
    GET_VIDEO = "get_video"
    GET_AUDIO = "get_audio"
    GET_INFO = "get_info"
    GET_LIVE_VIDEO = "get_live_video"
    GET_LIVE_AUDIO = "get_live_audio"

@dataclass
class Task:
    task_id: str
    key_name: str
    status: TaskStatus
    task_type: TaskType
    url: str
    video_format: Optional[str] = "bestvideo"
    audio_format: Optional[str] = "bestaudio"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    force_keyframes: bool = False
    start: Optional[int] = 0
    duration: Optional[int] = None
    completed_time: Optional[str] = None
    error: Optional[str] = None
    file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            'key_name': self.key_name,
            'status': self.status.value,
            'task_type': self.task_type.value,
            'url': self.url
        }
        
        optional_fields = ['video_format', 'audio_format', 'start_time', 
                          'end_time', 'force_keyframes', 'start', 'duration',
                          'completed_time', 'error', 'file']
        
        for field_name in optional_fields:
            value = getattr(self, field_name, None)
            if value is not None:
                data[field_name] = value
        
        return data

@dataclass
class ApiKey:
    key: str
    name: str
    permissions: List[str] = field(default_factory=list)
    memory_quota: int = 5368709120
    memory_usage: List[Dict] = field(default_factory=list)
    last_access: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key,
            'permissions': self.permissions,
            'memory_quota': self.memory_quota,
            'memory_usage': self.memory_usage,
            'last_access': self.last_access
        }

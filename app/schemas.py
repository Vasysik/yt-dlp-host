from pydantic import BaseModel, HttpUrl, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.models import TaskStatusEnum
from app.core.config import settings

class ApiKeyBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    permissions: List[str]
    memory_quota_bytes: Optional[int] = Field(settings.DEFAULT_MEMORY_QUOTA_BYTES, gt=0)

    @field_validator('permissions')
    def validate_permissions(cls, v):
        for perm in v:
            if perm not in settings.VALID_PERMISSIONS_SET:
                raise ValueError(f"Invalid permission: {perm}")
        return v

class ApiKeyCreate(ApiKeyBase):
    pass

class ApiKeyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50, pattern="^[a-zA-Z0-9_-]+$")
    permissions: Optional[List[str]] = None
    memory_quota_bytes: Optional[int] = Field(None, gt=0)
    is_active: Optional[bool] = None

    @field_validator('permissions')
    def validate_permissions_update(cls, v):
        if v is not None:
            for perm in v:
                if perm not in settings.VALID_PERMISSIONS_SET:
                    raise ValueError(f"Invalid permission: {perm}")
        return v

class ApiKeyInDBBase(ApiKeyBase):
    id: int
    key: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

class ApiKeyPublic(ApiKeyInDBBase):
    key: Optional[str] = Field(None, exclude=True)

class ApiKeyCreateResponse(BaseModel):
    message: str
    name: str
    key: str

class TaskRequestBase(BaseModel):
    url: HttpUrl

class GetVideoRequest(TaskRequestBase):
    video_format: str = Field("bestvideo[height<=1080]", examples=["bestvideo", "bestvideo[height<=720]+bestaudio[ext=m4a]"])
    audio_format: str = Field("bestaudio[abr<=129]", examples=["bestaudio", "worstaudio"])
    start_time: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}:\d{2}(\.\d+)?$", examples=["00:01:30", "1:15:10.500"])
    end_time: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}:\d{2}(\.\d+)?$", examples=["00:02:00"])
    force_keyframes: bool = False

    @model_validator(mode='after')
    def check_time_consistency(self):
        if self.end_time and not self.start_time:
            pass 
        return self

class GetAudioRequest(TaskRequestBase):
    audio_format: str = Field("bestaudio[abr<=129]")
    start_time: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}:\d{2}(\.\d+)?$")
    end_time: Optional[str] = Field(None, pattern=r"^\d{1,2}:\d{2}:\d{2}(\.\d+)?$")
    force_keyframes: bool = False
    # output_audio_format: str = "mp3"

class GetInfoRequest(TaskRequestBase):
    pass

class GetLiveVideoRequest(TaskRequestBase):
    video_format: str = Field("bestvideo[height<=1080]")
    audio_format: str = Field("bestaudio[abr<=129]")
    start_offset_seconds: Optional[int] = Field(0, ge=0, description="Offset from current time in seconds to start recording (for DVR). Not reliably implemented.")
    duration_seconds: int = Field(..., gt=0, description="Duration of the recording in seconds. Not reliably implemented for all live streams.")

class GetLiveAudioRequest(TaskRequestBase):
    audio_format: str = Field("bestaudio[abr<=129]")
    start_offset_seconds: Optional[int] = Field(0, ge=0, description="Offset from current time in seconds to start recording (for DVR). Not reliably implemented.")
    duration_seconds: int = Field(..., gt=0, description="Duration of the recording in seconds. Not reliably implemented for all live streams.")


class TaskCreateInternal(BaseModel):
    task_type: str
    params: Dict[str, Any]
    api_key_name: str

class TaskCreateResponse(BaseModel):
    task_id: str
    status: TaskStatusEnum

class TaskInDB(BaseModel):
    id: str
    task_type: str
    status: TaskStatusEnum
    params: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    api_key_name: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}

class TaskPublic(TaskInDB):
    pass

class InfoFileQualityDetail(BaseModel):
    abr: Optional[int] = None
    acodec: Optional[str] = None
    audio_channels: Optional[int] = None
    filesize: Optional[int] = None
    height: Optional[int] = None
    width: Optional[int] = None
    fps: Optional[int] = None
    vcodec: Optional[str] = None
    format_note: Optional[str] = None
    dynamic_range: Optional[str] = None

class InfoFileQualitiesResponse(BaseModel):
    audio: Dict[str, InfoFileQualityDetail] = {}
    video: Dict[str, InfoFileQualityDetail] = {}

class InfoFileFilteredResponse(BaseModel):
    qualities: Optional[InfoFileQualitiesResponse] = None
    model_config = {"extra": "allow"}

class MessageResponse(BaseModel):
    message: str

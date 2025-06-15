import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Set

from fastapi import HTTPException, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from starlette.status import (
    HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN,
    HTTP_429_TOO_MANY_REQUESTS, HTTP_503_SERVICE_UNAVAILABLE
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app import crud, models
from app.database import get_db

API_KEY_NAME_HEADER = "X-API-Key"
api_key_header_scheme = APIKeyHeader(name=API_KEY_NAME_HEADER, auto_error=False)

def generate_api_key_value() -> str:
    return secrets.token_urlsafe(32)

async def get_current_api_key_object(
    api_key_value_from_header: Optional[str] = Security(api_key_header_scheme),
    db: AsyncSession = Depends(get_db),
) -> models.ApiKey:
    if not api_key_value_from_header:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="API key required")
    
    db_api_key = await crud.get_api_key(db, api_key_value=api_key_value_from_header)
    if not db_api_key or not db_api_key.is_active:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API key")
    
    await crud.update_api_key_last_used(db, db_api_key.name)
    # await db.refresh(db_api_key)

    return db_api_key


class Authorize:
    def __init__(self, required_permissions: List[str]):
        self.required_permissions_set = set(required_permissions)

    async def __call__(
        self, 
        api_key_obj: models.ApiKey = Depends(get_current_api_key_object), 
        db: AsyncSession = Depends(get_db)
    ):
        user_permissions = set(api_key_obj.permissions)
        if not self.required_permissions_set.issubset(user_permissions):
            missing_perms = list(self.required_permissions_set - user_permissions)
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {', '.join(self.required_permissions_set)}. Missing: {', '.join(missing_perms)}"
            )
        
        rate_limit_window_start = datetime.utcnow() - timedelta(minutes=settings.TASK_CLEANUP_TIME_MINUTES)
        
        tasks_in_window = await crud.get_tasks_by_api_key_and_time_window_db(
            db, api_key_obj.name, rate_limit_window_start
        )
        if len(tasks_in_window) >= settings.REQUEST_LIMIT_PER_CLEANUP_TIME:
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded. Maximum {settings.REQUEST_LIMIT_PER_CLEANUP_TIME} "
                    f"task creation requests per {settings.TASK_CLEANUP_TIME_MINUTES} minutes for this API key."
                )
            )
        
        return api_key_obj


async def check_memory_quotas_and_server_limit(
    api_key_obj: models.ApiKey, 
    requested_size_bytes: int, 
    db: AsyncSession
) -> None:
    if requested_size_bytes <= 0:
        return
    
    memory_rate_limit_window_start = datetime.utcnow() - timedelta(minutes=settings.DEFAULT_MEMORY_QUOTA_RATE_MINUTES)
    
    current_server_usage_bytes = await crud.get_total_memory_usage_server_db(db, memory_rate_limit_window_start)
    
    if current_server_usage_bytes + requested_size_bytes > settings.AVAILABLE_SERVER_MEMORY_BYTES:
        current_usage_gb = current_server_usage_bytes / (1024**3)
        requested_gb = requested_size_bytes / (1024**3)
        available_gb = (settings.AVAILABLE_SERVER_MEMORY_BYTES - current_server_usage_bytes) / (1024**3)
        raise HTTPException(
            status_code=HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Server memory limit exceeded. "
                f"Current usage in window: {current_usage_gb:.2f}GB, "
                f"Requested: {requested_gb:.2f}GB, "
                f"Server available in window: {available_gb:.2f}GB."
            )
        )
    
    if api_key_obj.memory_quota_bytes <= 0:
        return

    memory_usage_entries_for_key = await crud.get_memory_usage_for_api_key_db(
        db, 
        api_key_obj.name, 
        memory_rate_limit_window_start
    )
    current_key_usage_bytes = sum(mu.size_bytes for mu in memory_usage_entries_for_key)

    if current_key_usage_bytes + requested_size_bytes > api_key_obj.memory_quota_bytes:
        current_usage_gb = current_key_usage_bytes / (1024**3)
        quota_gb = api_key_obj.memory_quota_bytes / (1024**3)
        requested_gb = requested_size_bytes / (1024**3)
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS, 
            detail=(
                f"User memory quota exceeded for API key '{api_key_obj.name}'. "
                f"Current usage in window: {current_usage_gb:.2f}GB, "
                f"Requested: {requested_gb:.2f}GB, "
                f"Quota: {quota_gb:.2f}GB."
            )
        )

async def record_task_memory_usage(db: AsyncSession, api_key_name: str, task_id: str, size_bytes: int):
    if size_bytes > 0:
        await crud.create_memory_usage_entry_db(db, api_key_name, task_id, size_bytes)

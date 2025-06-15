from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, update, func, and_
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid

from app import models, schemas
from app.core.config import settings

async def get_api_key(db: AsyncSession, api_key_value: str) -> Optional[models.ApiKey]:
    result = await db.execute(select(models.ApiKey).filter(models.ApiKey.key == api_key_value))
    return result.scalars().first()

async def get_api_key_by_name(db: AsyncSession, name: str) -> Optional[models.ApiKey]:
    result = await db.execute(select(models.ApiKey).filter(models.ApiKey.name == name))
    return result.scalars().first()

async def get_api_keys(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[models.ApiKey]:
    result = await db.execute(select(models.ApiKey).offset(skip).limit(limit).order_by(models.ApiKey.name))
    return result.scalars().all()

async def create_api_key_db(db: AsyncSession, name: str, key_value: str, permissions: List[str], memory_quota_bytes: int) -> models.ApiKey:
    db_api_key = models.ApiKey(
        name=name, 
        key=key_value, 
        permissions=permissions,
        memory_quota_bytes=memory_quota_bytes
    )
    db.add(db_api_key)
    await db.commit()
    await db.refresh(db_api_key)
    return db_api_key

async def delete_api_key_db(db: AsyncSession, name: str) -> Optional[models.ApiKey]:
    db_api_key = await get_api_key_by_name(db, name=name)
    if db_api_key:
        await db.delete(db_api_key)
        await db.commit()
        return db_api_key
    return None

async def update_api_key_last_used(db: AsyncSession, api_key_name: str) -> bool:
    stmt = (
        update(models.ApiKey)
        .where(models.ApiKey.name == api_key_name)
        .values(last_used_at=datetime.utcnow())
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

def _generate_task_id() -> str:
    return uuid.uuid4().hex[:16]

async def create_task_db(db: AsyncSession, task_create_internal: schemas.TaskCreateInternal) -> models.Task:
    task_id = _generate_task_id()
    db_task = models.Task(
        id=task_id,
        task_type=task_create_internal.task_type,
        params=task_create_internal.params,
        api_key_name=task_create_internal.api_key_name,
        status=models.TaskStatusEnum.WAITING
    )
    db.add(db_task)
    await db.commit()
    await db.refresh(db_task)
    return db_task

async def get_task_db(db: AsyncSession, task_id: str) -> Optional[models.Task]:
    result = await db.execute(select(models.Task).filter(models.Task.id == task_id))
    return result.scalars().first()

async def get_tasks_by_status_db(db: AsyncSession, status: models.TaskStatusEnum, limit: int = 10) -> List[models.Task]:
    result = await db.execute(
        select(models.Task).filter(models.Task.status == status).order_by(models.Task.created_at).limit(limit)
    )
    return result.scalars().all()

async def update_task_status_db(
    db: AsyncSession, 
    task_id: str, 
    status: models.TaskStatusEnum, 
    result_data: Optional[Dict[str, Any]] = None
) -> Optional[models.Task]:
    
    db_task = await get_task_db(db, task_id)
    if db_task:
        values_to_update = {"status": status, "updated_at": datetime.utcnow()}
        if status in [models.TaskStatusEnum.COMPLETED, models.TaskStatusEnum.ERROR]:
            values_to_update["completed_at"] = datetime.utcnow()
        if result_data is not None:
            values_to_update["result"] = result_data
        
        stmt = update(models.Task).where(models.Task.id == task_id).values(**values_to_update)
        await db.execute(stmt)
        await db.commit()
        await db.refresh(db_task)
        return db_task
    return None

async def get_tasks_for_cleanup_db(db: AsyncSession, cleanup_older_than: datetime) -> List[models.Task]:
    result = await db.execute(
        select(models.Task)
        .filter(models.Task.status.in_([models.TaskStatusEnum.COMPLETED, models.TaskStatusEnum.ERROR]))
        .filter(models.Task.completed_at < cleanup_older_than)
    )
    return result.scalars().all()

async def delete_task_from_db(db: AsyncSession, task_id: str) -> bool:
    stmt = delete(models.Task).where(models.Task.id == task_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0

async def get_tasks_by_api_key_and_time_window_db(
    db: AsyncSession, 
    api_key_name: str, 
    window_start_time: datetime
) -> List[models.Task]:
    result = await db.execute(
        select(models.Task)
        .filter(models.Task.api_key_name == api_key_name)
        .filter(models.Task.created_at >= window_start_time)
    )
    return result.scalars().all()
    
async def count_active_tasks_for_key_db(db: AsyncSession, api_key_name: str) -> int:
    result = await db.execute(
        select(func.count(models.Task.id))
        .filter(models.Task.api_key_name == api_key_name)
        .filter(models.Task.status.in_([models.TaskStatusEnum.WAITING, models.TaskStatusEnum.PROCESSING]))
    )
    return result.scalar_one()

async def create_memory_usage_entry_db(db: AsyncSession, api_key_name: str, task_id: str, size_bytes: int) -> models.MemoryUsage:
    db_mu = models.MemoryUsage(
        api_key_name=api_key_name,
        task_id=task_id,
        size_bytes=size_bytes,
        timestamp=datetime.utcnow()
    )
    db.add(db_mu)
    await db.commit()
    await db.refresh(db_mu)
    return db_mu

async def get_memory_usage_for_api_key_db(
    db: AsyncSession, 
    api_key_name: str, 
    window_start_time: datetime
) -> List[models.MemoryUsage]:
    result = await db.execute(
        select(models.MemoryUsage)
        .filter(models.MemoryUsage.api_key_name == api_key_name)
        .filter(models.MemoryUsage.timestamp >= window_start_time)
    )
    return result.scalars().all()

async def get_total_memory_usage_server_db(db: AsyncSession, window_start_time: datetime) -> int:
    result = await db.execute(
        select(func.sum(models.MemoryUsage.size_bytes).label("total_usage"))
        .filter(models.MemoryUsage.timestamp >= window_start_time)
    )
    total = result.scalar_one_or_none()
    return total or 0

async def delete_old_memory_usage_entries_db(db: AsyncSession, older_than: datetime):
    stmt = delete(models.MemoryUsage).where(models.MemoryUsage.timestamp < older_than)
    await db.execute(stmt)
    await db.commit()

async def get_processing_tasks_on_startup_db(db: AsyncSession) -> List[models.Task]:
    result = await db.execute(
        select(models.Task).filter(models.Task.status == models.TaskStatusEnum.PROCESSING)
    )
    return result.scalars().all()

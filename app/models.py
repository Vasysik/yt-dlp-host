from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Boolean, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func # for server_default=func.now()
from app.database import Base
import enum

class TaskStatusEnum(str, enum.Enum):
    WAITING = "waiting"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, index=True)
    task_type = Column(String, index=True, nullable=False)
    status = Column(String, default=TaskStatusEnum.WAITING, index=True, nullable=False)
    params = Column(JSON, nullable=False)
    result = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    api_key_name = Column(String, ForeignKey("api_keys.name", ondelete="CASCADE"), nullable=False, index=True)
    api_key_owner = relationship("ApiKey", back_populates="tasks")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    key = Column(String, unique=True, index=True, nullable=False)
    permissions = Column(JSON, nullable=False) # List[str]
    is_active = Column(Boolean, default=True)
    
    memory_quota_bytes = Column(BigInteger, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    tasks = relationship("Task", back_populates="api_key_owner", cascade="all, delete-orphan")


class MemoryUsage(Base):
    __tablename__ = "memory_usage"

    id = Column(Integer, primary_key=True, index=True)
    api_key_name = Column(String, ForeignKey("api_keys.name", ondelete="CASCADE"), nullable=False, index=True)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True)
    size_bytes = Column(BigInteger, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # api_key = relationship("ApiKey")
    # task = relationship("Task")

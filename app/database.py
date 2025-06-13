from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
from typing import AsyncGenerator

engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URL, echo=False) 

AsyncSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine, 
    class_=AsyncSession
)

Base = declarative_base()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    from app import crud
    from app.auth import generate_api_key_value
    
    async with AsyncSessionLocal() as session:
        admin_key_name = settings.INITIAL_ADMIN_KEY_NAME
        db_admin_key = await crud.get_api_key_by_name(session, name=admin_key_name)
        if not db_admin_key:
            admin_api_key_value = settings.INITIAL_ADMIN_KEY_VALUE or generate_api_key_value()
            await crud.create_api_key_db(
                db=session,
                name=admin_key_name,
                key_value=admin_api_key_value,
                permissions=settings.ALL_PERMISSIONS,
                memory_quota_bytes=settings.DEFAULT_MEMORY_QUOTA_BYTES
            )
            print(f"Initial admin key '{admin_key_name}' created with value: {admin_api_key_value}")
            print("PLEASE STORE THIS KEY SECURELY. It will not be shown again.")
        elif settings.INITIAL_ADMIN_KEY_VALUE and db_admin_key.key != settings.INITIAL_ADMIN_KEY_VALUE:
            print(f"Warning: Admin key '{admin_key_name}' exists in DB, but INITIAL_ADMIN_KEY_VALUE in config/env is different.")
        else:
            print(f"Admin key '{admin_key_name}' already exists.")

"""Async database engine and session factory.

This module provides `async_session` for use in async code.
Synchronous parts of the project can continue to import and use
`engine` from `models.py` unchanged.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.config import settings

# Expect DATABASE_URL_ASYNC in settings; fallback by converting sync URL.
if hasattr(settings, "DATABASE_URL_ASYNC") and settings.DATABASE_URL_ASYNC:
    async_db_url = settings.DATABASE_URL_ASYNC
else:
    # naive conversion: replace "postgresql://" with "postgresql+asyncpg://"
    async_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine_async = create_async_engine(async_db_url, echo=False, pool_size=10, max_overflow=20)

async_session = sessionmaker(engine_async, expire_on_commit=False, class_=AsyncSession)

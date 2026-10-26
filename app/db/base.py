from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Создаёт таблицы напрямую (для dev). В проде — alembic upgrade head."""
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # мини-миграции для баз, созданных старыми версиями (безопасно повторять)
        from sqlalchemy import text

        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS lang_chosen BOOLEAN NOT NULL DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE orders ALTER COLUMN fragment_req_id TYPE VARCHAR(128)"))
        await conn.execute(text("ALTER TABLE orders ALTER COLUMN tx_hash TYPE VARCHAR(256)"))

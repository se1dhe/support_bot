from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator

from config import load_config

# Загрузка конфигурации
config = load_config()

# База для всех моделей
Base = declarative_base()

# Создаём движок для работы с базой данных
engine = create_async_engine(
    config.db.get_uri(),
    echo=False,
    future=True,
    pool_pre_ping=True,
)

# Создаём фабрику сессий
async_session_factory = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Асинхронный генератор сессий для работы с БД.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables():
    """
    Создание всех таблиц в базе данных.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    """
    Удаление всех таблиц из базы данных.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
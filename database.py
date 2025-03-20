from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import AsyncGenerator, Optional
import logging

from config import Config, load_config

# База для всех моделей
Base = declarative_base()

# Инициализация логгера
logger = logging.getLogger(__name__)

# Глобальные переменные для работы с БД
engine = None
async_session_factory = None


async def init_db(config: Optional[Config] = None) -> None:
    """
    Инициализирует соединение с базой данных.

    Args:
        config: Объект конфигурации
    """
    global engine, async_session_factory

    if config is None:
        config = load_config()

    logger.info(f"Инициализация соединения с базой данных: {config.db.host}:{config.db.port}/{config.db.database}")

    # Создаём движок для работы с базой данных
    engine = create_async_engine(
        config.db.get_uri(),
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

    # Создаём фабрику сессий
    async_session_factory = sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )

    logger.info("Соединение с базой данных успешно инициализировано")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Асинхронный генератор сессий для работы с БД.

    Yields:
        AsyncSession: Сессия для работы с БД
    """
    if async_session_factory is None:
        await init_db()

    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_tables() -> None:
    """
    Создание всех таблиц в базе данных.
    """
    if engine is None:
        await init_db()

    async with engine.begin() as conn:
        logger.info("Создание таблиц в базе данных...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Таблицы успешно созданы")


async def drop_tables() -> None:
    """
    Удаление всех таблиц из базы данных.
    """
    if engine is None:
        await init_db()

    async with engine.begin() as conn:
        logger.info("Удаление таблиц из базы данных...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Таблицы успешно удалены")


class DatabaseMiddleware:
    """
    Middleware для работы с базой данных.
    Автоматически создает и закрывает сессию для каждого запроса.
    """

    async def __call__(self, handler, event, data):
        async with async_session_factory() as session:
            data["session"] = session
            return await handler(event, data)
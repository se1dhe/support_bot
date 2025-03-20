from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
import logging

# Импортируем модуль database полностью
import database
from database import init_db

logger = logging.getLogger(__name__)


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware для работы с базой данных.
    Создает сессию для каждого запроса и закрывает ее после обработки.
    """

    # middlewares/database.py
    # middlewares/database.py
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        logger.info("DatabaseMiddleware вызван")

        # Проверяем, инициализирована ли фабрика сессий
        if database.async_session_factory is None:
            logger.warning("async_session_factory is None! Инициализируем...")
            await init_db()

            if database.async_session_factory is None:
                logger.error("Не удалось инициализировать async_session_factory!")
                return await handler(event, data)

        try:
            # Создаем сессию и добавляем ее в data
            async with database.async_session_factory() as session:
                # Добавляем сессию в data для доступа в обработчиках
                data["session"] = session
                logger.info("Сессия создана и добавлена в data")

                # Выполняем обработчик
                return await handler(event, data)
        except Exception as e:
            logger.error(f"Ошибка в DatabaseMiddleware: {e}", exc_info=True)
            # В случае ошибки всё равно вызываем обработчик, но без сессии
            # Может потребоваться создание временной сессии
            return await handler(event, data)
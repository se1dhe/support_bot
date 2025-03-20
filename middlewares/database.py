from typing import Dict, Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_factory


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware для работы с базой данных.
    Создает сессию для каждого запроса и закрывает ее после обработки.
    """

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        # Создаем сессию
        if async_session_factory is None:
            # Если фабрика сессий не инициализирована, просто передаем управление дальше
            return await handler(event, data)

        # Создаем сессию и добавляем ее в data
        async with async_session_factory() as session:
            data["session"] = session

            # Выполняем обработчик
            return await handler(event, data)
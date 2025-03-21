from typing import Dict, Any, Callable, Awaitable, Optional, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User
from utils.i18n import get_i18n


class I18nMiddleware(BaseMiddleware):
    """
    Middleware для работы с локализацией.
    Устанавливает текущий язык пользователя на основе данных из БД.
    """

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: Union[Message, CallbackQuery],
            data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id пользователя
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            # Если не Message и не CallbackQuery, просто передаем управление дальше
            return await handler(event, data)

        # Получаем сессию БД
        session = data.get("session")
        if not session:
            # Если сессии нет, передаем управление дальше
            return await handler(event, data)

        # Получаем пользователя из БД
        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        # Если пользователь найден, устанавливаем его язык
        if user:
            # Сохраняем язык пользователя в data
            data["user_language"] = user.language

            # Устанавливаем текущий язык в i18n менеджере
            i18n = get_i18n()
            i18n.current_language = user.language

        # Передаем управление дальше
        return await handler(event, data)
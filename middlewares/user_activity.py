from typing import Dict, Any, Callable, Awaitable, Optional, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime

from models import User


class UserActivityMiddleware(BaseMiddleware):
    """
    Middleware для отслеживания активности пользователей.
    Обновляет время последней активности пользователя при каждом взаимодействии с ботом.
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

        # Обновляем время последней активности пользователя
        try:
            current_time = datetime.now()
            await session.execute(
                update(User)
                .where(User.telegram_id == user_id)
                .values(last_activity=current_time)
            )
            await session.commit()
        except Exception as e:
            # В случае ошибки просто логируем и продолжаем
            print(f"Ошибка при обновлении времени активности пользователя: {e}")

        # Передаем управление дальше
        return await handler(event, data)
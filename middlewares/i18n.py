from typing import Any, Awaitable, Callable, Dict, Optional, Union

from aiogram import BaseMiddleware, Bot, F
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import get_session
from models import User


class I18nMiddleware(BaseMiddleware):
    def __init__(self, i18n):
        self.i18n = i18n
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: Union[Message, CallbackQuery],
            data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id пользователя из Message или CallbackQuery
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)

        # Получаем сессию БД
        session = data.get("session")
        if not session:
            return await handler(event, data)

        # Используем новый синтаксис SQLAlchemy 2.x
        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        db_user = result.scalar_one_or_none()  # Используем scalar_one_or_none вместо first()

        # Если пользователь найден в БД, используем его язык
        if db_user:
            self.i18n.current_language = db_user.language

        # Вызываем следующий обработчик
        return await handler(event, data)
import asyncio
from typing import Any, Awaitable, Callable, Dict, Union

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        # TTLCache(максимальное количество элементов, время жизни элемента в секундах)
        self.cache = TTLCache(maxsize=10000, ttl=rate_limit)
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        # Получаем telegram_id пользователя
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)

        # Проверяем, есть ли пользователь в кэше
        if user_id in self.cache:
            # Пользователь отправляет сообщения слишком часто
            return None

        # Добавляем пользователя в кэш
        self.cache[user_id] = True

        # Вызываем следующий обработчик
        return await handler(event, data)
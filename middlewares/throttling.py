import time
from typing import Dict, Any, Callable, Awaitable, Union
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from cachetools import TTLCache


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware для защиты от спама.
    Ограничивает частоту запросов от пользователей.
    """

    def __init__(self, rate_limit: float = 0.5):
        """
        Инициализирует middleware с указанием ограничения.

        Args:
            rate_limit: Минимальный интервал между запросами в секундах
        """
        self.rate_limit = rate_limit
        # TTLCache: максимальное количество элементов, время жизни элемента в секундах
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
            # Если не Message и не CallbackQuery, просто передаем управление дальше
            return await handler(event, data)

        # Получаем текущее время
        current_time = time.time()

        # Проверяем, было ли недавно сообщение от этого пользователя
        if user_id in self.cache:
            # Определяем, сколько времени прошло с последнего запроса
            last_time = self.cache[user_id]
            elapsed = current_time - last_time

            # Если прошло меньше времени, чем ограничение, игнорируем запрос
            if elapsed < self.rate_limit:
                # Для CallbackQuery отправляем уведомление
                if isinstance(event, CallbackQuery):
                    await event.answer(
                        f"Пожалуйста, не так быстро! Подождите {self.rate_limit - elapsed:.1f} сек.",
                        show_alert=True
                    )
                return None

        # Обновляем время последнего запроса
        self.cache[user_id] = current_time

        # Передаем управление дальше
        return await handler(event, data)
from aiogram import Bot, Dispatcher
from typing import Optional

from config import Config
from middlewares.database import DatabaseMiddleware
from middlewares.i18n import I18nMiddleware
from middlewares.user_activity import UserActivityMiddleware
from middlewares.throttling import ThrottlingMiddleware


async def setup_middlewares(dp: Dispatcher, bot: Bot, config: Optional[Config] = None):
    """
    Настройка всех middleware для диспетчера.

    Args:
        dp: Диспетчер
        bot: Бот
        config: Конфигурация (опционально)
    """
    # Регистрируем middleware для базы данных (должен быть первым)
    dp.update.middleware.register(DatabaseMiddleware())

    # Регистрируем middleware для интернационализации
    dp.update.middleware.register(I18nMiddleware())

    # Регистрируем middleware для отслеживания активности пользователей
    dp.update.middleware.register(UserActivityMiddleware())

    # Регистрируем middleware для защиты от спама
    dp.update.middleware.register(ThrottlingMiddleware(rate_limit=0.5))
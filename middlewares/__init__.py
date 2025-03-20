from aiogram import Bot, Dispatcher
from typing import Optional

from config import Config
from middlewares.database import DatabaseMiddleware
from middlewares.i18n import I18nMiddleware
from middlewares.user_activity import UserActivityMiddleware
from middlewares.throttling import ThrottlingMiddleware


# middlewares/__init__.py
async def setup_middlewares(dp: Dispatcher, bot: Bot, config: Optional[Config] = None):
    # Регистрируем middleware для базы данных
    dp.update.middleware.register(DatabaseMiddleware())

    # Регистрируем остальные middleware для конкретных типов событий
    dp.message.middleware.register(I18nMiddleware())
    dp.callback_query.middleware.register(I18nMiddleware())

    dp.message.middleware.register(UserActivityMiddleware())
    dp.callback_query.middleware.register(UserActivityMiddleware())

    dp.message.middleware.register(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware.register(ThrottlingMiddleware(rate_limit=0.5))
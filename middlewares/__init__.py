from aiogram import Bot, Dispatcher
from typing import Optional

from config import Config
from middlewares.database import DatabaseMiddleware
from middlewares.i18n import I18nMiddleware
from middlewares.user_activity import UserActivityMiddleware
from middlewares.throttling import ThrottlingMiddleware


async def setup_middlewares(dp: Dispatcher, bot: Bot, config: Optional[Config] = None):
    # Убедитесь, что DatabaseMiddleware регистрируется первым
    dp.update.middleware.register(DatabaseMiddleware())

    # Потом остальные middleware
    dp.update.middleware.register(I18nMiddleware())
    dp.update.middleware.register(UserActivityMiddleware())
    dp.update.middleware.register(ThrottlingMiddleware(rate_limit=0.5))
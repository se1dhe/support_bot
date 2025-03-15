from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.utils.i18n import I18n
from aiogram.types import TelegramObject
from typing import Any, Awaitable, Callable, Dict

from config import Config
from database import get_session
from middlewares.i18n import I18nMiddleware
from middlewares.role import RoleMiddleware
from middlewares.throttling import ThrottlingMiddleware
from models import UserRole


class DBSessionMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: Dict[str, Any]
    ) -> Any:
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession() as session:
            data["session"] = session
            result = await handler(event, data)

        return result


async def setup_middlewares(dp: Dispatcher, bot: Bot, config: Config):
    """
    Настройка всех middlewares для диспетчера.
    """
    # Настройка I18n
    i18n = I18n(
        path=config.localization.locales_dir,
        default_locale=config.localization.default_language,
        domain=config.localization.domain
    )

    # Регистрируем middleware для интернационализации
    dp.message.middleware(I18nMiddleware(i18n))
    dp.callback_query.middleware(I18nMiddleware(i18n))

    # Регистрируем middleware для защиты от спама
    dp.message.middleware(ThrottlingMiddleware(rate_limit=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate_limit=0.5))

    # Middleware для сессий БД
    dp.message.middleware.register(DBSessionMiddleware())
    dp.callback_query.middleware.register(DBSessionMiddleware())
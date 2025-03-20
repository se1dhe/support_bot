from typing import Dict, Any, Callable, Awaitable, Optional, Union, List
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User, UserRole


class RoleMiddleware(BaseMiddleware):
    """
    Middleware для проверки роли пользователя.
    Проверяет, имеет ли пользователь необходимую роль для доступа к определенным функциям.
    """

    def __init__(self, allowed_roles: List[UserRole]):
        """
        Инициализирует middleware с указанием разрешенных ролей.

        Args:
            allowed_roles: Список разрешенных ролей
        """
        self.allowed_roles = allowed_roles
        super().__init__()

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

        # Если пользователь не найден, считаем его обычным пользователем
        if not user:
            if UserRole.USER in self.allowed_roles:
                # Добавляем информацию о пользователе в data
                data["user_role"] = UserRole.USER
                return await handler(event, data)
            else:
                # У пользователя нет доступа
                if isinstance(event, CallbackQuery):
                    await event.answer("У вас нет доступа к этой функции", show_alert=True)
                return None

        # Проверяем роль пользователя
        if user.role in self.allowed_roles:
            # Добавляем информацию о пользователе в data
            data["user_role"] = user.role
            data["user"] = user
            return await handler(event, data)
        else:
            # У пользователя нет доступа
            if isinstance(event, CallbackQuery):
                await event.answer("У вас нет доступа к этой функции", show_alert=True)
            return None
# role.py
# -------
from typing import Any, Awaitable, Callable, Dict, List, Union

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import User, UserRole


class RoleMiddleware(BaseMiddleware):
    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = allowed_roles
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
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

        # Получаем сессию БД из данных
        session = data.get("session")
        if not session:
            # Если в data нет сессии, создаем новую
            session = AsyncSession()
            data["session"] = session

        # Получаем пользователя из БД
        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        db_user = result.scalar_one_or_none()

        # Если пользователь не найден, считаем его обычным пользователем
        if not db_user:
            if UserRole.USER in self.allowed_roles:
                return await handler(event, data)
            else:
                # Пользователь не имеет доступа
                return None

        # Добавляем пользователя в data для использования в хендлерах
        data["user"] = db_user

        # Проверяем роль пользователя
        if db_user.role in self.allowed_roles:
            return await handler(event, data)
        else:
            # Пользователь не имеет доступа
            # В реальном приложении здесь можно отправить сообщение о недостатке прав
            return None

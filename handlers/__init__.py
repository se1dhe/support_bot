from aiogram import Dispatcher
from handlers import common, user, moderator, admin


def register_all_handlers(dp: Dispatcher):
    """
    Регистрация всех обработчиков

    :param dp: Диспетчер
    """
    # Регистрируем обработчики в порядке приоритета

    # Общие обработчики (доступны всем пользователям)
    dp.include_router(common.router)

    # Обработчики для администраторов
    dp.include_router(admin.router)

    # Обработчики для модераторов
    dp.include_router(moderator.router)

    # Обработчики для обычных пользователей
    dp.include_router(user.router)
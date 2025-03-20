from aiogram import Dispatcher

from handlers import common, user, moderator, admin


def register_all_handlers(dp: Dispatcher):
    """
    Регистрация всех обработчиков.

    Args:
        dp: Диспетчер
    """
    # Регистрируем обработчики в порядке приоритета

    # Общие обработчики (доступны всем пользователям)
    common.register_handlers(dp)

    # Обработчики для пользователей
    user.register_handlers(dp)

    # Обработчики для модераторов
    moderator.register_handlers(dp)

    # Обработчики для администраторов
    admin.register_handlers(dp)
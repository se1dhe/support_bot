from aiogram import Dispatcher

def register_handlers(dp: Dispatcher):
    """
    Регистрирует общие обработчики команд (/start, /help, /menu).
    """
    from handlers.common import register_handlers as common_handlers
    common_handlers(dp)
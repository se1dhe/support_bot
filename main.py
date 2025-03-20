import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from database import init_db, create_tables
from middlewares import setup_middlewares
from utils.i18n import setup_i18n

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def register_handlers(dp: Dispatcher):
    """
    Регистрирует все обработчики бота.
    """
    # Импортируем функции регистрации из всех модулей
    from handlers import register_handlers as common_register_handlers
    from handlers.user import register_handlers as user_register_handlers
    from handlers.moderator import register_handlers as moderator_register_handlers
    from handlers.admin import register_handlers as admin_register_handlers

    # Регистрируем обработчики
    common_register_handlers(dp)
    user_register_handlers(dp)
    moderator_register_handlers(dp)
    admin_register_handlers(dp)

async def main():
    """
    Основная функция запуска бота.
    """
    logger.info("Запуск бота...")

    # Загрузка конфигурации
    config = load_config()

    await init_db(config)  # Сначала инициализируем БД
    await create_tables()
    # Инициализация i18n
    setup_i18n(
        locales_dir=str(Path(__file__).parent / 'locales'),
        default_language=config.localization.default_language
    )

    # Создание экземпляра бота с использованием DefaultBotProperties
    bot = Bot(
        token=config.tg_bot.token,
        default=DefaultBotProperties(parse_mode="HTML")
    )

    # Создание диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Настройка middleware
    await setup_middlewares(dp, bot, config)

    # Регистрация всех обработчиков
    register_handlers(dp)

    try:
        logger.info("Бот запущен")

        # Удаляем вебхук на всякий случай
        await bot.delete_webhook(drop_pending_updates=True)

        # Запуск поллинга
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Бот остановлен")
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")


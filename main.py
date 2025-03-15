# main.py
# -------

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot import setup_bot, setup_dispatcher
from config import load_config
from database import create_tables, config
from handlers import register_all_handlers
from middlewares import setup_middlewares

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# В начале функции main после загрузки config добавьте:
from i18n_setup import setup_i18n
setup_i18n(config.localization.locales_dir,
           config.localization.default_language,
           config.localization.domain)

logger = logging.getLogger(__name__)


async def main():
    # Загрузка конфигурации
    config = load_config()

    # Настройка бота и диспетчера
    bot = await setup_bot(config)
    dp = setup_dispatcher()

    # Регистрация всех хендлеров
    register_all_handlers(dp)

    # Настройка мидлварей
    await setup_middlewares(dp, bot, config)

    # Создание таблиц в БД
    await create_tables()

    # Запуск polling
    logger.info("Starting bot")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
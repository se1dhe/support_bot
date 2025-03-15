# bot.py
# ------

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

from config import Config


async def setup_bot(config: Config) -> Bot:
    """
    Настройка и инициализация бота.
    """
    bot = Bot(
        token=config.tg_bot.token,
        default=DefaultBotProperties(parse_mode="HTML")
    )
    return bot


def setup_dispatcher() -> Dispatcher:
    """
    Настройка и инициализация диспетчера.
    """
    # Используем MemoryStorage для хранения состояний FSM
    # В production-среде лучше использовать RedisStorage
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    return dp
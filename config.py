from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from environs import Env


@dataclass
class DbConfig:
    """Конфигурация базы данных"""
    host: str
    port: int
    user: str
    password: str
    database: str

    def get_uri(self):
        """
        Возвращает URI для подключения к базе данных.

        Returns:
            str: URI подключения
        """
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class TgBot:
    """Конфигурация Telegram бота"""
    token: str
    admin_ids: List[int]


@dataclass
class Localization:
    """Конфигурация локализации"""
    default_language: str
    languages: List[str]
    locales_dir: Path


@dataclass
class Config:
    """Основная конфигурация приложения"""
    tg_bot: TgBot
    db: DbConfig
    localization: Localization


def load_config(path: Optional[str] = None) -> Config:
    """
    Загружает конфигурацию из .env файла.

    Args:
        path: Путь к .env файлу (опционально)

    Returns:
        Config: Объект с конфигурацией
    """
    env = Env()
    env.read_env(path)

    return Config(
        tg_bot=TgBot(
            token=env.str('BOT_TOKEN'),
            admin_ids=list(map(int, env.list('ADMIN_IDS'))),
        ),
        db=DbConfig(
            host=env.str('DB_HOST'),
            port=env.int('DB_PORT'),
            user=env.str('DB_USER'),
            password=env.str('DB_PASS'),
            database=env.str('DB_NAME'),
        ),
        localization=Localization(
            default_language=env.str('DEFAULT_LANGUAGE', 'ru'),
            languages=env.list('LANGUAGES', ['ru', 'en', 'uk']),
            locales_dir=Path(__file__).parent / 'locales',
        ),
    )
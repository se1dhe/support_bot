# config.py
# ---------

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from environs import Env


@dataclass
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str

    def get_uri(self):
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class TgBot:
    token: str
    admin_ids: List[int]


@dataclass
class Localization:
    default_language: str
    languages: List[str]
    domain: str
    locales_dir: Path


@dataclass
class Config:
    tg_bot: TgBot
    db: DbConfig
    localization: Localization


def load_config(path: str = None) -> Config:
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
            domain='support_bot',
            locales_dir=Path(__file__).parent / 'locales',
        ),
    )
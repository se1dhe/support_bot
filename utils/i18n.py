from typing import Optional, Dict, Any
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class I18nManager:
    """
    Менеджер локализации (i18n) для поддержки мультиязычности в боте.
    Использует простой подход с JSON-файлами для хранения переводов.
    """

    def __init__(self, locales_dir: str, default_language: str = "ru"):
        """
        Инициализирует менеджер локализации.

        Args:
            locales_dir: Путь к директории с файлами локализации
            default_language: Язык по умолчанию
        """
        self.locales_dir = Path(locales_dir)
        self.default_language = default_language
        self.translations: Dict[str, Dict[str, str]] = {}

        # Загружаем все доступные переводы
        self._load_translations()

    def _load_translations(self) -> None:
        """Загружает все файлы переводов из директории locales."""
        if not self.locales_dir.exists():
            logger.warning(f"Директория локализаций не найдена: {self.locales_dir}")
            return

        for locale_file in self.locales_dir.glob("*.json"):
            try:
                language = locale_file.stem  # Имя файла без расширения
                with open(locale_file, 'r', encoding='utf-8') as f:
                    self.translations[language] = json.load(f)
                logger.info(f"Загружен файл локализации: {language}")
            except Exception as e:
                logger.error(f"Ошибка при загрузке файла локализации {locale_file}: {e}")

    def get_text(self, key: str, language: str = None, **kwargs) -> str:
        """
        Получает перевод по ключу для указанного языка.

        Args:
            key: Ключ перевода
            language: Код языка (если None, используется язык по умолчанию)
            **kwargs: Параметры для форматирования строки

        Returns:
            str: Переведенный текст
        """
        # Если язык не указан, используем язык по умолчанию
        lang = language or self.default_language

        # Если указанного языка нет, используем язык по умолчанию
        if lang not in self.translations:
            logger.warning(f"Язык {lang} не найден, используем {self.default_language}")
            lang = self.default_language

        # Получаем перевод по ключу
        translation = self.translations.get(lang, {}).get(key)

        # Если перевод не найден, пробуем получить из языка по умолчанию
        if translation is None and lang != self.default_language:
            translation = self.translations.get(self.default_language, {}).get(key)

        # Если перевод все равно не найден, возвращаем ключ
        if translation is None:
            logger.warning(f"Перевод для ключа '{key}' не найден")
            return key

        # Форматируем строку, если переданы параметры
        if kwargs:
            try:
                return translation.format(**kwargs)
            except KeyError as e:
                logger.error(f"Ошибка форматирования перевода '{key}': {e}")
                return translation

        return translation

    def get_all_languages(self) -> list:
        """Возвращает список всех доступных языков."""
        return list(self.translations.keys())


# Глобальный экземпляр менеджера локализации
_i18n_manager = None


def setup_i18n(locales_dir: str, default_language: str = "ru") -> I18nManager:
    """
    Инициализирует глобальный менеджер локализации.

    Args:
        locales_dir: Путь к директории с файлами локализации
        default_language: Язык по умолчанию

    Returns:
        I18nManager: Экземпляр менеджера локализации
    """
    global _i18n_manager
    _i18n_manager = I18nManager(locales_dir, default_language)
    return _i18n_manager


def get_i18n() -> I18nManager:
    """
    Возвращает глобальный менеджер локализации.

    Returns:
        I18nManager: Экземпляр менеджера локализации
    """
    if _i18n_manager is None:
        raise RuntimeError("I18n не инициализирован. Вызовите setup_i18n() перед использованием.")
    return _i18n_manager


def _(key: str, language: str = None, **kwargs) -> str:
    """
    Функция-помощник для получения перевода.

    Args:
        key: Ключ перевода
        language: Код языка (если None, используется язык по умолчанию)
        **kwargs: Параметры для форматирования строки

    Returns:
        str: Переведенный текст
    """
    return get_i18n().get_text(key, language, **kwargs)
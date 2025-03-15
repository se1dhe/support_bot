from aiogram.utils.i18n import I18n

# Глобальный объект I18n
_i18n = None

def setup_i18n(locales_dir, default_language, domain):
    """Инициализация глобального объекта I18n"""
    global _i18n
    _i18n = I18n(path=locales_dir, default_locale=default_language, domain=domain)
    return _i18n

def get_i18n():
    """Получение глобального объекта I18n"""
    if _i18n is None:
        raise RuntimeError("I18n is not initialized")
    return _i18n

def gettext(text):
    """Функция перевода текста"""
    return get_i18n().gettext(text)
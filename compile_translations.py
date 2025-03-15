import os
import subprocess
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def compile_translations():
    """Компилирует файлы переводов .po в .mo"""
    locales_dir = os.path.join(os.path.dirname(__file__), 'locales')

    if not os.path.exists(locales_dir):
        logger.error(f"Директория локализаций не найдена: {locales_dir}")
        return

    # Проходим по всем языкам
    for lang in os.listdir(locales_dir):
        lang_dir = os.path.join(locales_dir, lang, 'LC_MESSAGES')

        if not os.path.exists(lang_dir):
            logger.warning(f"Директория LC_MESSAGES не найдена для языка {lang}")
            continue

        # Находим все .po файлы
        for filename in os.listdir(lang_dir):
            if filename.endswith('.po'):
                po_file = os.path.join(lang_dir, filename)
                mo_file = os.path.join(lang_dir, os.path.splitext(filename)[0] + '.mo')

                # Компилируем .po в .mo
                try:
                    subprocess.run(['msgfmt', po_file, '-o', mo_file], check=True)
                    logger.info(f"Скомпилирован файл: {mo_file}")
                except subprocess.CalledProcessError as e:
                    logger.error(f"Ошибка при компиляции {po_file}: {e}")
                except FileNotFoundError:
                    logger.error("Утилита msgfmt не найдена. Установите пакет gettext.")
                    return


if __name__ == "__main__":
    logger.info("Запуск компиляции файлов переводов")
    compile_translations()
    logger.info("Компиляция завершена")
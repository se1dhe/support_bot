import subprocess
import sys
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def run():
    """
    Запускает миграции и бота
    """
    try:
        # Компилируем переводы
        logger.info("Компиляция файлов переводов...")
        subprocess.run([sys.executable, "compile_translations.py"], check=True)

        # Запускаем миграции
        logger.info("Применение миграций...")
        subprocess.run(["alembic", "upgrade", "head"], check=True)

        # Запускаем бота
        logger.info("Запуск бота...")
        from main import main
        await main()
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при выполнении команды: {e}")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")


if __name__ == "__main__":
    asyncio.run(run())
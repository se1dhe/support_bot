import os
import pathlib


def create_project_structure():
    # Название проекта
    project_name = "support_bot"

    # Основные директории проекта
    directories = [
        "",  # Корневая директория
        "handlers",
        "middlewares",
        "callbacks",
        "models",
        "utils",
        "locales",
        "locales/en",
        "locales/ru",
        "locales/uk",
    ]

    # Файлы проекта
    files = [
        ".env.example",
        "main.py",
        "config.py",
        "database.py",
        "bot.py",
        "handlers/__init__.py",
        "handlers/user.py",
        "handlers/moderator.py",
        "handlers/admin.py",
        "handlers/common.py",
        "middlewares/__init__.py",
        "middlewares/i18n.py",
        "middlewares/role.py",
        "middlewares/throttling.py",
        "callbacks/__init__.py",
        "callbacks/user.py",
        "callbacks/moderator.py",
        "callbacks/admin.py",
        "models/__init__.py",
        "models/user.py",
        "models/ticket.py",
        "models/message.py",
        "utils/__init__.py",
        "utils/states.py",
        "utils/paginator.py",
        "utils/keyboards.py",
        "utils/emoji.py",
        "locales/en/LC_MESSAGES/support_bot.po",
        "locales/ru/LC_MESSAGES/support_bot.po",
        "locales/uk/LC_MESSAGES/support_bot.po",
        "requirements.txt",
        "alembic.ini",
        "migrations/env.py",
        "migrations/README",
        "migrations/script.py.mako",
    ]

    # Создаем базовую директорию проекта, если она еще не существует
    if not os.path.exists(project_name):
        os.makedirs(project_name)

    # Создаем структуру директорий
    for directory in directories:
        path = os.path.join(project_name, directory)
        if not os.path.exists(path):
            os.makedirs(path)

    # Создаем пустые файлы
    for file in files:
        path = os.path.join(project_name, file)
        # Проверяем, существует ли директория для файла
        dir_path = os.path.dirname(path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # Создаем пустой файл, если он еще не существует
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                # Пишем заголовок с указанием назначения файла
                f.write(f"# {os.path.basename(path)}\n# {'-' * len(os.path.basename(path))}\n\n")

    # Создаем migrations директорию, если она не существует
    migrations_dir = os.path.join(project_name, "migrations")
    if not os.path.exists(migrations_dir):
        os.makedirs(migrations_dir)
        os.makedirs(os.path.join(migrations_dir, "versions"))

    print(f"Структура проекта '{project_name}' успешно создана!")


if __name__ == "__main__":
    create_project_structure()
# common.py
# ---------
import logging
from typing import Union

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User, UserRole
from utils import (
    build_language_keyboard,
    build_user_main_menu,
    build_moderator_main_menu,
    build_admin_main_menu,
    UserStates, ModeratorStates, AdminStates
)

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.message(CommandStart())
async def command_start(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик команды /start
    """
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    # Проверяем, существует ли пользователь в БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Пользователь новый, добавляем его в БД
        user = User(
            telegram_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.USER
        )
        session.add(user)
        await session.commit()

        # Предлагаем выбрать язык
        await message.answer(
            "👋 Добро пожаловать в систему поддержки!\n\n"
            "Пожалуйста, выберите язык интерфейса:\n\n"
            "Welcome to the support system!\n"
            "Please select your language:\n\n"
            "Ласкаво просимо до системи підтримки!\n"
            "Будь ласка, виберіть мову інтерфейсу:",
            reply_markup=build_language_keyboard()
        )

        # Устанавливаем состояние выбора языка
        await state.set_state(UserStates.SELECTING_LANGUAGE)
    else:
        # Пользователь уже существует, определяем его роль и показываем соответствующее меню
        if user.role == UserRole.ADMIN:
            await message.answer(
                f"👑 Добро пожаловать, администратор {user.full_name}!\n"
                f"Выберите действие из меню:",
                reply_markup=build_admin_main_menu()
            )
            await state.set_state(AdminStates.MAIN_MENU)
        elif user.role == UserRole.MODERATOR:
            await message.answer(
                f"🔑 Добро пожаловать, модератор {user.full_name}!\n"
                f"Выберите действие из меню:",
                reply_markup=build_moderator_main_menu()
            )
            await state.set_state(ModeratorStates.MAIN_MENU)
        else:
            await message.answer(
                f"👤 Добро пожаловать, {user.full_name}!\n"
                f"Выберите действие из меню:",
                reply_markup=build_user_main_menu()
            )
            await state.set_state(UserStates.MAIN_MENU)

    logger.info(f"User {user_id} ({username or first_name}) started the bot")


@router.message(Command("help"))
async def command_help(message: Message):
    """
    Обработчик команды /help
    """
    help_text = (
        "🤝 <b>Помощь по использованию бота поддержки</b>\n\n"
        "<b>Основные команды:</b>\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/menu - Показать главное меню\n\n"

        "<b>Для пользователей:</b>\n"
        "- Создайте тикет, описав вашу проблему\n"
        "- Дождитесь, пока модератор примет ваш тикет\n"
        "- Общайтесь с модератором через бота\n"
        "- После решения проблемы оцените работу модератора\n\n"

        "<b>Для модераторов:</b>\n"
        "- Принимайте тикеты в работу\n"
        "- Общайтесь с пользователем через бота\n"
        "- Отметьте тикет как решенный, когда проблема будет устранена\n\n"

        "<b>Для администраторов:</b>\n"
        "- Назначайте новых модераторов\n"
        "- Просматривайте статистику работы бота\n"
    )

    await message.answer(help_text)
    logger.info(f"User {message.from_user.id} requested help")


@router.message(Command("menu"))
async def command_menu(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик команды /menu
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Если пользователя нет в БД, запускаем команду /start
        return await command_start(message, session, state)

    # Показываем соответствующее меню в зависимости от роли
    if user.role == UserRole.ADMIN:
        await message.answer(
            "👑 Меню администратора.\nВыберите действие:",
            reply_markup=build_admin_main_menu()
        )
        await state.set_state(AdminStates.MAIN_MENU)
    elif user.role == UserRole.MODERATOR:
        await message.answer(
            "🔑 Меню модератора.\nВыберите действие:",
            reply_markup=build_moderator_main_menu()
        )
        await state.set_state(ModeratorStates.MAIN_MENU)
    else:
        await message.answer(
            "👤 Главное меню.\nВыберите действие:",
            reply_markup=build_user_main_menu()
        )
        await state.set_state(UserStates.MAIN_MENU)

    logger.info(f"User {user_id} opened the menu")


@router.callback_query(F.data.startswith("language:"))
async def process_language_selection(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик выбора языка
    """
    user_id = callback_query.from_user.id
    selected_language = callback_query.data.split(":")[1]

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if user:
        # Обновляем язык пользователя
        user.language = selected_language
        await session.commit()

        # Формируем приветственное сообщение в зависимости от выбранного языка
        if selected_language == "ru":
            welcome_text = "🇷🇺 Язык изменен на русский. Добро пожаловать в систему поддержки!"
        elif selected_language == "en":
            welcome_text = "🇬🇧 Language changed to English. Welcome to the support system!"
        elif selected_language == "uk":
            welcome_text = "🇺🇦 Мову змінено на українську. Ласкаво просимо до системи підтримки!"
        else:
            welcome_text = "Язык успешно выбран. Добро пожаловать в систему поддержки!"

        # Показываем пользовательское меню
        await callback_query.message.edit_text(
            f"{welcome_text}\n\nВыберите действие из меню:",
            reply_markup=build_user_main_menu()
        )

        # Устанавливаем состояние главного меню
        await state.set_state(UserStates.MAIN_MENU)

        logger.info(f"User {user_id} selected {selected_language} language")
    else:
        # На всякий случай, если пользователя нет в БД
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте снова: /start",
        )
        logger.error(f"User {user_id} not found in database during language selection")

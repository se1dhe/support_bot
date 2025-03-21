import logging
from typing import Union, Dict, Any

from aiogram import Router, F, Dispatcher, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User, UserRole
from utils.i18n import _
from utils.keyboards import KeyboardFactory
from utils.states import UserStates, ModeratorStates, AdminStates

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.message(CommandStart())
async def command_start_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика команды /start
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик command_start!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_start_command(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_start_command(message, session, state)


async def _process_start_command(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика команды /start
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
            reply_markup=KeyboardFactory.language_selection()
        )

        # Устанавливаем состояние выбора языка
        await state.set_state(UserStates.SELECTING_LANGUAGE)
    else:
        # Пользователь уже существует, показываем соответствующее меню
        # Создаем Reply Keyboard в зависимости от роли
        reply_markup = KeyboardFactory.main_reply_keyboard(user.role, user.language)

        if user.role == UserRole.ADMIN:
            await message.answer(
                _("welcome_admin", user.language, name=user.full_name),
                reply_markup=reply_markup
            )
            # Также показываем Inline Keyboard
            await message.answer(
                _("main_menu", user.language),
                reply_markup=KeyboardFactory.main_menu(UserRole.ADMIN, user.language)
            )
            await state.set_state(AdminStates.MAIN_MENU)
        elif user.role == UserRole.MODERATOR:
            await message.answer(
                _("welcome_moderator", user.language, name=user.full_name),
                reply_markup=reply_markup
            )
            # Также показываем Inline Keyboard
            await message.answer(
                _("main_menu", user.language),
                reply_markup=KeyboardFactory.main_menu(UserRole.MODERATOR, user.language)
            )
            await state.set_state(ModeratorStates.MAIN_MENU)
        else:
            await message.answer(
                _("welcome_user", user.language, name=user.full_name),
                reply_markup=reply_markup
            )
            # Также показываем Inline Keyboard
            await message.answer(
                _("main_menu", user.language),
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
            )
            await state.set_state(UserStates.MAIN_MENU)

    logger.info(f"User {user_id} ({username or first_name}) started the bot")


@router.message(F.text == "📋 Меню")
async def reply_menu_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Меню" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик reply_menu_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_menu_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_menu_button(message, session, state)


async def _process_menu_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Меню" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Если пользователя нет в БД, запускаем команду /start
        return await _process_start_command(message, session, state)

    # Показываем соответствующее меню в зависимости от роли
    if user.role == UserRole.ADMIN:
        await message.answer(
            _("admin_main_menu", user.language),
            reply_markup=KeyboardFactory.main_menu(UserRole.ADMIN, user.language)
        )
        await state.set_state(AdminStates.MAIN_MENU)
    elif user.role == UserRole.MODERATOR:
        await message.answer(
            _("moderator_main_menu", user.language),
            reply_markup=KeyboardFactory.main_menu(UserRole.MODERATOR, user.language)
        )
        await state.set_state(ModeratorStates.MAIN_MENU)
    else:
        await message.answer(
            _("user_main_menu", user.language),
            reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
        )
        await state.set_state(UserStates.MAIN_MENU)

    logger.info(f"User {user_id} opened the menu using reply button")


@router.message(Command("help"))
async def command_help_wrapper(message: Message, **kwargs):
    """
    Обертка для обработчика команды /help
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик command_help!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_help_command(message, temp_session)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_help_command(message, session)


async def _process_help_command(message: Message, session: AsyncSession):
    """
    Реализация обработчика команды /help
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        # Если пользователя нет в БД, используем русский язык по умолчанию
        language = "ru"
    else:
        language = user.language

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
    logger.info(f"User {user_id} requested help")


@router.message(Command("menu"))
async def command_menu_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика команды /menu
    """
    # Используем тот же обработчик, что и для кнопки "Меню"
    return await reply_menu_button_wrapper(message, state, **kwargs)


def register_handlers(dp: Dispatcher):
    """
    Регистрирует все обработчики данного модуля.

    Args:
        dp: Диспетчер
    """
    dp.include_router(router)


# Добавляем в существующий файл handlers/common.py

@router.message(F.text == "🔍 Поиск тикета")
async def search_ticket_cmd_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика команды поиска тикета
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик search_ticket_cmd!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_search_ticket(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_search_ticket(message, session, state)


async def _process_search_ticket(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика команды поиска тикета
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.ADMIN:
        await message.answer(
            _("error_access_denied", user.language if user else None)
        )
        return

    await message.answer(
        _("search_ticket_prompt", user.language),
        reply_markup=KeyboardFactory.back_button("admin:back_to_menu", user.language)
    )

    await state.set_state(AdminStates.SEARCHING_TICKET)

    logger.info(f"Admin {user_id} started ticket search")

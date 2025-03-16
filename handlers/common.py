# common.py
# ---------
import logging
from typing import Union

from aiogram import Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import bot
from models import User, UserRole, Ticket, TicketStatus
from utils import (
    build_language_keyboard,
    build_user_main_menu,
    build_moderator_main_menu,
    build_admin_main_menu,
    UserStates, ModeratorStates, AdminStates
)
from utils.keyboards import build_main_reply_keyboard

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
        # Создаем Reply Keyboard в зависимости от роли
        reply_markup = build_main_reply_keyboard(user.role)

        if user.role == UserRole.ADMIN:
            await message.answer(
                f"👑 Добро пожаловать, администратор {user.full_name}!\n"
                f"Выберите действие из меню:",
                reply_markup=reply_markup
            )
            # Также показываем Inline Keyboard
            await message.answer(
                "Основное меню:",
                reply_markup=build_admin_main_menu()
            )
            await state.set_state(AdminStates.MAIN_MENU)
        elif user.role == UserRole.MODERATOR:
            await message.answer(
                f"🔑 Добро пожаловать, модератор {user.full_name}!\n"
                f"Выберите действие из меню:",
                reply_markup=reply_markup
            )
            # Также показываем Inline Keyboard
            await message.answer(
                "Основное меню:",
                reply_markup=build_moderator_main_menu()
            )
            await state.set_state(ModeratorStates.MAIN_MENU)
        else:
            await message.answer(
                f"👤 Добро пожаловать, {user.full_name}!\n"
                f"Выберите действие из меню:",
                reply_markup=reply_markup
            )
            # Также показываем Inline Keyboard
            await message.answer(
                "Основное меню:",
                reply_markup=build_user_main_menu()
            )
            await state.set_state(UserStates.MAIN_MENU)

    logger.info(f"User {user_id} ({username or first_name}) started the bot")

@router.message(F.text == "📋 Меню")
async def reply_menu_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Меню" на Reply Keyboard
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

    logger.info(f"User {user_id} opened the menu using reply button")


@router.message(F.text == "📝 Активный тикет")
async def reply_active_ticket_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Активный тикет" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        return await message.answer("Пожалуйста, перезапустите бота: /start")

    # В зависимости от роли вызываем соответствующий обработчик
    if user.role == UserRole.MODERATOR:
        # Получаем активный тикет модератора
        active_ticket_query = select(Ticket).where(
            (Ticket.moderator_id == user.id) &
            (Ticket.status == TicketStatus.IN_PROGRESS)
        )
        active_ticket_result = await session.execute(active_ticket_query)
        active_ticket = active_ticket_result.scalar_one_or_none()

        if active_ticket:
            # Создаем событие с callback_data для вызова обработчика back_to_ticket
            fake_callback = types.CallbackQuery(
                id="0",
                from_user=message.from_user,
                chat_instance="0",
                message=message,
                data=f"mod:back_to_ticket",
                json_string=""
            )
            # Импортируем и вызываем функцию back_to_ticket
            from handlers.moderator import back_to_ticket
            await back_to_ticket(fake_callback, bot, session, state)
        else:
            await message.answer("У вас нет активных тикетов в работе.")
    else:
        # Для обычных пользователей
        # Создаем событие с callback_data для вызова обработчика active_ticket
        fake_callback = types.CallbackQuery(
            id="0",
            from_user=message.from_user,
            chat_instance="0",
            message=message,
            data="user:active_ticket",
            json_string=""
        )
        # Импортируем и вызываем функцию active_ticket
        from handlers.user import active_ticket
        await active_ticket(fake_callback, bot, session, state)


# Добавьте аналогичные обработчики для других кнопок на Reply Keyboard
@router.message(F.text == "✏️ Новый тикет")
async def reply_new_ticket_button(message: Message, session: AsyncSession, state: FSMContext):
    # Аналогично create_ticket в handlers/user.py
    pass

@router.message(F.text == "📋 История тикетов")
async def reply_ticket_history_button(message: Message, session: AsyncSession, state: FSMContext):
    # Аналогично ticket_history в handlers/user.py
    pass

@router.message(F.text == "📨 Неназначенные тикеты")
async def reply_unassigned_tickets_button(message: Message, session: AsyncSession, state: FSMContext):
    # Аналогично unassigned_tickets в handlers/moderator.py
    pass

@router.message(F.text == "📊 Моя статистика")
async def reply_my_stats_button(message: Message, session: AsyncSession, state: FSMContext):
    # Аналогично my_stats в handlers/moderator.py
    pass

@router.message(F.text == "📈 Статистика")
async def reply_stats_button(message: Message, session: AsyncSession, state: FSMContext):
    # Аналогично stats в handlers/admin.py
    pass

@router.message(F.text == "👨‍💼 Управление модераторами")
async def reply_manage_mods_button(message: Message, session: AsyncSession, state: FSMContext):
    # Аналогично manage_moderators в handlers/admin.py
    pass

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
    db_user = result.scalar_one_or_none()

    if db_user:
        # Обновляем язык пользователя
        db_user.language = selected_language
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

        # Создаем Reply Keyboard
        reply_markup = build_main_reply_keyboard(db_user.role)

        # Показываем пользовательское меню
        await callback_query.message.edit_text(
            f"{welcome_text}\n\nВыберите действие из меню:"
        )

        # Отправляем новое сообщение с клавиатурой быстрого доступа
        await callback_query.message.answer(
            "Используйте кнопки быстрого доступа или меню ниже:",
            reply_markup=reply_markup
        )

        # Отправляем Inline меню
        await callback_query.message.answer(
            "Основное меню:",
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

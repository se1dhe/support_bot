# common.py
# ---------
import logging
from typing import Union

from aiogram import Router, F, types, Bot
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from models import User, UserRole, Ticket, TicketStatus, Message as TicketMessage, MessageType
from utils import (
    build_language_keyboard,
    build_user_main_menu,
    build_moderator_main_menu,
    build_admin_main_menu,
    build_back_keyboard,
    build_rating_keyboard,
    build_tickets_list_keyboard,
    UserStates, ModeratorStates, AdminStates,
    TICKET_STATUS_EMOJI, RATING_EMOJI
)
from utils.keyboards import build_main_reply_keyboard
from utils.paginator import Paginator

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
async def reply_active_ticket_button(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
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

    # В зависимости от роли выполняем соответствующие действия
    if user.role == UserRole.MODERATOR:
        await handle_moderator_active_ticket(message, bot, session, state, user)
    else:
        await handle_user_active_ticket(message, bot, session, state, user)


async def handle_moderator_active_ticket(message: Message, bot: Bot, session: AsyncSession, state: FSMContext,
                                         user: User):
    """
    Обработка активного тикета для модератора
    """
    # Получаем активный тикет модератора
    active_ticket_query = select(Ticket).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user), selectinload(Ticket.messages))
    active_ticket_result = await session.execute(active_ticket_query)
    active_ticket = active_ticket_result.scalar_one_or_none()

    if not active_ticket:
        await message.answer("У вас нет активных тикетов в работе.")
        return

    # Формируем сообщение с информацией о тикете
    message_text = (
        f"🔄 <b>Тикет #{active_ticket.id}</b>\n\n"
        f"👤 Пользователь: {active_ticket.user.full_name}\n"
        f"📝 Тема: {active_ticket.subject or 'Не указана'}\n"
        f"📅 Создан: {active_ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    )

    # Создаем клавиатуру
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="✅ Отметить как решённый", callback_data=f"mod:resolve_ticket:{active_ticket.id}"))
    kb.add(InlineKeyboardButton(text="🔄 Переназначить", callback_data=f"mod:reassign_ticket:{active_ticket.id}"))
    kb.add(InlineKeyboardButton(text="🔙 В меню", callback_data="mod:back_to_menu"))

    await message.answer(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(ModeratorStates.WORKING_WITH_TICKET)
    await state.update_data(active_ticket_id=active_ticket.id)

    # Отправляем историю сообщений
    if active_ticket.messages:
        await message.answer("📜 <b>История сообщений:</b>")

        # Ограничиваем количество сообщений
        max_messages = 20
        start_idx = max(0, len(active_ticket.messages) - max_messages)

        # Если в тикете много сообщений, добавляем информацию об ограничении
        if len(active_ticket.messages) > max_messages:
            await message.answer(
                f"<i>Показаны последние {max_messages} из {len(active_ticket.messages)} сообщений.</i>"
            )

        for msg in active_ticket.messages[start_idx:]:
            if msg.sender_id == active_ticket.user_id:
                sender = "Пользователь"
            elif msg.sender_id == user.id:
                sender = "Вы"
            else:
                sender = "Система"

            time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

            if msg.message_type == MessageType.SYSTEM:
                await message.answer(f"🔔 <i>{msg.text}</i>")
            elif msg.message_type == MessageType.TEXT:
                await message.answer(f"<b>{sender}</b> [{time}]:\n{msg.text}")
            elif msg.message_type == MessageType.PHOTO:
                caption = f"<b>{sender}</b> [{time}]:" + (f"\n{msg.text.replace('[ФОТО] ', '')}" if msg.text else "")
                await bot.send_photo(
                    chat_id=message.from_user.id,
                    photo=msg.file_id,
                    caption=caption
                )
            elif msg.message_type == MessageType.VIDEO:
                caption = f"<b>{sender}</b> [{time}]:" + (f"\n{msg.text.replace('[ВИДЕО] ', '')}" if msg.text else "")
                await bot.send_video(
                    chat_id=message.from_user.id,
                    video=msg.file_id,
                    caption=caption
                )
            elif msg.message_type == MessageType.DOCUMENT:
                caption = f"<b>{sender}</b> [{time}]:" + (
                    f"\n{msg.text.replace('[ДОКУМЕНТ: ', '').split(']')[1] if ']' in msg.text else ''}" if msg.text else "")
                await bot.send_document(
                    chat_id=message.from_user.id,
                    document=msg.file_id,
                    caption=caption
                )

        await message.answer(
            "<i>Чтобы ответить пользователю, просто отправьте сообщение в этот чат.</i>"
        )


async def handle_user_active_ticket(message: Message, bot: Bot, session: AsyncSession, state: FSMContext, user: User):
    """
    Обработка активного тикета для пользователя
    """
    # Получаем активный тикет пользователя
    active_ticket_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]))
    ).options(selectinload(Ticket.moderator))
    active_ticket_result = await session.execute(active_ticket_query)
    ticket = active_ticket_result.scalar_one_or_none()

    if not ticket:
        await message.answer(
            "📝 <b>Активный тикет</b>\n\n"
            "У вас нет активных тикетов. Вы можете создать новый тикет в главном меню.",
            reply_markup=build_back_keyboard("user:back_to_menu")
        )
        return

    # Формируем сообщение с информацией о тикете
    status_text = {
        TicketStatus.OPEN: "🆕 Открыт (ожидает модератора)",
        TicketStatus.IN_PROGRESS: "🔄 В работе",
        TicketStatus.RESOLVED: "✅ Решен (ожидает подтверждения)",
        TicketStatus.CLOSED: "🔒 Закрыт"
    }.get(ticket.status, "Неизвестный статус")

    message_text = (
        f"📝 <b>Тикет #{ticket.id}</b>\n\n"
        f"Статус: {status_text}\n"
        f"Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )

    if ticket.moderator:
        message_text += f"Модератор: {ticket.moderator.full_name}\n"

    # Добавляем соответствующую клавиатуру в зависимости от статуса
    if ticket.status == TicketStatus.RESOLVED:
        await message.answer(
            message_text,
            reply_markup=build_rating_keyboard()
        )
        await state.set_state(UserStates.RATING_MODERATOR)
        await state.update_data(active_ticket_id=ticket.id)
    else:
        # Для других статусов
        await message.answer(
            message_text,
            reply_markup=build_back_keyboard("user:back_to_menu")
        )

        # Получаем сообщения тикета
        messages_query = select(TicketMessage).where(
            TicketMessage.ticket_id == ticket.id
        ).order_by(TicketMessage.sent_at.asc())
        messages_result = await session.execute(messages_query)
        messages = messages_result.scalars().all()

        # Отображаем последние сообщения
        if messages:
            await message.answer("📜 <b>История сообщений:</b>")

            # Ограничиваем количество сообщений
            max_messages = 10
            start_idx = max(0, len(messages) - max_messages)

            for msg in messages[start_idx:]:
                sender = "Вы" if msg.sender_id == user.id else "Модератор"
                time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

                if msg.message_type == MessageType.SYSTEM:
                    await message.answer(f"🔔 <i>{msg.text}</i>")
                elif msg.message_type == MessageType.TEXT:
                    await message.answer(f"<b>{sender}</b> [{time}]:\n{msg.text}")
                elif msg.message_type == MessageType.PHOTO:
                    caption = f"<b>{sender}</b> [{time}]:" + (
                        f"\n{msg.text.replace('[ФОТО] ', '')}" if msg.text else "")
                    await bot.send_photo(
                        chat_id=message.from_user.id,
                        photo=msg.file_id,
                        caption=caption
                    )
                elif msg.message_type == MessageType.VIDEO:
                    caption = f"<b>{sender}</b> [{time}]:" + (
                        f"\n{msg.text.replace('[ВИДЕО] ', '')}" if msg.text else "")
                    await bot.send_video(
                        chat_id=message.from_user.id,
                        video=msg.file_id,
                        caption=caption
                    )
                elif msg.message_type == MessageType.DOCUMENT:
                    caption = f"<b>{sender}</b> [{time}]:" + (
                        f"\n{msg.text.replace('[ДОКУМЕНТ: ', '').split(']')[1] if ']' in msg.text else ''}" if msg.text else "")
                    await bot.send_document(
                        chat_id=message.from_user.id,
                        document=msg.file_id,
                        caption=caption
                    )

        if ticket.status == TicketStatus.IN_PROGRESS:
            await message.answer(
                "<i>Чтобы ответить модератору, просто отправьте сообщение в этот чат.</i>"
            )
            await state.set_state(UserStates.SENDING_MESSAGE)
            await state.update_data(active_ticket_id=ticket.id)
        else:
            await message.answer(
                "<i>Ожидайте, пока модератор примет ваш тикет в работу.</i>"
            )


@router.message(F.text == "✏️ Новый тикет")
async def reply_new_ticket_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Новый тикет" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        return await command_start(message, session, state)

    # Проверяем, есть ли у пользователя активные тикеты
    active_ticket_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]))
    )
    active_ticket_result = await session.execute(active_ticket_query)
    active_ticket = active_ticket_result.scalar_one_or_none()

    if active_ticket:
        # У пользователя уже есть активный тикет
        await message.answer(
            f"У вас уже есть активный тикет #{active_ticket.id} "
            f"({TICKET_STATUS_EMOJI[active_ticket.status]} {active_ticket.status.value}). "
            f"Пожалуйста, дождитесь его закрытия, прежде чем создавать новый.",
            reply_markup=build_user_main_menu()
        )
        return

    # Отправляем инструкции по созданию тикета
    await message.answer(
        "✏️ <b>Создание нового тикета</b>\n\n"
        "Пожалуйста, опишите вашу проблему в одном сообщении.\n"
        "Вы можете приложить изображение, видео или документ к вашему сообщению.\n\n"
        "<i>Отправьте сообщение с описанием проблемы:</i>",
        reply_markup=build_back_keyboard("user:back_to_menu")
    )

    # Устанавливаем состояние создания тикета
    await state.set_state(UserStates.CREATING_TICKET)

    logger.info(f"User {user_id} accessed create ticket using reply button")


@router.message(F.text == "📋 История тикетов")
async def reply_ticket_history_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "История тикетов" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        return await command_start(message, session, state)

    # Получаем закрытые тикеты пользователя
    tickets_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status == TicketStatus.CLOSED)
    ).order_by(Ticket.created_at.desc())
    tickets_result = await session.execute(tickets_query)
    tickets = tickets_result.scalars().all()

    if not tickets:
        await message.answer(
            "📋 <b>История тикетов</b>\n\n"
            "У вас пока нет закрытых тикетов.",
            reply_markup=build_back_keyboard("user:back_to_menu")
        )
        return

    # Сохраняем тикеты в state для пагинации
    tickets_data = [
        {
            "id": ticket.id,
            "subject": ticket.subject or "Без темы",
            "created_at": ticket.created_at.strftime("%d.%m.%Y %H:%M"),
            "closed_at": ticket.closed_at.strftime("%d.%m.%Y %H:%M") if ticket.closed_at else "Не закрыт",
            "rating": ticket.rating
        }
        for ticket in tickets
    ]
    await state.update_data(tickets=tickets_data, page=0)

    # Формируем сообщение со списком тикетов
    paginator = Paginator(tickets_data, page_size=5)
    page_items = paginator.get_page(0)

    message_text = "📋 <b>История тикетов</b>\n\n"
    for item in page_items:
        stars = RATING_EMOJI.get(int(item["rating"])) if item["rating"] else "Нет оценки"
        message_text += (
            f"🔹 <b>Тикет #{item['id']}</b>\n"
            f"📝 {item['subject']}\n"
            f"📅 Создан: {item['created_at']}\n"
            f"🔒 Закрыт: {item['closed_at']}\n"
            f"⭐ Оценка: {stars}\n\n"
        )

    message_text += f"Страница {1} из {paginator.total_pages}"

    # Создаем клавиатуру с навигацией
    await message.answer(
        message_text,
        reply_markup=build_tickets_list_keyboard(tickets_data, 0)
    )

    await state.set_state(UserStates.VIEWING_TICKET_HISTORY)

    logger.info(f"User {user_id} accessed ticket history using reply button")


@router.message(F.text == "📨 Неназначенные тикеты")
async def reply_unassigned_tickets_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Неназначенные тикеты" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Проверяем, есть ли у модератора активный тикет
    active_mod_ticket_query = select(Ticket).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    active_mod_ticket_result = await session.execute(active_mod_ticket_query)
    active_mod_ticket = active_mod_ticket_result.scalar_one_or_none()

    if active_mod_ticket:
        await message.answer(
            f"⚠️ У вас уже есть активный тикет #{active_mod_ticket.id}.\n\n"
            f"Модератор может работать только с одним тикетом одновременно. "
            f"Пожалуйста, завершите работу с текущим тикетом, прежде чем принимать новый.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        return

    # Получаем неназначенные тикеты
    unassigned_tickets_query = select(Ticket).where(
        (Ticket.status == TicketStatus.OPEN) &
        (Ticket.moderator_id == None)
    ).order_by(Ticket.created_at.asc()).options(selectinload(Ticket.user))
    unassigned_tickets_result = await session.execute(unassigned_tickets_query)
    unassigned_tickets = unassigned_tickets_result.scalars().all()

    if not unassigned_tickets:
        await message.answer(
            "📨 <b>Неназначенные тикеты</b>\n\n"
            "В настоящее время нет неназначенных тикетов.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        return

    # Сохраняем тикеты в state для пагинации
    tickets_data = [
        {
            "id": ticket.id,
            "subject": ticket.subject or "Без темы",
            "created_at": ticket.created_at.strftime("%d.%m.%Y %H:%M"),
            "user_name": ticket.user.full_name if ticket.user else "Неизвестный пользователь"
        }
        for ticket in unassigned_tickets
    ]
    await state.update_data(tickets=tickets_data, page=0)

    # Формируем сообщение со списком тикетов
    paginator = Paginator(tickets_data, page_size=5)
    page_items = paginator.get_page(0)

    message_text = "📨 <b>Неназначенные тикеты</b>\n\n"
    for item in page_items:
        message_text += (
            f"🔹 <b>Тикет #{item['id']}</b>\n"
            f"👤 Пользователь: {item['user_name']}\n"
            f"📝 {item['subject']}\n"
            f"📅 Создан: {item['created_at']}\n\n"
        )

    message_text += f"Страница {1} из {paginator.total_pages}"

    # Создаем клавиатуру с навигацией
    kb = InlineKeyboardBuilder()

    for item in page_items:
        kb.add(InlineKeyboardButton(
            text=f"Принять тикет #{item['id']}",
            callback_data=f"mod:take_ticket:{item['id']}"
        ))

    # Добавляем навигационные кнопки
    row = []
    if paginator.total_pages > 1:
        row.append(InlineKeyboardButton(text="▶️", callback_data="mod:page:1"))

    row.append(InlineKeyboardButton(text="🔙 Назад", callback_data="mod:back_to_menu"))
    kb.row(*row)

    await message.answer(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(ModeratorStates.VIEWING_TICKETS)

    logger.info(f"Moderator {user_id} accessed unassigned tickets using reply button")


@router.message(F.text == "📊 Моя статистика")
async def reply_my_stats_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Моя статистика" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Получаем статистику по закрытым тикетам
    closed_tickets_query = select(func.count(Ticket.id), func.avg(Ticket.rating)).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.CLOSED)
    )
    closed_tickets_result = await session.execute(closed_tickets_query)
    closed_count, avg_rating = closed_tickets_result.one()

    # Получаем статистику по тикетам в работе
    in_progress_tickets_query = select(func.count(Ticket.id)).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    in_progress_result = await session.execute(in_progress_tickets_query)
    in_progress_count = in_progress_result.scalar()

    # Получаем статистику по решенным тикетам, ожидающим оценки
    resolved_tickets_query = select(func.count(Ticket.id)).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.RESOLVED)
    )
    resolved_result = await session.execute(resolved_tickets_query)
    resolved_count = resolved_result.scalar()

    # Получаем статистику по всем тикетам
    all_tickets_query = select(func.count(Ticket.id)).where(
        Ticket.moderator_id == user.id
    )
    all_tickets_result = await session.execute(all_tickets_query)
    all_tickets_count = all_tickets_result.scalar()

    # Форматируем средний рейтинг
    avg_rating_text = f"{avg_rating:.2f}" if avg_rating else "Нет оценок"
    avg_rating_stars = RATING_EMOJI.get(round(avg_rating)) if avg_rating else "Нет оценок"

    # Формируем сообщение со статистикой
    message_text = (
        f"📊 <b>Статистика модератора {user.full_name}</b>\n\n"
        f"<b>Обработано тикетов:</b> {all_tickets_count}\n"
        f"<b>Закрыто тикетов:</b> {closed_count}\n"
        f"<b>Тикетов в работе:</b> {in_progress_count}\n"
        f"<b>Решенных тикетов (ожидают оценки):</b> {resolved_count}\n\n"
        f"<b>Средний рейтинг:</b> {avg_rating_text} {avg_rating_stars}\n"
    )

    # Получаем последние 5 закрытых тикетов
    recent_tickets_query = select(Ticket).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.CLOSED)
    ).order_by(Ticket.closed_at.desc()).limit(5).options(selectinload(Ticket.user))
    recent_tickets_result = await session.execute(recent_tickets_query)
    recent_tickets = recent_tickets_result.scalars().all()

    if recent_tickets:
        message_text += "\n<b>Последние закрытые тикеты:</b>\n"
        for ticket in recent_tickets:
            rating_text = RATING_EMOJI.get(int(ticket.rating)) if ticket.rating else "Без оценки"
            message_text += (
                f"🔹 <b>Тикет #{ticket.id}</b> - {rating_text}\n"
                f"👤 Пользователь: {ticket.user.full_name}\n"
                f"📅 Закрыт: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )

    await message.answer(
        message_text,
        reply_markup=build_back_keyboard("mod:back_to_menu")
    )

    logger.info(f"Moderator {user_id} viewed their stats using reply button")


@router.message(F.text == "📈 Статистика")
async def reply_stats_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Статистика" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.ADMIN:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Получаем статистику по пользователям
    users_stats_query = select(
        func.count(User.id).filter(User.role == UserRole.USER).label("users_count"),
        func.count(User.id).filter(User.role == UserRole.MODERATOR).label("moderators_count"),
        func.count(User.id).filter(User.role == UserRole.ADMIN).label("admins_count")
    )
    users_stats_result = await session.execute(users_stats_query)
    users_stats = users_stats_result.one()

    # Получаем статистику по тикетам
    tickets_stats_query = select(
        func.count(Ticket.id).label("total_tickets"),
        func.count(Ticket.id).filter(Ticket.status == TicketStatus.OPEN).label("open_tickets"),
        func.count(Ticket.id).filter(Ticket.status == TicketStatus.IN_PROGRESS).label("in_progress_tickets"),
        func.count(Ticket.id).filter(Ticket.status == TicketStatus.RESOLVED).label("resolved_tickets"),
        func.count(Ticket.id).filter(Ticket.status == TicketStatus.CLOSED).label("closed_tickets"),
        func.avg(Ticket.rating).filter(Ticket.status == TicketStatus.CLOSED).label("avg_rating")
    )
    tickets_stats_result = await session.execute(tickets_stats_query)
    tickets_stats = tickets_stats_result.one()

    # Формируем статистику
    message_text = (
        f"📈 <b>Общая статистика</b>\n\n"
        f"<b>Пользователи:</b>\n"
        f"👤 Пользователи: {users_stats.users_count}\n"
        f"🔑 Модераторы: {users_stats.moderators_count}\n"
        f"👑 Администраторы: {users_stats.admins_count}\n\n"

        f"<b>Тикеты:</b>\n"
        f"📊 Всего тикетов: {tickets_stats.total_tickets}\n"
        f"🆕 Открытых: {tickets_stats.open_tickets}\n"
        f"🔄 В работе: {tickets_stats.in_progress_tickets}\n"
        f"✅ Решенных (ожидают оценки): {tickets_stats.resolved_tickets}\n"
        f"🔒 Закрытых: {tickets_stats.closed_tickets}\n"
        f"⭐ Средняя оценка: {tickets_stats.avg_rating:.2f if tickets_stats.avg_rating else 'Нет оценок'}/5.0\n\n"
    )

    await message.answer(
        message_text,
        reply_markup=build_back_keyboard("admin:back_to_menu")
    )

    await state.set_state(AdminStates.VIEWING_STATISTICS)

    logger.info(f"Admin {user_id} viewed general statistics using reply button")


@router.message(F.text == "👨‍💼 Управление модераторами")
async def reply_manage_mods_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Управление модераторами" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.ADMIN:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Получаем список модераторов
    moderators_query = select(User).where(User.role == UserRole.MODERATOR)
    moderators_result = await session.execute(moderators_query)
    moderators = moderators_result.scalars().all()

    # Формируем сообщение со списком модераторов
    message_text = "👨‍💼 <b>Управление модераторами</b>\n\n"

    if not moderators:
        message_text += "В настоящее время нет назначенных модераторов."
    else:
        message_text += "<b>Текущие модераторы:</b>\n\n"
        for i, mod in enumerate(moderators, 1):
            message_text += f"{i}. {mod.full_name} (ID: {mod.telegram_id})\n"

    # Создаем клавиатуру с действиями
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="➕ Добавить модератора", callback_data="admin:add_moderator"))

    if moderators:
        kb.add(InlineKeyboardButton(text="❌ Удалить модератора", callback_data="admin:remove_moderator"))

    kb.add(InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back_to_menu"))

    # Размещаем кнопки в один столбец
    kb.adjust(1)

    await message.answer(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(AdminStates.MANAGING_MODERATORS)

    logger.info(f"Admin {user_id} accessed moderator management using reply button")


@router.message(F.text == "🔍 Поиск тикета")
async def reply_search_ticket_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик кнопки "Поиск тикета" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.ADMIN:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Так как функция поиска тикета не реализована в коде, предлагаем базовую реализацию
    await message.answer(
        "🔍 <b>Поиск тикета</b>\n\n"
        "Эта функция пока находится в разработке.\n"
        "Пожалуйста, используйте другие возможности для работы с тикетами.",
        reply_markup=build_admin_main_menu()
    )
    await state.set_state(AdminStates.MAIN_MENU)

    logger.info(f"Admin {user_id} tried to access ticket search using reply button")


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
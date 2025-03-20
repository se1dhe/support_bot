import logging
from typing import Union, Dict, List, Any, Optional
from datetime import datetime

from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from models import User, Ticket, Message as TicketMessage, TicketStatus, MessageType, UserRole
from utils.i18n import _
from utils.keyboards import KeyboardFactory
from utils.states import UserStates
from utils.paginator import Paginator

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.callback_query(F.data == "user:create_ticket")
async def create_ticket_cmd_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика команды создания нового тикета
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик create_ticket_cmd!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_create_ticket(callback_query, session, state)



async def _process_create_ticket(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика команды создания нового тикета
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

    # Проверяем, есть ли у пользователя активные тикеты
    active_ticket_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]))
    )
    active_ticket_result = await session.execute(active_ticket_query)
    active_ticket = active_ticket_result.scalar_one_or_none()

    if active_ticket:
        # У пользователя уже есть активный тикет
        await callback_query.message.edit_text(
            f"У вас уже есть активный тикет #{active_ticket.id}. "
            f"Пожалуйста, дождитесь его закрытия, прежде чем создавать новый.",
            reply_markup=KeyboardFactory.back_button("user:back_to_menu", user.language)
        )
        await callback_query.answer()
        return

    # Отправляем инструкции по созданию тикета
    await callback_query.message.edit_text(
        "✏️ <b>Создание нового тикета</b>\n\n"
        "Пожалуйста, опишите вашу проблему в одном сообщении.\n"
        "Вы можете приложить изображение, видео или документ к вашему сообщению.\n\n"
        "<i>Отправьте сообщение с описанием проблемы:</i>",
        reply_markup=KeyboardFactory.back_button("user:back_to_menu", user.language)
    )

    # Устанавливаем состояние создания тикета
    await state.set_state(UserStates.CREATING_TICKET)
    await callback_query.answer()

    logger.info(f"User {user_id} started ticket creation")


@router.message(UserStates.CREATING_TICKET, F.text | F.photo | F.document | F.video)
async def process_ticket_creation_wrapper(message: Message, bot: Bot, state: FSMContext, **kwargs):
    """
    Обертка для обработчика сообщения для создания тикета
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_ticket_creation!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_ticket_creation(message, bot, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_ticket_creation(message, bot, session, state)


async def _process_ticket_creation(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика сообщения для создания тикета
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Произошла ошибка. Пожалуйста, перезапустите бота: /start")
        return

    # Проверяем, есть ли у пользователя активные тикеты
    active_ticket_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED])))
    active_ticket_result = await session.execute(active_ticket_query)
    active_ticket = active_ticket_result.scalar_one_or_none()

    if active_ticket:
        # У пользователя уже есть активный тикет
        await message.answer(
            _(
                "error_already_has_active_ticket",
                user.language,
                ticket_id=active_ticket.id
            ),
            reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
        )
        await state.set_state(UserStates.MAIN_MENU)
        return

    # Создаем новый тикет
    new_ticket = Ticket(
        user_id=user.id,
        status=TicketStatus.OPEN,
        subject=message.text[:50] + "..." if message.text and len(message.text) > 50 else message.text
    )
    session.add(new_ticket)
    await session.flush()  # Для получения ID тикета

    # Определяем тип сообщения и сохраняем его
    message_type = MessageType.TEXT
    file_id = None
    text = message.text or ""

    if message.photo:
        message_type = MessageType.PHOTO
        file_id = message.photo[-1].file_id  # Берем фото максимального размера
        caption = message.caption or ""
        text = f"[ФОТО] {caption}"
    elif message.document:
        message_type = MessageType.DOCUMENT
        file_id = message.document.file_id
        caption = message.caption or ""
        text = f"[ДОКУМЕНТ: {message.document.file_name}] {caption}"
    elif message.video:
        message_type = MessageType.VIDEO
        file_id = message.video.file_id
        caption = message.caption or ""
        text = f"[ВИДЕО] {caption}"

    # Сохраняем сообщение в базу данных
    ticket_message = TicketMessage(
        ticket_id=new_ticket.id,
        sender_id=user.id,
        message_type=message_type,
        text=text,
        file_id=file_id
    )
    session.add(ticket_message)

    # Сохраняем изменения в БД
    await session.commit()

    # Уведомляем пользователя о создании тикета
    await message.answer(
        _(
            "ticket_created",
            user.language,
            ticket_id=new_ticket.id
        ) + "\n\n" +
        _(
            "ticket_sent_to_support",
            user.language
        ) + " " +
        _(
            "wait_for_moderator",
            user.language
        ),
        reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
    )

    # Возвращаем пользователя в главное меню
    await state.set_state(UserStates.MAIN_MENU)

    # Отправляем уведомления всем модераторам
    moderators_query = select(User).where(User.role == UserRole.MODERATOR)
    moderators_result = await session.execute(moderators_query)
    moderators = moderators_result.scalars().all()

    for moderator in moderators:
        # Создаем клавиатуру с кнопкой "Принять тикет"
        keyboard = KeyboardFactory.ticket_actions(TicketStatus.OPEN, new_ticket.id, moderator.language)

        # Отправляем уведомление
        try:
            await bot.send_message(
                chat_id=moderator.telegram_id,
                text=f"📩 <b>Новый тикет #{new_ticket.id}</b>\n\n"
                     f"От: {user.full_name}\n"
                     f"Тема: {new_ticket.subject or 'Не указана'}\n\n"
                     f"Сообщение:\n{text}",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Failed to send notification to moderator {moderator.telegram_id}: {e}")

    logger.info(f"User {user_id} created ticket #{new_ticket.id}")


@router.callback_query(F.data == "user:ticket_history")
async def ticket_history_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика просмотра истории тикетов
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик ticket_history!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_ticket_history(callback_query, session, state)


async def _process_ticket_history(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика просмотра истории тикетов
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

    # Получаем закрытые тикеты пользователя
    tickets_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status == TicketStatus.CLOSED)
    ).order_by(Ticket.created_at.desc())
    tickets_result = await session.execute(tickets_query)
    tickets = tickets_result.scalars().all()

    if not tickets:
        await callback_query.message.edit_text(
            _("ticket_history_title", user.language) + "\n\n" +
            _("no_closed_tickets", user.language),
            reply_markup=KeyboardFactory.back_button("user:back_to_menu", user.language)
        )
        await callback_query.answer()
        return

    # Сохраняем тикеты в state для пагинации
    tickets_data = [
        {
            "id": ticket.id,
            "text": f"Тикет #{ticket.id} - {ticket.subject or 'Без темы'}",
            "subject": ticket.subject or _("no_subject", user.language),
            "created_at": ticket.created_at.strftime("%d.%m.%Y %H:%M"),
            "closed_at": ticket.closed_at.strftime("%d.%m.%Y %H:%M") if ticket.closed_at else "Не закрыт",
            "rating": ticket.rating
        }
        for ticket in tickets
    ]
    await state.update_data(tickets=tickets_data, page=0)

    # Создаем пагинатор для тикетов
    paginator = Paginator(tickets_data, page_size=5)
    page_items = paginator.get_page(0)

    # Формируем сообщение со списком тикетов
    message_text = _("ticket_history_title", user.language) + "\n\n"

    for item in page_items:
        rating_stars = "⭐" * int(item["rating"]) if item["rating"] else "Нет оценки"
        message_text += (
            f"🔹 <b>Тикет #{item['id']}</b>\n"
            f"📝 {item['subject']}\n"
            f"📅 Создан: {item['created_at']}\n"
            f"🔒 Закрыт: {item['closed_at']}\n"
            f"⭐ Оценка: {rating_stars}\n\n"
        )

    message_text += _("page_info", user.language, current_page=1, total_pages=paginator.total_pages)

    # Отправляем сообщение с клавиатурой
    await callback_query.message.edit_text(
        message_text,
        reply_markup=KeyboardFactory.paginated_list(
            tickets_data,
            0,
            page_size=5,
            action_prefix="ticket",
            back_callback="user:back_to_menu",
            language=user.language
        )
    )

    await state.set_state(UserStates.VIEWING_TICKET_HISTORY)
    await callback_query.answer()

    logger.info(f"User {user_id} viewed ticket history")


@router.callback_query(F.data == "user:active_ticket")
async def active_ticket_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика просмотра активного тикета
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик active_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик active_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_active_ticket(callback_query, bot, session, state)


async def _process_active_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика просмотра активного тикета
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

    # Получаем активный тикет пользователя
    active_ticket_query = select(Ticket).where(
        (Ticket.user_id == user.id) &
        (Ticket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]))
    ).options(selectinload(Ticket.moderator))
    active_ticket_result = await session.execute(active_ticket_query)
    ticket = active_ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            _("active_ticket_title", user.language) + "\n\n" +
            _("no_active_tickets", user.language),
            reply_markup=KeyboardFactory.back_button("user:back_to_menu", user.language)
        )
        await callback_query.answer()
        return

    # Формируем сообщение с информацией о тикете
    status_texts = {
        TicketStatus.OPEN: "🆕 " + _("status_open", user.language) + " (ожидает модератора)",
        TicketStatus.IN_PROGRESS: "🔄 " + _("status_in_progress", user.language),
        TicketStatus.RESOLVED: "✅ " + _("status_resolved", user.language) + " (ожидает подтверждения)",
        TicketStatus.CLOSED: "🔒 " + _("status_closed", user.language)
    }

    message_text = (
        f"📝 <b>Тикет #{ticket.id}</b>\n\n"
        f"Статус: {status_texts.get(ticket.status, 'Неизвестный статус')}\n"
        f"Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )

    if ticket.moderator:
        message_text += f"Модератор: {ticket.moderator.full_name}\n"

    # Определяем клавиатуру в зависимости от статуса тикета
    if ticket.status == TicketStatus.RESOLVED:
        keyboard = KeyboardFactory.rating_keyboard(user.language)
        await state.set_state(UserStates.RATING_MODERATOR)
        await state.update_data(active_ticket_id=ticket.id)
    else:
        keyboard = KeyboardFactory.back_button("user:back_to_menu", user.language)

        # Отправляем сообщение с информацией о тикете
    await callback_query.message.edit_text(
        message_text,
        reply_markup=keyboard
    )

    # Получаем сообщения тикета
    messages_query = select(TicketMessage).where(
        TicketMessage.ticket_id == ticket.id
    ).order_by(TicketMessage.sent_at.asc())
    messages_result = await session.execute(messages_query)
    messages = messages_result.scalars().all()

    # Отправляем историю сообщений
    if messages:
        await callback_query.message.answer(_("message_history", user.language))

        # Ограничиваем количество сообщений
        max_messages = 20
        start_idx = max(0, len(messages) - max_messages)

        # Если в тикете много сообщений, добавляем информацию об ограничении
        if len(messages) > max_messages:
            await callback_query.message.answer(
                f"<i>Показаны последние {max_messages} из {len(messages)} сообщений.</i>"
            )

        # Отправляем сообщения
        for msg in messages[start_idx:]:
            sender = "Вы" if msg.sender_id == user.id else "Модератор"
            time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

            if msg.message_type == MessageType.SYSTEM:
                await callback_query.message.answer(f"🔔 <i>{msg.text}</i>")
            elif msg.message_type == MessageType.TEXT:
                await callback_query.message.answer(f"<b>{sender}</b> [{time}]:\n{msg.text}")
            elif msg.message_type == MessageType.PHOTO:
                caption = f"<b>{sender}</b> [{time}]:" + (
                    f"\n{msg.text.replace('[ФОТО] ', '')}" if msg.text else "")
                await bot.send_photo(
                    chat_id=callback_query.from_user.id,
                    photo=msg.file_id,
                    caption=caption
                )
            elif msg.message_type == MessageType.VIDEO:
                caption = f"<b>{sender}</b> [{time}]:" + (
                    f"\n{msg.text.replace('[ВИДЕО] ', '')}" if msg.text else "")
                await bot.send_video(
                    chat_id=callback_query.from_user.id,
                    video=msg.file_id,
                    caption=caption
                )
            elif msg.message_type == MessageType.DOCUMENT:
                caption = f"<b>{sender}</b> [{time}]:" + (
                    f"\n{msg.text.replace('[ДОКУМЕНТ: ', '').split(']')[1] if ']' in msg.text else ''}" if msg.text else "")
                await bot.send_document(
                    chat_id=callback_query.from_user.id,
                    document=msg.file_id,
                    caption=caption
                )

    # Добавляем дополнительные инструкции в зависимости от статуса тикета
    if ticket.status == TicketStatus.IN_PROGRESS:
        await callback_query.message.answer(
            "<i>Чтобы ответить модератору, просто отправьте сообщение в этот чат.</i>"
        )
        await state.set_state(UserStates.SENDING_MESSAGE)
        await state.update_data(active_ticket_id=ticket.id)
    elif ticket.status == TicketStatus.OPEN:
        await callback_query.message.answer(
            _("wait_for_moderator_assignment", user.language)
        )

    await callback_query.answer()

    logger.info(f"User {user_id} viewed active ticket #{ticket.id}")


@router.message(UserStates.SENDING_MESSAGE, F.text | F.photo | F.document | F.video)
async def process_ticket_message_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика сообщения в активном тикете
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_ticket_message!")
        await message.answer(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик process_ticket_message!")
        await message.answer(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        return

    return await _process_ticket_message(message, bot, session, state)


async def _process_ticket_message(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика сообщения в активном тикете
    """
    # Получаем данные из состояния
    state_data = await state.get_data()
    ticket_id = state_data.get("active_ticket_id")

    if not ticket_id:
        await message.answer(
            "Произошла ошибка. Пожалуйста, вернитесь в главное меню: /menu"
        )
        return

    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Произошла ошибка. Пожалуйста, перезапустите бота: /start")
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.user_id == user.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.moderator))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket or not ticket.moderator:
        await message.answer(
            "Невозможно отправить сообщение. Возможно, тикет был закрыт "
            "или еще не принят модератором.",
            reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
        )
        await state.set_state(UserStates.MAIN_MENU)
        return

    # Определяем тип сообщения и сохраняем его
    message_type = MessageType.TEXT
    file_id = None
    text = message.text or ""

    if message.photo:
        message_type = MessageType.PHOTO
        file_id = message.photo[-1].file_id
        caption = message.caption or ""
        text = f"[ФОТО] {caption}"
    elif message.document:
        message_type = MessageType.DOCUMENT
        file_id = message.document.file_id
        caption = message.caption or ""
        text = f"[ДОКУМЕНТ: {message.document.file_name}] {caption}"
    elif message.video:
        message_type = MessageType.VIDEO
        file_id = message.video.file_id
        caption = message.caption or ""
        text = f"[ВИДЕО] {caption}"

    # Сохраняем сообщение в базу данных
    ticket_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=user.id,
        message_type=message_type,
        text=text,
        file_id=file_id
    )
    session.add(ticket_message)

    # Обновляем время последнего обновления тикета
    ticket.updated_at = datetime.now()

    await session.commit()

    # Отправляем подтверждение пользователю
    await message.answer(_("user_message_sent", user.language))

    # Отправляем сообщение модератору
    try:
        # Отправляем в зависимости от типа сообщения
        if message_type == MessageType.TEXT:
            await bot.send_message(
                chat_id=ticket.moderator.telegram_id,
                text=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                     f"От: {user.full_name}\n\n"
                     f"{text}"
            )
        elif message_type == MessageType.PHOTO:
            await bot.send_photo(
                chat_id=ticket.moderator.telegram_id,
                photo=file_id,
                caption=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                        f"От: {user.full_name}\n\n"
                        f"{message.caption or ''}"
            )
        elif message_type == MessageType.DOCUMENT:
            await bot.send_document(
                chat_id=ticket.moderator.telegram_id,
                document=file_id,
                caption=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                        f"От: {user.full_name}\n\n"
                        f"{message.caption or ''}"
            )
        elif message_type == MessageType.VIDEO:
            await bot.send_video(
                chat_id=ticket.moderator.telegram_id,
                video=file_id,
                caption=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                        f"От: {user.full_name}\n\n"
                        f"{message.caption or ''}"
            )
    except Exception as e:
        logger.error(f"Failed to send message to moderator {ticket.moderator.telegram_id}: {e}")
        await message.answer(
            "⚠️ Не удалось доставить сообщение модератору. "
            "Но оно сохранено в истории тикета."
        )

    logger.info(f"User {user_id} sent message to ticket #{ticket.id}")


@router.callback_query(F.data.startswith("rating:"))
async def process_rating_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика выставления оценки модератору
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_rating!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик process_rating!")
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_rating(callback_query, bot, session, state)


async def _process_rating(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика выставления оценки модератору
    """
    user_id = callback_query.from_user.id
    rating = int(callback_query.data.split(":")[1])

    logger.info(f"Пользователь {user_id} выставил оценку {rating}")

    # Получаем текущее состояние FSM для логирования
    current_state = await state.get_state()
    logger.info(f"Текущее состояние пользователя {user_id}: {current_state}")

    # Получаем данные из состояния
    state_data = await state.get_data()
    ticket_id = state_data.get("active_ticket_id")
    logger.info(f"Данные состояния для пользователя {user_id}: active_ticket_id={ticket_id}")

    try:
        # Получаем пользователя из БД
        query = select(User).where(User.telegram_id == user_id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            logger.error(f"Пользователь с ID {user_id} не найден в базе данных")
            await callback_query.message.edit_text(
                "Ошибка идентификации пользователя. Пожалуйста, перезапустите бота, отправив команду /start"
            )
            await callback_query.answer()
            return

        # Если ID тикета не найден в состоянии, ищем активный решенный тикет пользователя
        if not ticket_id:
            logger.warning(
                f"active_ticket_id не найден в состоянии для пользователя {user_id}, ищем активный решенный тикет")
            # Ищем решенный тикет пользователя
            ticket_query = select(Ticket).where(
                (Ticket.user_id == user.id) &
                (Ticket.status == TicketStatus.RESOLVED)
            ).order_by(Ticket.updated_at.desc())
            ticket_result = await session.execute(ticket_query)
            resolved_tickets = ticket_result.scalars().all()

            if resolved_tickets:
                ticket_id = resolved_tickets[0].id
                logger.info(f"Найден активный решенный тикет #{ticket_id} для пользователя {user_id}")

                # Обновляем состояние с найденным ID тикета
                await state.update_data(active_ticket_id=ticket_id)
                logger.info(f"Обновлены данные состояния пользователя {user_id}: active_ticket_id={ticket_id}")
            else:
                logger.warning(f"Не найдено активных решенных тикетов для пользователя {user_id}")
                await callback_query.message.edit_text(
                    "У вас нет активных тикетов, ожидающих оценки. Возможно, тикет уже был закрыт или произошла ошибка синхронизации.",
                    reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
                )
                await state.set_state(UserStates.MAIN_MENU)
                logger.info(f"Пользователь {user_id} переведен в состояние MAIN_MENU")
                await callback_query.answer()
                return

        # Получаем тикет из БД
        logger.info(f"Поиск тикета #{ticket_id} для пользователя {user_id}")
        ticket_query = select(Ticket).where(
            (Ticket.id == ticket_id) &
            (Ticket.user_id == user.id) &
            (Ticket.status == TicketStatus.RESOLVED)
        ).options(selectinload(Ticket.moderator))
        ticket_result = await session.execute(ticket_query)
        ticket = ticket_result.scalar_one_or_none()

        if not ticket:
            logger.warning(f"Тикет #{ticket_id} не найден или не принадлежит пользователю {user_id}")
            await callback_query.message.edit_text(
                f"Тикет #{ticket_id} не найден или не доступен для оценки. Пожалуйста, вернитесь в главное меню.",
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
            )
            await state.set_state(UserStates.MAIN_MENU)
            await callback_query.answer()
            return

        if not ticket.moderator:
            logger.warning(f"Тикет #{ticket_id} не имеет назначенного модератора")
            await callback_query.message.edit_text(
                f"Невозможно оценить тикет #{ticket_id}, так как он не был обработан модератором.",
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
            )
            await state.set_state(UserStates.MAIN_MENU)
            await callback_query.answer()
            return

        if ticket.status != TicketStatus.RESOLVED:
            logger.warning(
                f"Тикет #{ticket_id} имеет неверный статус: {ticket.status} (ожидается {TicketStatus.RESOLVED})")
            await callback_query.message.edit_text(
                f"Тикет #{ticket_id} имеет статус '{ticket.status.value}', оценка доступна только для статуса 'resolved'.",
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
            )
            await state.set_state(UserStates.MAIN_MENU)
            await callback_query.answer()
            return

        # Обновляем тикет: ставим оценку, меняем статус и добавляем время закрытия
        logger.info(f"Обновление тикета #{ticket_id}: оценка {rating}, статус -> CLOSED")
        ticket.rating = rating
        ticket.status = TicketStatus.CLOSED
        ticket.closed_at = datetime.now()

        # Добавляем системное сообщение об оценке
        rating_stars = "⭐" * rating
        system_message = TicketMessage(
            ticket_id=ticket.id,
            sender_id=user.id,
            message_type=MessageType.SYSTEM,
            text=f"Пользователь оценил работу модератора на {rating_stars} ({rating}/5)"
        )
        session.add(system_message)
        logger.info(f"Добавлено системное сообщение об оценке для тикета #{ticket_id}")

        try:
            await session.commit()
            logger.info(f"Изменения успешно сохранены в базе данных для тикета #{ticket_id}")
        except Exception as db_error:
            logger.error(f"Ошибка при сохранении изменений в базе данных: {db_error}", exc_info=True)
            await session.rollback()
            await callback_query.message.edit_text(
                "Произошла ошибка при сохранении вашей оценки. Пожалуйста, попробуйте еще раз позже.",
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
            )
            await state.set_state(UserStates.MAIN_MENU)
            await callback_query.answer()
            return

        # Отправляем подтверждение пользователю
        logger.info(f"Отправка подтверждения пользователю {user_id} о закрытии тикета #{ticket_id}")
        try:
            await callback_query.message.edit_text(
                _("thank_you_for_rating", user.language) + "\n\n" +
                _("ticket_closed", user.language, ticket_id=ticket.id) + "\n\n" +
                _("create_new_ticket_info", user.language),
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
            )
        except Exception as msg_error:
            logger.error(f"Ошибка при отправке сообщения пользователю: {msg_error}", exc_info=True)
            # Пробуем отправить новое сообщение
            try:
                await callback_query.message.answer(
                    _("thank_you_for_rating", user.language) + "\n\n" +
                    _("ticket_closed", user.language, ticket_id=ticket.id) + "\n\n" +
                    _("create_new_ticket_info", user.language),
                    reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
                )
            except Exception as retry_error:
                logger.error(f"Повторная ошибка при отправке сообщения: {retry_error}", exc_info=True)

        # Уведомляем модератора об оценке
        logger.info(f"Отправка уведомления модератору {ticket.moderator.telegram_id} об оценке тикета #{ticket.id}")
        try:
            await bot.send_message(
                chat_id=ticket.moderator.telegram_id,
                text=f"⭐ <b>Тикет #{ticket.id} закрыт</b>\n\n"
                     f"Пользователь {user.full_name} оценил вашу работу на "
                     f"{rating_stars} ({rating}/5).\n\n"
                     f"Спасибо за вашу работу!"
            )
            logger.info(f"Уведомление успешно отправлено модератору {ticket.moderator.telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления модератору {ticket.moderator.telegram_id}: {e}",
                         exc_info=True)

        # Очищаем состояние и переводим пользователя в главное меню
        await state.clear()
        logger.info(f"Состояние пользователя {user_id} очищено")
        await state.set_state(UserStates.MAIN_MENU)
        logger.info(f"Пользователь {user_id} переведен в состояние MAIN_MENU")
        await callback_query.answer()

        logger.info(f"Пользователь {user_id} успешно оценил тикет #{ticket.id} с оценкой {rating}/5")

    except Exception as e:
        logger.error(f"Непредвиденная ошибка при обработке оценки от пользователя {user_id}: {e}", exc_info=True)
        try:
            await callback_query.message.edit_text(
                "Произошла неожиданная ошибка при обработке вашей оценки. Пожалуйста, попробуйте еще раз или обратитесь к администратору.",
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language if user else None)
            )
        except Exception:
            # В случае ошибки с изменением сообщения, пробуем отправить новое
            await callback_query.message.answer(
                "Произошла неожиданная ошибка при обработке вашей оценки. Пожалуйста, попробуйте еще раз или обратитесь к администратору.",
                reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language if user else None)
            )

        await state.set_state(UserStates.MAIN_MENU)
        await callback_query.answer()


@router.callback_query(F.data == "user:change_language")
async def change_language_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика изменения языка
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик change_language!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_change_language(callback_query, session, state)


async def _process_change_language(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика изменения языка
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

    await callback_query.message.edit_text(
        _("language_selection", user.language),
        reply_markup=KeyboardFactory.language_selection(user.language)
    )

    await callback_query.answer()

    logger.info(f"User {user_id} accessed language selection")


@router.callback_query(F.data == "user:back_to_menu")
async def back_to_menu_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика возврата в главное меню
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик back_to_menu!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_back_to_menu(callback_query, session, state)


async def _process_back_to_menu(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика возврата в главное меню
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

    await callback_query.message.edit_text(
        _("user_main_menu", user.language),
        reply_markup=KeyboardFactory.main_menu(UserRole.USER, user.language)
    )

    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"User {user_id} returned to main menu")


@router.callback_query(F.data.startswith("language:"))
async def process_language_selection_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика выбора языка
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_language_selection!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_language_selection(callback_query, session, state)


async def _process_language_selection(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика выбора языка
    """
    user_id = callback_query.from_user.id
    selected_language = callback_query.data.split(":")[1]

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

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

    # Отправляем сообщение с новым языком
    await callback_query.message.edit_text(
        welcome_text + "\n\n" + _("user_main_menu", selected_language),
        reply_markup=KeyboardFactory.main_menu(UserRole.USER, selected_language)
    )

    # Устанавливаем состояние главного меню
    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"User {user_id} changed language to {selected_language}")


def register_handlers(dp: Dispatcher):
    """
    Регистрирует все обработчики данного модуля.

    Args:
        dp: Диспетчер
    """
    dp.include_router(router)


@router.message(F.text == "📝 Мой активный тикет")
async def active_ticket_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Активный тикет" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик active_ticket_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_active_ticket_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_active_ticket_button(message, session, state)


async def _process_active_ticket_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Активный тикет" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Произошла ошибка. Пожалуйста, перезапустите бота: /start")
        return

    # Симулируем нажатие на Inline кнопку для активного тикета
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "user:active_ticket"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Получаем bot из контекста сообщения
    bot = message.bot

    # Вызываем обработчик для Inline кнопки "Активный тикет"
    await active_ticket_wrapper(fake_callback, state, session=session, bot=bot)

    logger.info(f"User {user_id} used Reply button 'Active Ticket'")


async def _process_create_ticket_button(message: Message, session: AsyncSession, state: FSMContext, **kwargs):
    """
    Реализация обработчика кнопки "Создать тикет" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Произошла ошибка. Пожалуйста, перезапустите бота: /start")
        return

    # Симулируем нажатие на Inline кнопку для создания тикета
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "user:create_ticket"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "Создать тикет"
    await create_ticket_cmd_wrapper(fake_callback, state, session=session)

    logger.info(f"User {user_id} used Reply button 'Create Ticket'")


@router.message(F.text == "✏️ Создать тикет")
async def create_ticket_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Создать тикет" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик create_ticket_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_create_ticket_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_create_ticket_button(message, session, state)


async def _process_create_ticket_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Создать тикет" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Произошла ошибка. Пожалуйста, перезапустите бота: /start")
        return

    # Симулируем нажатие на Inline кнопку для создания тикета
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "user:create_ticket"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "Создать тикет"
    await create_ticket_cmd_wrapper(fake_callback, state, session=session)

    logger.info(f"User {user_id} used Reply button 'Create Ticket'")


@router.message(F.text == "📋 История тикетов")
async def ticket_history_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "История тикетов" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик ticket_history_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_ticket_history_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_ticket_history_button(message, session, state)


async def _process_ticket_history_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "История тикетов" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await message.answer("Произошла ошибка. Пожалуйста, перезапустите бота: /start")
        return

    # Симулируем нажатие на Inline кнопку для истории тикетов
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "user:ticket_history"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "История тикетов"
    await ticket_history_wrapper(fake_callback, state, session=session)

    logger.info(f"User {user_id} used Reply button 'Ticket History'")
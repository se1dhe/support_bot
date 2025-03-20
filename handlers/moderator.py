import logging
from typing import Union, Dict, List, Any, Optional
from datetime import datetime

from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from models import User, Ticket, Message as TicketMessage, TicketStatus, MessageType, UserRole
from utils.i18n import _
from utils.keyboards import KeyboardFactory
from utils.states import ModeratorStates, UserStates
from utils.paginator import Paginator

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.callback_query(F.data == "mod:unassigned_tickets")
async def unassigned_tickets_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика просмотра неназначенных тикетов
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик unassigned_tickets!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_unassigned_tickets(callback_query, session, state)


async def _process_unassigned_tickets(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика просмотра неназначенных тикетов
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            _("error_access_denied", user.language if user else None)
        )
        await callback_query.answer()
        return

    # Проверяем, есть ли у модератора активный тикет
    active_mod_ticket_query = select(Ticket).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    active_mod_ticket_result = await session.execute(active_mod_ticket_query)
    active_mod_ticket = active_mod_ticket_result.scalar_one_or_none()

    if active_mod_ticket:
        await callback_query.message.edit_text(
            f"⚠️ У вас уже есть активный тикет #{active_mod_ticket.id}.\n\n"
            f"Модератор может работать только с одним тикетом одновременно. "
            f"Пожалуйста, завершите работу с текущим тикетом, прежде чем принимать новый.",
            reply_markup=KeyboardFactory.back_button("mod:back_to_menu", user.language)
        )
        await callback_query.answer()
        return

    # Получаем неназначенные тикеты
    unassigned_tickets_query = select(Ticket).where(
        (Ticket.status == TicketStatus.OPEN) &
        (Ticket.moderator_id == None)
    ).order_by(Ticket.created_at.asc()).options(selectinload(Ticket.user))
    unassigned_tickets_result = await session.execute(unassigned_tickets_query)
    unassigned_tickets = unassigned_tickets_result.scalars().all()

    if not unassigned_tickets:
        await callback_query.message.edit_text(
            "📨 <b>Неназначенные тикеты</b>\n\n"
            "В настоящее время нет неназначенных тикетов.",
            reply_markup=KeyboardFactory.back_button("mod:back_to_menu", user.language)
        )
        await callback_query.answer()
        return

    # Сохраняем тикеты в state для пагинации
    tickets_data = [
        {
            "id": ticket.id,
            "text": f"Тикет #{ticket.id} - {ticket.user.full_name if ticket.user else 'Неизвестный пользователь'}",
            "subject": ticket.subject or "Без темы",
            "created_at": ticket.created_at.strftime("%d.%m.%Y %H:%M"),
            "user_name": ticket.user.full_name if ticket.user else "Неизвестный пользователь",
            "user_id": ticket.user.id if ticket.user else None
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

    page_info = paginator.get_page_info(0)
    message_text += _("page_info", user.language,
                      current_page=page_info["current_page"],
                      total_pages=page_info["total_pages"])

    # Создаем клавиатуру с тикетами и кнопками действий
    kb_items = []
    for item in page_items:
        kb_items.append({
            "id": f"take:{item['id']}",
            "text": f"Принять тикет #{item['id']}"
        })

    # Отправляем сообщение с клавиатурой
    await callback_query.message.edit_text(
        message_text,
        reply_markup=KeyboardFactory.paginated_list(
            kb_items,
            0,
            action_prefix="mod",
            back_callback="mod:back_to_menu",
            language=user.language
        )
    )

    await state.set_state(ModeratorStates.VIEWING_TICKETS)
    await callback_query.answer()

    logger.info(f"Moderator {user_id} viewed unassigned tickets")


@router.callback_query(F.data.startswith("mod:take:"))
async def take_ticket_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика принятия тикета в работу
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик take_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик take_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_take_ticket(callback_query, bot, session, state)


async def _process_take_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика принятия тикета в работу
    """
    user_id = callback_query.from_user.id
    ticket_id = int(callback_query.data.split(":")[2])

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            _("error_access_denied", moderator.language if moderator else None)
        )
        await callback_query.answer()
        return

    # Проверяем, есть ли у модератора активный тикет
    active_mod_ticket_query = select(Ticket).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    active_mod_ticket_result = await session.execute(active_mod_ticket_query)
    active_mod_ticket = active_mod_ticket_result.scalar_one_or_none()

    if active_mod_ticket:
        await callback_query.message.edit_text(
            f"⚠️ У вас уже есть активный тикет #{active_mod_ticket.id}.\n\n"
            f"Модератор может работать только с одним тикетом одновременно. "
            f"Пожалуйста, завершите работу с текущим тикетом, прежде чем принимать новый.",
            reply_markup=KeyboardFactory.back_button("mod:back_to_menu", moderator.language)
        )
        await callback_query.answer()
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.status == TicketStatus.OPEN)
    ).options(selectinload(Ticket.user), selectinload(Ticket.messages))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            _("error_ticket_not_found", moderator.language, ticket_id=ticket_id) + " " +
            "Возможно, тикет уже был взят другим модератором.",
            reply_markup=KeyboardFactory.back_button("mod:back_to_menu", moderator.language)
        )
        await callback_query.answer()
        return

    # Обновляем тикет: назначаем модератора и меняем статус
    ticket.moderator_id = moderator.id
    ticket.status = TicketStatus.IN_PROGRESS
    ticket.updated_at = datetime.now()

    # Добавляем системное сообщение о принятии тикета
    system_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=moderator.id,
        message_type=MessageType.SYSTEM,
        text=_("moderator_took_ticket", None, moderator_name=moderator.full_name)
    )
    session.add(system_message)

    await session.commit()

    # Отправляем информацию о тикете
    message_text = (
        f"🔄 <b>Тикет #{ticket.id} принят в работу</b>\n\n"
        f"👤 Пользователь: {ticket.user.full_name}\n"
        f"📝 Тема: {ticket.subject or 'Не указана'}\n"
        f"📅 Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    )

    # Создаем клавиатуру с действиями для тикета
    keyboard = KeyboardFactory.ticket_actions(TicketStatus.IN_PROGRESS, ticket.id, moderator.language)

    await callback_query.message.edit_text(
        message_text,
        reply_markup=keyboard
    )

    # Устанавливаем состояние работы с тикетом
    await state.set_state(ModeratorStates.WORKING_WITH_TICKET)
    await state.update_data(active_ticket_id=ticket.id)

    # Отправляем историю сообщений отдельными сообщениями
    if ticket.messages:
        await callback_query.message.answer(_("message_history", moderator.language))

        # Ограничиваем количество сообщений
        max_messages = 20
        start_idx = max(0, len(ticket.messages) - max_messages)

        # Если в тикете много сообщений, добавляем информацию об ограничении
        if len(ticket.messages) > max_messages:
            await callback_query.message.answer(
                f"<i>Показаны последние {max_messages} из {len(ticket.messages)} сообщений.</i>"
            )

        for msg in ticket.messages[start_idx:]:
            if msg.sender_id == ticket.user_id:
                sender = "Пользователь"
            elif msg.sender_id == moderator.id:
                sender = "Вы"
            else:
                sender = "Система"

            time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

            if msg.message_type == MessageType.SYSTEM:
                await callback_query.message.answer(f"🔔 <i>{msg.text}</i>")
            elif msg.message_type == MessageType.TEXT:
                await callback_query.message.answer(f"<b>{sender}</b> [{time}]:\n{msg.text}")
            elif msg.message_type == MessageType.PHOTO:
                caption = f"<b>{sender}</b> [{time}]:" + (f"\n{msg.text.replace('[ФОТО] ', '')}" if msg.text else "")
                await bot.send_photo(
                    chat_id=callback_query.from_user.id,
                    photo=msg.file_id,
                    caption=caption
                )
            elif msg.message_type == MessageType.VIDEO:
                caption = f"<b>{sender}</b> [{time}]:" + (f"\n{msg.text.replace('[ВИДЕО] ', '')}" if msg.text else "")
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

        await callback_query.message.answer(
            "<i>Чтобы ответить пользователю, просто отправьте сообщение в этот чат.</i>"
        )

    # Уведомляем пользователя о том, что его тикет принят в работу
    try:
        await bot.send_message(
            chat_id=ticket.user.telegram_id,
            text=f"🔔 <b>Ваш тикет #{ticket.id} принят в работу</b>\n\n"
                 f"Модератор {moderator.full_name} начал работу с вашим запросом.\n"
                 f"Вы можете продолжить общение через бота.",
        )
    except Exception as e:
        logger.error(f"Failed to send notification to user {ticket.user.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Moderator {user_id} took ticket #{ticket.id}")


@router.callback_query(F.data.startswith("mod:resolve_ticket:"))
async def resolve_ticket_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика отметки тикета как решенного
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик resolve_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_resolve_ticket(callback_query, session, state)


async def _process_resolve_ticket(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика отметки тикета как решенного
    """
    user_id = callback_query.from_user.id
    ticket_id = int(callback_query.data.split(":")[2])

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            _("error_access_denied", moderator.language if moderator else None)
        )
        await callback_query.answer()
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            _("error_ticket_not_found", moderator.language, ticket_id=ticket_id) + " " +
            "или он не находится в работе у вас.",
            reply_markup=KeyboardFactory.back_button("mod:back_to_menu", moderator.language)
        )
        await callback_query.answer()
        return

    # Подтверждение действия
    await callback_query.message.edit_text(
        _("confirm_prompt", moderator.language, action="отметить тикет как решенный") + "\n\n" +
        f"После этого пользователю будет предложено оценить вашу работу и закрыть тикет.",
        reply_markup=KeyboardFactory.confirmation_keyboard(f"resolve:{ticket.id}", moderator.language)
    )

    await callback_query.answer()


@router.callback_query(F.data.startswith("confirm:resolve:"))
async def confirm_resolve_ticket_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика подтверждения отметки тикета как решенного
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик confirm_resolve_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик confirm_resolve_ticket!")
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_confirm_resolve_ticket(callback_query, bot, session, state)


async def _process_confirm_resolve_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession,
                                          state: FSMContext):
    """
    Реализация обработчика подтверждения отметки тикета как решенного
    """
    user_id = callback_query.from_user.id
    ticket_id = int(callback_query.data.split(":")[2])

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            _("error_access_denied", moderator.language if moderator else None)
        )
        await callback_query.answer()
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            _("error_ticket_not_found", moderator.language, ticket_id=ticket_id) + " " +
            "или он не находится в работе у вас.",
            reply_markup=KeyboardFactory.back_button("mod:back_to_menu", moderator.language)
        )
        await callback_query.answer()
        return

    # Обновляем тикет: меняем статус
    ticket.status = TicketStatus.RESOLVED
    ticket.updated_at = datetime.now()

    # Добавляем системное сообщение о решении тикета
    system_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=moderator.id,
        message_type=MessageType.SYSTEM,
        text=_("moderator_resolved_ticket", None, moderator_name=moderator.full_name)
    )
    session.add(system_message)

    await session.commit()

    # Отправляем подтверждение модератору
    await callback_query.message.edit_text(
        f"✅ <b>Тикет #{ticket.id} отмечен как решенный</b>\n\n"
        f"Пользователю было отправлено уведомление с предложением "
        f"оценить вашу работу и закрыть тикет.",
        reply_markup=KeyboardFactory.main_menu(UserRole.MODERATOR, moderator.language)
    )

    # Сбрасываем состояние
    await state.set_state(ModeratorStates.MAIN_MENU)
    await state.clear()

    # Уведомляем пользователя о решении тикета
    try:
        user_language = ticket.user.language if ticket.user else "ru"
        await bot.send_message(
            chat_id=ticket.user.telegram_id,
            text=f"🔔 <b>Ваш тикет #{ticket.id} отмечен как решенный</b>\n\n"
                 f"Модератор {moderator.full_name} отметил ваш запрос как решенный.\n"
                 f"Пожалуйста, оцените качество обслуживания и закройте тикет.",
            reply_markup=KeyboardFactory.rating_keyboard(user_language)
        )
    except Exception as e:
        logger.error(f"Failed to send notification to user {ticket.user.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Moderator {user_id} marked ticket #{ticket.id} as resolved")


@router.callback_query(F.data == "mod:my_stats")
async def my_stats_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика просмотра статистики модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик my_stats!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_my_stats(callback_query, session, state)


async def _process_my_stats(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика просмотра статистики модератора
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            _("error_access_denied", moderator.language if moderator else None)
        )
        await callback_query.answer()
        return

    # Получаем статистику по закрытым тикетам
    closed_tickets_query = select(func.count(Ticket.id), func.avg(Ticket.rating)).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.CLOSED)
    )
    closed_tickets_result = await session.execute(closed_tickets_query)
    closed_count, avg_rating = closed_tickets_result.one()

    # Получаем статистику по тикетам в работе
    in_progress_tickets_query = select(func.count(Ticket.id)).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    in_progress_result = await session.execute(in_progress_tickets_query)
    in_progress_count = in_progress_result.scalar()

    # Получаем статистику по решенным тикетам, ожидающим оценки
    resolved_tickets_query = select(func.count(Ticket.id)).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.RESOLVED)
    )
    resolved_result = await session.execute(resolved_tickets_query)
    resolved_count = resolved_result.scalar()

    # Получаем статистику по всем тикетам
    all_tickets_query = select(func.count(Ticket.id)).where(
        Ticket.moderator_id == moderator.id
    )
    all_tickets_result = await session.execute(all_tickets_query)
    all_tickets_count = all_tickets_result.scalar()

    # Форматируем средний рейтинг
    avg_rating_text = f"{avg_rating:.2f}" if avg_rating else "Нет оценок"
    avg_rating_stars = "⭐" * round(avg_rating) if avg_rating else "Нет оценок"

    # Формируем сообщение со статистикой
    message_text = (
        f"📊 <b>Статистика модератора {moderator.full_name}</b>\n\n"
        f"<b>Обработано тикетов:</b> {all_tickets_count}\n"
        f"<b>Закрыто тикетов:</b> {closed_count}\n"
        f"<b>Тикетов в работе:</b> {in_progress_count}\n"
        f"<b>Решенных тикетов (ожидают оценки):</b> {resolved_count}\n\n"
        f"<b>Средний рейтинг:</b> {avg_rating_text} {avg_rating_stars}\n"
    )

    # Получаем последние 5 закрытых тикетов
    recent_tickets_query = select(Ticket).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.CLOSED)
    ).order_by(Ticket.closed_at.desc()).limit(5).options(selectinload(Ticket.user))
    recent_tickets_result = await session.execute(recent_tickets_query)
    recent_tickets = recent_tickets_result.scalars().all()

    if recent_tickets:
        message_text += "\n<b>Последние закрытые тикеты:</b>\n"
        for ticket in recent_tickets:
            rating_stars = "⭐" * int(ticket.rating) if ticket.rating else "Без оценки"
            message_text += (
                f"🔹 <b>Тикет #{ticket.id}</b> - {rating_stars}\n"
                f"👤 Пользователь: {ticket.user.full_name if ticket.user else 'Неизвестный'}\n"
                f"📅 Закрыт: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )

    await callback_query.message.edit_text(
        message_text,
        reply_markup=KeyboardFactory.back_button("mod:back_to_menu", moderator.language)
    )

    await state.set_state(ModeratorStates.VIEWING_STATISTICS)
    await callback_query.answer()

    logger.info(f"Moderator {user_id} viewed their stats")


@router.message(ModeratorStates.WORKING_WITH_TICKET, F.text | F.photo | F.document | F.video)
async def process_moderator_message_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика сообщения модератора в активном тикете
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_moderator_message!")
        await message.answer(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик process_moderator_message!")
        await message.answer(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        return

    return await _process_moderator_message(message, bot, session, state)


async def _process_moderator_message(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика сообщения модератора в активном тикете
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

    # Получаем модератора из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await message.answer(
            f"Тикет #{ticket_id} не найден или не находится в работе у вас.",
            reply_markup=KeyboardFactory.main_menu(UserRole.MODERATOR, moderator.language)
        )
        await state.set_state(ModeratorStates.MAIN_MENU)
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
        sender_id=moderator.id,
        message_type=message_type,
        text=text,
        file_id=file_id
    )
    session.add(ticket_message)

    # Обновляем время последнего обновления тикета
    ticket.updated_at = datetime.now()

    await session.commit()

    # Отправляем подтверждение модератору
    await message.answer(_("moderator_message_sent", moderator.language))

    # Отправляем сообщение пользователю
    try:
        user_language = ticket.user.language if ticket.user else "ru"

        # Отправляем в зависимости от типа сообщения
        if message_type == MessageType.TEXT:
            await bot.send_message(
                chat_id=ticket.user.telegram_id,
                text=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                     f"От: Модератор {moderator.full_name}\n\n"
                     f"{text}"
            )
        elif message_type == MessageType.PHOTO:
            await bot.send_photo(
                chat_id=ticket.user.telegram_id,
                photo=file_id,
                caption=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                        f"От: Модератор {moderator.full_name}\n\n"
                        f"{message.caption or ''}"
            )
        elif message_type == MessageType.DOCUMENT:
            await bot.send_document(
                chat_id=ticket.user.telegram_id,
                document=file_id,
                caption=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                        f"От: Модератор {moderator.full_name}\n\n"
                        f"{message.caption or ''}"
            )
        elif message_type == MessageType.VIDEO:
            await bot.send_video(
                chat_id=ticket.user.telegram_id,
                video=file_id,
                caption=f"📨 <b>Новое сообщение в тикете #{ticket.id}</b>\n\n"
                        f"От: Модератор {moderator.full_name}\n\n"
                        f"{message.caption or ''}"
            )
    except Exception as e:
        logger.error(f"Failed to send message to user {ticket.user.telegram_id}: {e}")
        await message.answer(
            "⚠️ Не удалось доставить сообщение пользователю. "
            "Но оно сохранено в истории тикета."
        )

    logger.info(f"Moderator {user_id} sent message to ticket #{ticket.id}")


@router.callback_query(F.data == "mod:back_to_menu")
async def back_to_menu_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика возврата в главное меню модератора
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
    Реализация обработчика возврата в главное меню модератора
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    language = moderator.language if moderator else "ru"

    await callback_query.message.edit_text(
        _("moderator_main_menu", language),
        reply_markup=KeyboardFactory.main_menu(UserRole.MODERATOR, language)
    )

    await state.set_state(ModeratorStates.MAIN_MENU)
    await state.clear()
    await callback_query.answer()

    logger.info(f"Moderator {user_id} returned to main menu")


@router.callback_query(F.data == "mod:user_menu")
async def switch_to_user_menu_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика переключения на меню пользователя
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик switch_to_user_menu!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_switch_to_user_menu(callback_query, session, state)


async def _process_switch_to_user_menu(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика переключения на меню пользователя
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    language = user.language if user else "ru"

    await callback_query.message.edit_text(
        _("user_main_menu", language),
        reply_markup=KeyboardFactory.main_menu(UserRole.USER, language)
    )

    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"Moderator {user_id} switched to user menu")


def register_handlers(dp: Dispatcher):
    """
    Регистрирует все обработчики данного модуля.

    Args:
        dp: Диспетчер
    """
    dp.include_router(router)


@router.message(F.text == "📝 Активный тикет")
async def mod_active_ticket_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Активный тикет" для модератора
    """
    # Получаем сессию и проверяем, что пользователь - модератор
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик mod_active_ticket_button!")
        await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
        return

    user_id = message.from_user.id
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await message.answer(_("error_access_denied", user.language if user else None))
        return

    # Здесь обработка текущего активного тикета модератора
    active_ticket_query = select(Ticket).where(
        (Ticket.moderator_id == user.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user), selectinload(Ticket.messages))
    active_ticket_result = await session.execute(active_ticket_query)
    ticket = active_ticket_result.scalar_one_or_none()

    if not ticket:
        await message.answer(
            "У вас нет активных тикетов в работе. Вы можете взять тикет из списка неназначенных.",
            reply_markup=KeyboardFactory.main_reply_keyboard(UserRole.MODERATOR, user.language)
        )
        return

    # Если есть активный тикет, показываем информацию о нем
    message_text = (
        f"🔄 <b>Тикет #{ticket.id} в работе</b>\n\n"
        f"👤 Пользователь: {ticket.user.full_name}\n"
        f"📝 Тема: {ticket.subject or 'Не указана'}\n"
        f"📅 Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    )

    # Создаем клавиатуру с действиями для тикета
    keyboard = KeyboardFactory.ticket_actions(TicketStatus.IN_PROGRESS, ticket.id, user.language)

    await message.answer(message_text, reply_markup=keyboard)

    # Устанавливаем состояние работы с тикетом
    await state.set_state(ModeratorStates.WORKING_WITH_TICKET)
    await state.update_data(active_ticket_id=ticket.id)

    # Получаем бота из kwargs для отправки истории сообщений
    bot = kwargs.get("bot")
    if not bot:
        await message.answer("Произошла ошибка при получении истории сообщений.")
        return

    # Отправляем историю сообщений отдельными сообщениями
    if ticket.messages:
        await message.answer(_("message_history", user.language))

        # Ограничиваем количество сообщений
        max_messages = 20
        start_idx = max(0, len(ticket.messages) - max_messages)

        # Если в тикете много сообщений, добавляем информацию об ограничении
        if len(ticket.messages) > max_messages:
            await message.answer(
                f"<i>Показаны последние {max_messages} из {len(ticket.messages)} сообщений.</i>"
            )

        for msg in ticket.messages[start_idx:]:
            if msg.sender_id == ticket.user_id:
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

    logger.info(f"Moderator {user_id} viewed active ticket #{ticket.id}")


@router.message(F.text == "📨 Неназначенные тикеты")
async def unassigned_tickets_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Неназначенные тикеты" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик unassigned_tickets_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_unassigned_tickets_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_unassigned_tickets_button(message, session, state)


async def _process_unassigned_tickets_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Неназначенные тикеты" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await message.answer(
            _("error_access_denied", user.language if user else None)
        )
        return

    # Симулируем нажатие на Inline кнопку для неназначенных тикетов
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "mod:unassigned_tickets"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Здесь создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "Неназначенные тикеты"
    await unassigned_tickets_wrapper(fake_callback, state, session=session)

    logger.info(f"Moderator {user_id} used Reply button 'Unassigned Tickets'")


@router.message(F.text == "📊 Моя статистика")
async def my_stats_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Моя статистика" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик my_stats_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_my_stats_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_my_stats_button(message, session, state)


async def _process_my_stats_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Моя статистика" на Reply Keyboard
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await message.answer(
            _("error_access_denied", user.language if user else None)
        )
        return

    # Симулируем нажатие на Inline кнопку для статистики модератора
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "mod:my_stats"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Здесь создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "Моя статистика"
    await my_stats_wrapper(fake_callback, state, session=session)

    logger.info(f"Moderator {user_id} used Reply button 'My Statistics'")
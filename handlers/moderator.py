import logging
from typing import Union, Dict, List, Any
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from models import User, Ticket, Message as TicketMessage, TicketStatus, MessageType, UserRole
from utils import (
    build_moderator_main_menu,
    build_user_main_menu,
    build_tickets_list_keyboard,
    build_back_keyboard,
    build_confirm_keyboard,
    ModeratorStates,
    UserStates,
    Paginator,
    TICKET_STATUS_EMOJI,
    RATING_EMOJI
)

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.callback_query(F.data == "mod:unassigned_tickets")
async def unassigned_tickets(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик просмотра неназначенных тикетов
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user or user.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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
            reply_markup=build_back_keyboard("mod:back_to_menu")
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
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
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

    await callback_query.message.edit_text(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(ModeratorStates.VIEWING_TICKETS)
    await callback_query.answer()


@router.callback_query(F.data.startswith("mod:take_ticket:"))
async def take_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик принятия тикета в работу
    """
    user_id = callback_query.from_user.id
    ticket_id = int(callback_query.data.split(":")[2])

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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
            reply_markup=build_back_keyboard("mod:back_to_menu")
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
            f"Тикет #{ticket_id} не найден или уже взят другим модератором.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Обновляем тикет: назначаем модератора и меняем статус
    ticket.moderator_id = moderator.id
    ticket.status = TicketStatus.IN_PROGRESS
    ticket.updated_at = func.now()

    # Добавляем системное сообщение о принятии тикета
    system_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=moderator.id,
        message_type=MessageType.SYSTEM,
        text=f"Модератор {moderator.full_name} принял тикет в работу"
    )
    session.add(system_message)

    await session.commit()

    # Формируем сообщение с историей тикета
    message_text = (
        f"🔄 <b>Тикет #{ticket.id} принят в работу</b>\n\n"
        f"👤 Пользователь: {ticket.user.full_name}\n"
        f"📝 Тема: {ticket.subject or 'Не указана'}\n"
        f"📅 Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<b>История переписки:</b>\n\n"
    )

    for msg in ticket.messages:
        sender = "Пользователь" if msg.sender_id == ticket.user_id else "Модератор"
        time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

        if msg.message_type == MessageType.SYSTEM:
            message_text += f"🔔 <i>{msg.text}</i>\n\n"
        else:
            message_text += f"<b>{sender}</b> [{time}]:\n{msg.text}\n\n"

    message_text += (
        "<i>Чтобы ответить пользователю, просто отправьте сообщение в этот чат.</i>"
    )

    # Отправляем сообщение модератору
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="✅ Отметить как решённый", callback_data=f"mod:resolve_ticket:{ticket.id}"))
    kb.add(InlineKeyboardButton(text="🔄 Переназначить", callback_data=f"mod:reassign_ticket:{ticket.id}"))
    kb.add(InlineKeyboardButton(text="🔙 В меню", callback_data="mod:back_to_menu"))

    await callback_query.message.edit_text(
        message_text,
        reply_markup=kb.as_markup()
    )

    # Устанавливаем состояние работы с тикетом
    await state.set_state(ModeratorStates.WORKING_WITH_TICKET)
    await state.update_data(active_ticket_id=ticket.id)

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
async def resolve_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик отметки тикета как решенного
    """
    user_id = callback_query.from_user.id
    ticket_id = int(callback_query.data.split(":")[2])

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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
            f"Тикет #{ticket_id} не найден или не находится в работе у вас.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Подтверждение действия
    await callback_query.message.edit_text(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы уверены, что хотите отметить тикет #{ticket.id} как решенный?\n\n"
        f"После этого пользователю будет предложено оценить вашу работу и закрыть тикет.",
        reply_markup=build_confirm_keyboard(f"resolve:{ticket.id}")
    )

    await callback_query.answer()


@router.callback_query(F.data.startswith("confirm:resolve:"))
async def confirm_resolve_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик подтверждения отметки тикета как решенного
    """
    user_id = callback_query.from_user.id
    ticket_id = int(callback_query.data.split(":")[2])

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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
            f"Тикет #{ticket_id} не найден или не находится в работе у вас.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Обновляем тикет: меняем статус
    ticket.status = TicketStatus.RESOLVED
    ticket.updated_at = func.now()

    # Добавляем системное сообщение о решении тикета
    system_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=moderator.id,
        message_type=MessageType.SYSTEM,
        text=f"Модератор {moderator.full_name} отметил тикет как решенный"
    )
    session.add(system_message)

    await session.commit()

    # Отправляем подтверждение модератору
    await callback_query.message.edit_text(
        f"✅ <b>Тикет #{ticket.id} отмечен как решенный</b>\n\n"
        f"Пользователю было отправлено уведомление с предложением "
        f"оценить вашу работу и закрыть тикет.",
        reply_markup=build_moderator_main_menu()
    )

    # Сбрасываем состояние
    await state.set_state(ModeratorStates.MAIN_MENU)
    await state.clear_data()

    # Уведомляем пользователя о решении тикета
    try:
        await bot.send_message(
            chat_id=ticket.user.telegram_id,
            text=f"🔔 <b>Ваш тикет #{ticket.id} отмечен как решенный</b>\n\n"
                 f"Модератор {moderator.full_name} отметил ваш запрос как решенный.\n"
                 f"Пожалуйста, оцените качество обслуживания и закройте тикет.",
            reply_markup=build_rating_keyboard()
        )
    except Exception as e:
        logger.error(f"Failed to send notification to user {ticket.user.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Moderator {user_id} marked ticket #{ticket.id} as resolved")


@router.callback_query(F.data.startswith("mod:reassign_ticket"))
async def reassign_ticket_menu(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик меню переназначения тикета
    """
    user_id = callback_query.from_user.id

    # Если в callback_data есть id тикета, используем его
    if ":" in callback_query.data:
        ticket_id = int(callback_query.data.split(":")[2])
        await state.update_data(active_ticket_id=ticket_id)
    else:
        # Иначе берем id из состояния
        state_data = await state.get_data()
        ticket_id = state_data.get("active_ticket_id")

    if not ticket_id:
        await callback_query.message.edit_text(
            "Не удалось определить тикет для переназначения.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            f"Тикет #{ticket_id} не найден или не находится в работе у вас.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Получаем список свободных модераторов
    free_moderators_query = select(User).where(
        (User.role == UserRole.MODERATOR) &
        (User.id != moderator.id)
    )
    free_moderators_result = await session.execute(free_moderators_query)
    free_moderators = free_moderators_result.scalars().all()

    # Фильтруем модераторов, у которых уже есть активные тикеты
    busy_moderators_query = select(User.id).where(
        (User.role == UserRole.MODERATOR) &
        (User.id.in_([mod.id for mod in free_moderators])) &
        (User.id == Ticket.moderator_id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    )
    busy_moderators_result = await session.execute(busy_moderators_query)
    busy_moderators_ids = [row[0] for row in busy_moderators_result.all()]

    available_moderators = [mod for mod in free_moderators if mod.id not in busy_moderators_ids]

    if not available_moderators:
        await callback_query.message.edit_text(
            f"⚠️ Нет доступных модераторов для переназначения тикета.\n\n"
            f"Все модераторы либо заняты, либо недоступны.",
            reply_markup=build_back_keyboard("mod:back_to_ticket")
        )
        await callback_query.answer()
        return

    # Формируем клавиатуру с доступными модераторами
    kb = InlineKeyboardBuilder()
    for mod in available_moderators:
        kb.add(InlineKeyboardButton(
            text=f"{mod.full_name}",
            callback_data=f"mod:assign_to:{mod.id}:{ticket.id}"
        ))

    kb.add(InlineKeyboardButton(text="🔙 Назад", callback_data="mod:back_to_ticket"))

    await callback_query.message.edit_text(
        f"🔄 <b>Переназначение тикета #{ticket.id}</b>\n\n"
        f"Выберите модератора, которому вы хотите переназначить этот тикет:",
        reply_markup=kb.as_markup()
    )

    await state.set_state(ModeratorStates.REASSIGNING_TICKET)
    await callback_query.answer()


@router.callback_query(F.data.startswith("mod:assign_to:"))
async def assign_to_moderator(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик переназначения тикета другому модератору
    """
    user_id = callback_query.from_user.id
    parts = callback_query.data.split(":")
    new_moderator_id = int(parts[2])
    ticket_id = int(parts[3])

    # Получаем текущего модератора из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    current_moderator = result.scalar_one_or_none()

    if not current_moderator or current_moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем нового модератора из БД
    new_moderator_query = select(User).where(User.id == new_moderator_id)
    new_moderator_result = await session.execute(new_moderator_query)
    new_moderator = new_moderator_result.scalar_one_or_none()

    if not new_moderator or new_moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "Выбранный модератор не найден или не является модератором.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.moderator_id == current_moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user), selectinload(Ticket.messages))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            f"Тикет #{ticket_id} не найден или не находится в работе у вас.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Обновляем тикет: меняем модератора
    ticket.moderator_id = new_moderator.id
    ticket.updated_at = func.now()

    # Добавляем системное сообщение о переназначении тикета
    system_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=current_moderator.id,
        message_type=MessageType.SYSTEM,
        text=f"Тикет переназначен с модератора {current_moderator.full_name} на модератора {new_moderator.full_name}"
    )
    session.add(system_message)

    await session.commit()

    # Отправляем подтверждение текущему модератору
    await callback_query.message.edit_text(
        f"✅ <b>Тикет #{ticket.id} успешно переназначен</b>\n\n"
        f"Тикет был переназначен модератору {new_moderator.full_name}.",
        reply_markup=build_moderator_main_menu()
    )

    # Сбрасываем состояние
    await state.set_state(ModeratorStates.MAIN_MENU)
    await state.clear_data()

    # Отправляем уведомление новому модератору
    try:
        # Формируем сообщение с историей тикета
        message_text = (
            f"🔄 <b>Вам переназначен тикет #{ticket.id}</b>\n\n"
            f"👤 Пользователь: {ticket.user.full_name}\n"
            f"📝 Тема: {ticket.subject or 'Не указана'}\n"
            f"📅 Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"<b>История переписки:</b>\n\n"
        )

        for msg in ticket.messages:
            if msg.sender_id == ticket.user_id:
                sender = "Пользователь"
            elif msg.sender_id == current_moderator.id:
                sender = f"Модератор {current_moderator.full_name}"
            else:
                sender = "Система"

            time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

            if msg.message_type == MessageType.SYSTEM:
                message_text += f"🔔 <i>{msg.text}</i>\n\n"
            else:
                message_text += f"<b>{sender}</b> [{time}]:\n{msg.text}\n\n"

        message_text += (
            "<i>Чтобы ответить пользователю, просто отправьте сообщение в этот чат.</i>"
        )

        # Клавиатура для нового модератора
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="✅ Отметить как решённый", callback_data=f"mod:resolve_ticket:{ticket.id}"))
        kb.add(InlineKeyboardButton(text="🔄 Переназначить", callback_data=f"mod:reassign_ticket:{ticket.id}"))
        kb.add(InlineKeyboardButton(text="🔙 В меню", callback_data="mod:back_to_menu"))

        await bot.send_message(
            chat_id=new_moderator.telegram_id,
            text=message_text,
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logger.error(f"Failed to send notification to new moderator {new_moderator.telegram_id}: {e}")

    # Уведомляем пользователя о переназначении тикета
    try:
        await bot.send_message(
            chat_id=ticket.user.telegram_id,
            text=f"🔔 <b>Ваш тикет #{ticket.id} переназначен</b>\n\n"
                 f"Ваш запрос был переназначен модератору {new_moderator.full_name}.\n"
                 f"Продолжайте общение через бота как обычно."
        )
    except Exception as e:
        logger.error(f"Failed to send notification to user {ticket.user.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Moderator {user_id} reassigned ticket #{ticket.id} to moderator {new_moderator_id}")


@router.callback_query(F.data == "mod:my_stats")
async def my_stats(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик просмотра статистики модератора
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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
    avg_rating_stars = RATING_EMOJI.get(round(avg_rating)) if avg_rating else "Нет оценок"

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
            rating_text = RATING_EMOJI.get(int(ticket.rating)) if ticket.rating else "Без оценки"
            message_text += (
                f"🔹 <b>Тикет #{ticket.id}</b> - {rating_text}\n"
                f"👤 Пользователь: {ticket.user.full_name}\n"
                f"📅 Закрыт: {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )

    await callback_query.message.edit_text(
        message_text,
        reply_markup=build_back_keyboard("mod:back_to_menu")
    )

    await callback_query.answer()

    logger.info(f"Moderator {user_id} viewed their stats")


@router.message(ModeratorStates.WORKING_WITH_TICKET, F.text | F.photo | F.document | F.video)
async def process_moderator_message(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик сообщения модератора в активном тикете
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
            reply_markup=build_moderator_main_menu()
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
    ticket.updated_at = func.now()

    await session.commit()

    # Отправляем подтверждение модератору
    await message.answer("✅ Ваше сообщение отправлено пользователю.")

    # Отправляем сообщение пользователю
    try:
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
async def back_to_menu(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик возврата в главное меню модератора
    """
    await callback_query.message.edit_text(
        "🔑 <b>Меню модератора</b>\n\n"
        "Выберите действие из меню:",
        reply_markup=build_moderator_main_menu()
    )

    await state.set_state(ModeratorStates.MAIN_MENU)
    await state.clear_data()
    await callback_query.answer()


@router.callback_query(F.data == "mod:back_to_ticket")
async def back_to_ticket(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик возврата к активному тикету
    """
    user_id = callback_query.from_user.id

    # Получаем данные из состояния
    state_data = await state.get_data()
    ticket_id = state_data.get("active_ticket_id")

    if not ticket_id:
        await callback_query.message.edit_text(
            "Не удалось определить активный тикет.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Получаем модератора из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    moderator = result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status == TicketStatus.IN_PROGRESS)
    ).options(selectinload(Ticket.user), selectinload(Ticket.messages))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await callback_query.message.edit_text(
            f"Тикет #{ticket_id} не найден или не находится в работе у вас.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Формируем сообщение с историей тикета
    message_text = (
        f"🔄 <b>Тикет #{ticket.id}</b>\n\n"
        f"👤 Пользователь: {ticket.user.full_name}\n"
        f"📝 Тема: {ticket.subject or 'Не указана'}\n"
        f"📅 Создан: {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"<b>История переписки:</b>\n\n"
    )

    # Максимальное количество сообщений для отображения
    max_messages = 10
    start_idx = max(0, len(ticket.messages) - max_messages)

    for i, msg in enumerate(ticket.messages[start_idx:], start=start_idx + 1):
        if msg.sender_id == ticket.user_id:
            sender = "Пользователь"
        elif msg.sender_id == moderator.id:
            sender = "Вы"
        else:
            sender = "Система"

        time = msg.sent_at.strftime("%d.%m.%Y %H:%M")

        if msg.message_type == MessageType.SYSTEM:
            message_text += f"🔔 <i>{msg.text}</i>\n\n"
        else:
            message_text += f"<b>{sender}</b> [{time}]:\n{msg.text}\n\n"

    # Если в тикете много сообщений, добавляем информацию об ограничении
    if len(ticket.messages) > max_messages:
        message_text += f"<i>Показаны последние {max_messages} из {len(ticket.messages)} сообщений.</i>\n\n"

    message_text += (
        "<i>Чтобы ответить пользователю, просто отправьте сообщение в этот чат.</i>"
    )

    # Отправляем сообщение модератору
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="✅ Отметить как решённый", callback_data=f"mod:resolve_ticket:{ticket.id}"))
    kb.add(InlineKeyboardButton(text="🔄 Переназначить", callback_data=f"mod:reassign_ticket:{ticket.id}"))
    kb.add(InlineKeyboardButton(text="🔙 В меню", callback_data="mod:back_to_menu"))

    await callback_query.message.edit_text(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(ModeratorStates.WORKING_WITH_TICKET)
    await callback_query.answer()


@router.callback_query(F.data == "mod:user_menu")
async def switch_to_user_menu(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик переключения на меню пользователя
    """
    await callback_query.message.edit_text(
        "👤 <b>Меню пользователя</b>\n\n"
        "Выберите действие из меню:",
        reply_markup=build_user_main_menu()
    )

    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()


@router.callback_query(F.data.startswith("mod:page:"))
async def paginate_tickets(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик пагинации списка тикетов
    """
    user_id = callback_query.from_user.id
    new_page = int(callback_query.data.split(":")[2])

    # Получаем данные из состояния
    state_data = await state.get_data()
    tickets_data = state_data.get("tickets", [])

    if not tickets_data:
        await callback_query.message.edit_text(
            "Данные о тикетах отсутствуют.",
            reply_markup=build_back_keyboard("mod:back_to_menu")
        )
        await callback_query.answer()
        return

    # Формируем сообщение со списком тикетов
    paginator = Paginator(tickets_data, page_size=5)

    if new_page < 0 or new_page >= paginator.total_pages:
        await callback_query.answer("Страница не существует")
        return

    page_items = paginator.get_page(new_page)

    message_text = "📨 <b>Неназначенные тикеты</b>\n\n"
    for item in page_items:
        message_text += (
            f"🔹 <b>Тикет #{item['id']}</b>\n"
            f"👤 Пользователь: {item.get('user_name', 'Неизвестный')}\n"
            f"📝 {item.get('subject', 'Без темы')}\n"
            f"📅 Создан: {item.get('created_at', 'Неизвестно')}\n\n"
        )

    message_text += f"Страница {new_page + 1} из {paginator.total_pages}"

    # Создаем клавиатуру с навигацией
    kb = InlineKeyboardBuilder()

    for item in page_items:
        kb.add(InlineKeyboardButton(
            text=f"Принять тикет #{item['id']}",
            callback_data=f"mod:take_ticket:{item['id']}"
        ))

    # Добавляем навигационные кнопки
    row = []
    if paginator.has_prev(new_page):
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"mod:page:{new_page - 1}"))

    row.append(InlineKeyboardButton(text="🔙 Назад", callback_data="mod:back_to_menu"))

    if paginator.has_next(new_page):
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"mod:page:{new_page + 1}"))

    kb.row(*row)

    await callback_query.message.edit_text(
        message_text,
        reply_markup=kb.as_markup()
    )

    # Обновляем текущую страницу в состоянии
    await state.update_data(page=new_page)
    await callback_query.answer()
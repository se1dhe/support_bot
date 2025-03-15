import logging
from typing import Union, Dict, List, Any

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models import User, Ticket, Message as TicketMessage, TicketStatus, MessageType, UserRole
from utils import (
    build_user_main_menu,
    build_ticket_actions_keyboard,
    build_tickets_list_keyboard,
    build_back_keyboard,
    build_rating_keyboard,
    UserStates,
    Paginator,
    TICKET_STATUS_EMOJI,
    RATING_EMOJI, build_language_keyboard
)

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.callback_query(F.data == "user:create_ticket")
async def create_ticket(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик создания нового тикета
    """
    await callback_query.message.edit_text(
        "✏️ <b>Создание нового тикета</b>\n\n"
        "Пожалуйста, опишите вашу проблему в одном сообщении.\n"
        "Вы можете приложить изображение, видео или документ к вашему сообщению.\n\n"
        "<i>Отправьте сообщение с описанием проблемы:</i>",
        reply_markup=build_back_keyboard("user:back_to_menu")
    )

    # Устанавливаем состояние создания тикета
    await state.set_state(UserStates.CREATING_TICKET)
    await callback_query.answer()


@router.message(UserStates.CREATING_TICKET, F.text | F.photo | F.document | F.video)
async def process_ticket_creation(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик сообщения для создания тикета
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
        f"✅ Тикет #{new_ticket.id} успешно создан!\n\n"
        f"Ваш запрос был отправлен команде поддержки. "
        f"Пожалуйста, ожидайте ответа от модератора. "
        f"Вы получите уведомление, когда ваш тикет будет принят в работу.",
        reply_markup=build_user_main_menu()
    )

    # Возвращаем пользователя в главное меню
    await state.set_state(UserStates.MAIN_MENU)

    # Отправляем уведомления всем модераторам
    moderators_query = select(User).where(User.role == UserRole.MODERATOR)
    moderators_result = await session.execute(moderators_query)
    moderators = moderators_result.scalars().all()

    for moderator in moderators:
        # Создаем клавиатуру с кнопкой "Принять тикет"
        take_keyboard = InlineKeyboardBuilder()
        take_keyboard.add(InlineKeyboardButton(
            text="✅ Принять тикет",
            callback_data=f"mod:take_ticket:{new_ticket.id}"
        ))

        # Отправляем уведомление
        try:
            await bot.send_message(
                chat_id=moderator.telegram_id,
                text=f"📩 <b>Новый тикет #{new_ticket.id}</b>\n\n"
                     f"От: {user.full_name}\n"
                     f"Тема: {new_ticket.subject or 'Не указана'}\n\n"
                     f"Сообщение:\n{text}",
                reply_markup=take_keyboard.as_markup()
            )
        except Exception as e:
            logger.error(f"Failed to send notification to moderator {moderator.telegram_id}: {e}")

    logger.info(f"User {user_id} created ticket #{new_ticket.id}")


@router.callback_query(F.data == "user:ticket_history")
async def ticket_history(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик просмотра истории тикетов
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
            "📋 <b>История тикетов</b>\n\n"
            "У вас пока нет закрытых тикетов.",
            reply_markup=build_back_keyboard("user:back_to_menu")
        )
        await callback_query.answer()
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
    await callback_query.message.edit_text(
        message_text,
        reply_markup=build_tickets_list_keyboard(tickets_data, 0)
    )

    await state.set_state(UserStates.VIEWING_TICKET_HISTORY)
    await callback_query.answer()


@router.callback_query(F.data == "user:active_ticket")
async def active_ticket(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик просмотра активного тикета
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
            "📝 <b>Активный тикет</b>\n\n"
            "У вас нет активных тикетов. Вы можете создать новый тикет в главном меню.",
            reply_markup=build_back_keyboard("user:back_to_menu")
        )
        await callback_query.answer()
        return

    # Получаем сообщения тикета
    messages_query = select(TicketMessage).where(
        TicketMessage.ticket_id == ticket.id
    ).order_by(TicketMessage.sent_at.asc())
    messages_result = await session.execute(messages_query)
    messages = messages_result.scalars().all()

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
        await callback_query.message.edit_text(
            message_text,
            reply_markup=build_rating_keyboard()
        )
        await state.set_state(UserStates.RATING_MODERATOR)
        await state.update_data(active_ticket_id=ticket.id)

        # Отправляем историю сообщений
        if messages:
            await callback_query.message.answer("📜 <b>История сообщений:</b>")

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
                        f"\n{msg.text.replace('[ДОКУМЕНТ: ', '').split(']')[1] if ']' in msg.text else ""}" if msg.text else "")
                    await bot.send_document(
                        chat_id=callback_query.from_user.id,
                        document=msg.file_id,
                        caption=caption
                    )

            await callback_query.message.answer(
                "<i>Модератор отметил тикет как решенный. "
                "Пожалуйста, оцените работу модератора.</i>"
            )
        return
    else:
        # Для других статусов
        await callback_query.message.edit_text(
            message_text,
            reply_markup=build_back_keyboard("user:back_to_menu")
        )

        # Отправляем историю сообщений и инструкции в зависимости от статуса
        if messages:
            await callback_query.message.answer("📜 <b>История сообщений:</b>")

            max_messages = 20
            start_idx = max(0, len(messages) - max_messages)

            if len(messages) > max_messages:
                await callback_query.message.answer(
                    f"<i>Показаны последние {max_messages} из {len(messages)} сообщений.</i>"
                )

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
                        f"\n{msg.text.replace('[ДОКУМЕНТ: ', '').split(']')[1] if ']' in msg.text else ""}" if msg.text else "")
                    await bot.send_document(
                        chat_id=callback_query.from_user.id,
                        document=msg.file_id,
                        caption=caption
                    )

        if ticket.status == TicketStatus.IN_PROGRESS:
            await callback_query.message.answer(
                "<i>Чтобы ответить модератору, просто отправьте сообщение в этот чат.</i>"
            )
            await state.set_state(UserStates.SENDING_MESSAGE)
            await state.update_data(active_ticket_id=ticket.id)
        else:
            await callback_query.message.answer(
                "<i>Ожидайте, пока модератор примет ваш тикет в работу.</i>"
            )

    await callback_query.answer()


@router.message(UserStates.SENDING_MESSAGE, F.text | F.photo | F.document | F.video)
async def process_ticket_message(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик сообщения в активном тикете
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
            reply_markup=build_user_main_menu()
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
    ticket.updated_at = func.now()

    await session.commit()

    # Отправляем подтверждение пользователю
    await message.answer("✅ Ваше сообщение отправлено модератору.")

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
async def process_rating(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик выставления оценки модератору
    """
    user_id = callback_query.from_user.id
    rating = int(callback_query.data.split(":")[1])

    # Получаем данные из состояния
    state_data = await state.get_data()
    ticket_id = state_data.get("active_ticket_id")

    if not ticket_id:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, вернитесь в главное меню: /menu"
        )
        return

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    user = result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, перезапустите бота: /start"
        )
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(
        (Ticket.id == ticket_id) &
        (Ticket.user_id == user.id) &
        (Ticket.status == TicketStatus.RESOLVED)
    ).options(selectinload(Ticket.moderator))
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket or not ticket.moderator:
        await callback_query.message.edit_text(
            "Невозможно оценить тикет. Возможно, он уже был закрыт.",
            reply_markup=build_user_main_menu()
        )
        await state.set_state(UserStates.MAIN_MENU)
        return

    # Обновляем тикет: ставим оценку, меняем статус и добавляем время закрытия
    ticket.rating = rating
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = func.now()

    # Добавляем системное сообщение об оценке
    system_message = TicketMessage(
        ticket_id=ticket.id,
        sender_id=user.id,
        message_type=MessageType.SYSTEM,
        text=f"Пользователь оценил работу модератора на {RATING_EMOJI[rating]} ({rating}/5)"
    )
    session.add(system_message)

    await session.commit()

    # Отправляем подтверждение пользователю
    await callback_query.message.edit_text(
        f"🌟 <b>Спасибо за вашу оценку!</b>\n\n"
        f"Вы оценили работу модератора на {RATING_EMOJI[rating]} ({rating}/5).\n"
        f"Тикет #{ticket.id} закрыт.\n\n"
        f"Если у вас возникнут новые вопросы, вы можете создать новый тикет в главном меню.",
        reply_markup=build_user_main_menu()
    )

    # Уведомляем модератора об оценке
    try:
        await bot.send_message(
            chat_id=ticket.moderator.telegram_id,
            text=f"⭐ <b>Тикет #{ticket.id} закрыт</b>\n\n"
                 f"Пользователь {user.full_name} оценил вашу работу на "
                 f"{RATING_EMOJI[rating]} ({rating}/5).\n\n"
                 f"Спасибо за вашу работу!"
        )
    except Exception as e:
        logger.error(f"Failed to send rating notification to moderator {ticket.moderator.telegram_id}: {e}")

    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"User {user_id} rated ticket #{ticket.id} with {rating}/5")


@router.callback_query(F.data == "user:change_language")
async def change_language(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик изменения языка
    """
    await callback_query.message.edit_text(
        "🌐 <b>Выбор языка</b>\n\n"
        "Пожалуйста, выберите язык интерфейса:",
        reply_markup=build_language_keyboard()
    )

    await callback_query.answer()


@router.callback_query(F.data == "user:back_to_menu")
async def back_to_menu(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик возврата в главное меню
    """
    await callback_query.message.edit_text(
        "👤 <b>Главное меню</b>\n\n"
        "Выберите действие из меню:",
        reply_markup=build_user_main_menu()
    )

    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()
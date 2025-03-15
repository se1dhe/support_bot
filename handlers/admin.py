import logging
from typing import Union, Dict, List, Any
from datetime import datetime, timedelta

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select

from models import User, Ticket, Message as TicketMessage, TicketStatus, MessageType, UserRole
from utils import (
    build_admin_main_menu,
    build_moderator_main_menu,
    build_user_main_menu,
    build_back_keyboard,
    build_confirm_keyboard,
    AdminStates,
    ModeratorStates,
    UserStates,
    TICKET_STATUS_EMOJI
)

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик просмотра общей статистики
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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

    # Получаем статистику по тикетам за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    recent_tickets_query = select(
        func.count(Ticket.id).label("total_tickets")
    ).where(Ticket.created_at >= week_ago)
    recent_tickets_result = await session.execute(recent_tickets_query)
    recent_tickets_count = recent_tickets_result.scalar()

    # Получаем статистику по модераторам
    moderators_query = select(
        User,
        func.count(Ticket.id).filter(Ticket.status == TicketStatus.CLOSED).label("closed_count"),
        func.avg(Ticket.rating).filter(Ticket.status == TicketStatus.CLOSED).label("avg_rating")
    ).where(
        User.role == UserRole.MODERATOR
    ).outerjoin(
        Ticket, Ticket.moderator_id == User.id
    ).group_by(
        User.id
    ).order_by(
        desc("closed_count")
    ).limit(5)
    moderators_result = await session.execute(moderators_query)
    top_moderators = moderators_result.all()

    # Формируем сообщение со статистикой
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
        f"📅 Новых за последние 7 дней: {recent_tickets_count}\n"
        f"⭐ Средняя оценка: {tickets_stats.avg_rating:.2f if tickets_stats.avg_rating else 'Нет оценок'}/5.0\n\n"
    )

    if top_moderators:
        message_text += "<b>Топ модераторов:</b>\n"
        for i, (moderator, closed_count, avg_rating) in enumerate(top_moderators, 1):
            avg_rating_text = f"{avg_rating:.2f}/5.0" if avg_rating else "Нет оценок"
            message_text += (
                f"{i}. {moderator.full_name} - {closed_count} тикетов, "
                f"рейтинг: {avg_rating_text}\n"
            )

    await callback_query.message.edit_text(
        message_text,
        reply_markup=build_back_keyboard("admin:back_to_menu")
    )

    await state.set_state(AdminStates.VIEWING_STATISTICS)
    await callback_query.answer()

    logger.info(f"Admin {user_id} viewed general statistics")


@router.callback_query(F.data == "admin:manage_mods")
async def manage_moderators(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик управления модераторами
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
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

    await callback_query.message.edit_text(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(AdminStates.MANAGING_MODERATORS)
    await callback_query.answer()


@router.callback_query(F.data == "admin:add_moderator")
async def add_moderator_start(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик начала процесса добавления модератора
    """
    await callback_query.message.edit_text(
        "➕ <b>Добавление нового модератора</b>\n\n"
        "Пожалуйста, отправьте Telegram ID пользователя, "
        "которого вы хотите назначить модератором.\n\n"
        "<i>Пользователь должен быть зарегистрирован в боте.</i>",
        reply_markup=build_back_keyboard("admin:back_to_manage_mods")
    )

    await state.set_state(AdminStates.ADDING_MODERATOR)
    await callback_query.answer()


@router.message(AdminStates.ADDING_MODERATOR, F.text)
async def process_add_moderator(message: Message, session: AsyncSession, state: FSMContext):
    """
    Обработчик добавления модератора
    """
    admin_id = message.from_user.id

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await message.answer("У вас нет доступа к этой функции.")
        return

    # Проверяем, что введенный текст - число
    try:
        new_moderator_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Некорректный ввод. Пожалуйста, введите числовой ID пользователя.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        return

    # Получаем пользователя из БД
    user_query = select(User).where(User.telegram_id == new_moderator_id)
    user_result = await session.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        await message.answer(
            f"❌ Пользователь с ID {new_moderator_id} не найден в базе данных.\n\n"
            f"Пользователь должен быть зарегистрирован в боте (выполнить команду /start).",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        return

    if user.role == UserRole.ADMIN:
        await message.answer(
            f"❌ Пользователь {user.full_name} уже является администратором.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        return

    if user.role == UserRole.MODERATOR:
        await message.answer(
            f"❌ Пользователь {user.full_name} уже является модератором.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        return

    # Подтверждение действия
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text="✅ Да", callback_data=f"admin:confirm_add_mod:{new_moderator_id}"))
    kb.add(InlineKeyboardButton(text="❌ Нет", callback_data="admin:back_to_manage_mods"))

    await message.answer(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы действительно хотите назначить пользователя {user.full_name} "
        f"(ID: {user.telegram_id}) модератором?",
        reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.startswith("admin:confirm_add_mod:"))
async def confirm_add_moderator(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик подтверждения добавления модератора
    """
    admin_id = callback_query.from_user.id
    new_moderator_id = int(callback_query.data.split(":")[2])

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем пользователя из БД
    user_query = select(User).where(User.telegram_id == new_moderator_id)
    user_result = await session.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            f"Пользователь с ID {new_moderator_id} не найден в базе данных.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        await callback_query.answer()
        return

    # Назначаем пользователя модератором
    user.role = UserRole.MODERATOR
    await session.commit()

    await callback_query.message.edit_text(
        f"✅ Пользователь {user.full_name} (ID: {user.telegram_id}) "
        f"успешно назначен модератором.",
        reply_markup=build_back_keyboard("admin:back_to_manage_mods")
    )

    # Уведомляем нового модератора
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=f"🎉 <b>Поздравляем!</b>\n\n"
                 f"Вы были назначены модератором системы поддержки.\n"
                 f"Теперь вы можете принимать тикеты и помогать пользователям.\n\n"
                 f"Используйте команду /menu, чтобы открыть меню модератора."
        )
    except Exception as e:
        logger.error(f"Failed to send notification to new moderator {user.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Admin {admin_id} added new moderator {new_moderator_id}")


@router.callback_query(F.data == "admin:remove_moderator")
async def remove_moderator_start(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик начала процесса удаления модератора
    """
    user_id = callback_query.from_user.id

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == user_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем список модераторов
    moderators_query = select(User).where(User.role == UserRole.MODERATOR)
    moderators_result = await session.execute(moderators_query)
    moderators = moderators_result.scalars().all()

    if not moderators:
        await callback_query.message.edit_text(
            "В настоящее время нет назначенных модераторов.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        await callback_query.answer()
        return

    # Формируем сообщение со списком модераторов
    message_text = "❌ <b>Удаление модератора</b>\n\n"
    message_text += "Выберите модератора, которого вы хотите удалить:\n\n"

    # Создаем клавиатуру со списком модераторов
    kb = InlineKeyboardBuilder()

    for mod in moderators:
        kb.add(InlineKeyboardButton(
            text=f"{mod.full_name} (ID: {mod.telegram_id})",
            callback_data=f"admin:confirm_remove_mod:{mod.telegram_id}"
        ))

    kb.add(InlineKeyboardButton(text="🔙 Назад", callback_data="admin:back_to_manage_mods"))

    # Размещаем кнопки в один столбец
    kb.adjust(1)

    await callback_query.message.edit_text(
        message_text,
        reply_markup=kb.as_markup()
    )

    await state.set_state(AdminStates.REMOVING_MODERATOR)
    await callback_query.answer()


@router.callback_query(F.data.startswith("admin:confirm_remove_mod:"))
async def confirm_remove_moderator(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик подтверждения удаления модератора
    """
    admin_id = callback_query.from_user.id
    moderator_id = int(callback_query.data.split(":")[2])

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем модератора из БД
    mod_query = select(User).where(User.telegram_id == moderator_id)
    mod_result = await session.execute(mod_query)
    moderator = mod_result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            f"Модератор с ID {moderator_id} не найден.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        await callback_query.answer()
        return

    # Проверяем, есть ли у модератора активные тикеты
    active_tickets_query = select(func.count(Ticket.id)).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status.in_([TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]))
    )
    active_tickets_result = await session.execute(active_tickets_query)
    active_tickets_count = active_tickets_result.scalar()

    if active_tickets_count > 0:
        # Модератор имеет активные тикеты, нужно подтверждение
        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(
            text="✅ Да, удалить и переназначить тикеты",
            callback_data=f"admin:force_remove_mod:{moderator_id}"
        ))
        kb.add(InlineKeyboardButton(text="❌ Отмена", callback_data="admin:back_to_manage_mods"))

        await callback_query.message.edit_text(
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Модератор {moderator.full_name} имеет {active_tickets_count} активных тикетов.\n\n"
            f"Если вы продолжите, все активные тикеты будут возвращены в очередь неназначенных тикетов.\n\n"
            f"Вы уверены, что хотите удалить этого модератора?",
            reply_markup=kb.as_markup()
        )
        await callback_query.answer()
        return

    # Разжалуем модератора до обычного пользователя
    moderator.role = UserRole.USER
    await session.commit()

    await callback_query.message.edit_text(
        f"✅ Модератор {moderator.full_name} (ID: {moderator.telegram_id}) "
        f"успешно удален из списка модераторов.",
        reply_markup=build_back_keyboard("admin:back_to_manage_mods")
    )

    # Уведомляем бывшего модератора
    try:
        await bot.send_message(
            chat_id=moderator.telegram_id,
            text=f"ℹ️ <b>Уведомление</b>\n\n"
                 f"Ваши права модератора системы поддержки были отозваны администратором.\n\n"
                 f"Вы можете продолжать использовать бота как обычный пользователь."
        )
    except Exception as e:
        logger.error(f"Failed to send notification to former moderator {moderator.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Admin {admin_id} removed moderator {moderator_id}")


@router.callback_query(F.data.startswith("admin:force_remove_mod:"))
async def force_remove_moderator(callback_query: CallbackQuery, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Обработчик принудительного удаления модератора с активными тикетами
    """
    admin_id = callback_query.from_user.id
    moderator_id = int(callback_query.data.split(":")[2])

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            "У вас нет доступа к этой функции."
        )
        return

    # Получаем модератора из БД
    mod_query = select(User).where(User.telegram_id == moderator_id)
    mod_result = await session.execute(mod_query)
    moderator = mod_result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            f"Модератор с ID {moderator_id} не найден.",
            reply_markup=build_back_keyboard("admin:back_to_manage_mods")
        )
        await callback_query.answer()
        return

    # Получаем активные тикеты модератора
    active_tickets_query = select(Ticket).where(
        (Ticket.moderator_id == moderator.id) &
        (Ticket.status.in_([TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED]))
    ).options(selectinload(Ticket.user))
    active_tickets_result = await session.execute(active_tickets_query)
    active_tickets = active_tickets_result.scalars().all()

    # Освобождаем тикеты модератора
    for ticket in active_tickets:
        # Сбрасываем статус тикета и информацию о модераторе
        ticket.status = TicketStatus.OPEN
        ticket.moderator_id = None

        # Добавляем системное сообщение о переназначении
        system_message = TicketMessage(
            ticket_id=ticket.id,
            sender_id=admin.id,
            message_type=MessageType.SYSTEM,
            text=f"Тикет возвращен в очередь из-за удаления модератора {moderator.full_name}"
        )
        session.add(system_message)

        # Уведомляем пользователя
        try:
            await bot.send_message(
                chat_id=ticket.user.telegram_id,
                text=f"ℹ️ <b>Уведомление по тикету #{ticket.id}</b>\n\n"
                     f"Ваш тикет был возвращен в общую очередь из-за изменений в команде модераторов.\n"
                     f"Пожалуйста, ожидайте, когда другой модератор примет ваш тикет в работу."
            )
        except Exception as e:
            logger.error(f"Failed to send notification to user {ticket.user.telegram_id}: {e}")

    # Разжалуем модератора до обычного пользователя
    moderator.role = UserRole.USER
    await session.commit()

    await callback_query.message.edit_text(
        f"✅ Модератор {moderator.full_name} (ID: {moderator.telegram_id}) "
        f"успешно удален из списка модераторов.\n\n"
        f"Все активные тикеты ({len(active_tickets)}) были возвращены в общую очередь.",
        reply_markup=build_back_keyboard("admin:back_to_manage_mods")
    )

    # Уведомляем бывшего модератора
    try:
        await bot.send_message(
            chat_id=moderator.telegram_id,
            text=f"ℹ️ <b>Уведомление</b>\n\n"
                 f"Ваши права модератора системы поддержки были отозваны администратором.\n\n"
                 f"Все ваши активные тикеты были возвращены в общую очередь.\n"
                 f"Вы можете продолжать использовать бота как обычный пользователь."
        )
    except Exception as e:
        logger.error(f"Failed to send notification to former moderator {moderator.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Admin {admin_id} force removed moderator {moderator_id} with active tickets")


@router.callback_query(F.data == "admin:back_to_menu")
async def back_to_menu(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик возврата в главное меню администратора
    """
    await callback_query.message.edit_text(
        "👑 <b>Меню администратора</b>\n\n"
        "Выберите действие из меню:",
        reply_markup=build_admin_main_menu()
    )

    await state.set_state(AdminStates.MAIN_MENU)
    await callback_query.answer()


@router.callback_query(F.data == "admin:back_to_manage_mods")
async def back_to_manage_mods(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Обработчик возврата в меню управления модераторами
    """
    await state.set_state(AdminStates.MANAGING_MODERATORS)
    await manage_moderators(callback_query, session, state)


@router.callback_query(F.data == "admin:mod_menu")
async def switch_to_mod_menu(callback_query: CallbackQuery, state: FSMContext):
    """
    Обработчик переключения на меню модератора
    """
    await callback_query.message.edit_text(
        "🔑 <b>Меню модератора</b>\n\n"
        "Выберите действие из меню:",
        reply_markup=build_moderator_main_menu()
    )

    await state.set_state(ModeratorStates.MAIN_MENU)
    await callback_query.answer()


@router.callback_query(F.data == "admin:user_menu")
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
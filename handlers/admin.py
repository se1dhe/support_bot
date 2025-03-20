import logging
from typing import Union, Dict, List, Any, Optional
from datetime import datetime, timedelta

from aiogram import Router, F, Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, update
from sqlalchemy.orm import selectinload

from models import User, Ticket, Message as TicketMessage, TicketStatus, MessageType, UserRole
from utils.i18n import _
from utils.keyboards import KeyboardFactory
from utils.states import AdminStates, ModeratorStates, UserStates

# Инициализация логгера
logger = logging.getLogger(__name__)

# Создание роутера
router = Router()


@router.callback_query(F.data == "admin:stats")
async def admin_stats_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика просмотра общей статистики
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик admin_stats!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_admin_stats(callback_query, session, state)


async def _process_admin_stats(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика просмотра общей статистики
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
        return

    # Получаем статистику по пользователям - исправленный запрос
    users_query = select(User.role, func.count(User.id).label("count")).group_by(User.role)
    users_result = await session.execute(users_query)
    users_counts = {role: count for role, count in users_result}

    # Получаем количество пользователей по ролям
    users_count = users_counts.get(UserRole.USER, 0)
    moderators_count = users_counts.get(UserRole.MODERATOR, 0)
    admins_count = users_counts.get(UserRole.ADMIN, 0)

    # Получаем общее количество тикетов
    total_tickets_query = select(func.count(Ticket.id))
    total_tickets_result = await session.execute(total_tickets_query)
    total_tickets = total_tickets_result.scalar() or 0

    # Получаем количество открытых тикетов
    open_tickets_query = select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.OPEN)
    open_tickets_result = await session.execute(open_tickets_query)
    open_tickets = open_tickets_result.scalar() or 0

    # Получаем количество тикетов в работе
    in_progress_tickets_query = select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.IN_PROGRESS)
    in_progress_tickets_result = await session.execute(in_progress_tickets_query)
    in_progress_tickets = in_progress_tickets_result.scalar() or 0

    # Получаем количество решенных тикетов
    resolved_tickets_query = select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.RESOLVED)
    resolved_tickets_result = await session.execute(resolved_tickets_query)
    resolved_tickets = resolved_tickets_result.scalar() or 0

    # Получаем количество закрытых тикетов
    closed_tickets_query = select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.CLOSED)
    closed_tickets_result = await session.execute(closed_tickets_query)
    closed_tickets = closed_tickets_result.scalar() or 0

    # Получаем среднюю оценку закрытых тикетов
    avg_rating_query = select(func.avg(Ticket.rating)).where(Ticket.status == TicketStatus.CLOSED)
    avg_rating_result = await session.execute(avg_rating_query)
    avg_rating = avg_rating_result.scalar()

    # Правильное форматирование средней оценки
    if avg_rating is not None:
        avg_rating_text = f"{avg_rating:.2f}/5.0"
    else:
        avg_rating_text = "Нет оценок"

    # Получаем статистику по тикетам за последние 7 дней
    week_ago = datetime.now() - timedelta(days=7)
    recent_tickets_query = select(func.count(Ticket.id)).where(Ticket.created_at >= week_ago)
    recent_tickets_result = await session.execute(recent_tickets_query)
    recent_tickets_count = recent_tickets_result.scalar() or 0

    # Получаем статистику по модераторам
    moderators_query = select(
        User,
        func.count(Ticket.id).label("closed_count"),
        func.avg(Ticket.rating).label("avg_rating")
    ).where(
        User.role == UserRole.MODERATOR
    ).outerjoin(
        Ticket, (Ticket.moderator_id == User.id) & (Ticket.status == TicketStatus.CLOSED)
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
        f"👤 Пользователи: {users_count}\n"
        f"🔑 Модераторы: {moderators_count}\n"
        f"👑 Администраторы: {admins_count}\n\n"

        f"<b>Тикеты:</b>\n"
        f"📊 Всего тикетов: {total_tickets}\n"
        f"🆕 Открытых: {open_tickets}\n"
        f"🔄 В работе: {in_progress_tickets}\n"
        f"✅ Решенных (ожидают оценки): {resolved_tickets}\n"
        f"🔒 Закрытых: {closed_tickets}\n"
        f"📅 Новых за последние 7 дней: {recent_tickets_count}\n"
        f"⭐ Средняя оценка: {avg_rating_text}\n\n"
    )

    if top_moderators:
        message_text += "<b>Топ модераторов:</b>\n"
        for i, (moderator, closed_count, avg_rating) in enumerate(top_moderators, 1):
            # Здесь также нужно исправить форматирование
            if avg_rating is not None:
                avg_rating_text = f"{avg_rating:.2f}/5.0"
            else:
                avg_rating_text = "Нет оценок"

            message_text += (
                f"{i}. {moderator.full_name} - {closed_count} тикетов, "
                f"рейтинг: {avg_rating_text}\n"
            )

    await callback_query.message.edit_text(
        message_text,
        reply_markup=KeyboardFactory.back_button("admin:back_to_menu", admin.language)
    )

    await state.set_state(AdminStates.VIEWING_STATISTICS)
    await callback_query.answer()

    logger.info(f"Admin {user_id} viewed general statistics")


@router.callback_query(F.data == "admin:manage_mods")
async def manage_moderators_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика управления модераторами
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик manage_moderators!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_manage_moderators(callback_query, session, state)


async def _process_manage_moderators(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика управления модераторами
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
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
    kb_items = [
        {"id": "add_moderator", "text": "➕ Добавить модератора"}
    ]

    if moderators:
        kb_items.append({"id": "remove_moderator", "text": "❌ Удалить модератора"})

    kb_items.append({"id": "back_to_menu", "text": "🔙 Назад"})

    # Отправляем сообщение с клавиатурой
    await callback_query.message.edit_text(
        message_text,
        reply_markup=KeyboardFactory.paginated_list(
            kb_items,
            0,
            action_prefix="admin",
            back_callback="admin:back_to_menu",
            language=admin.language
        )
    )

    await state.set_state(AdminStates.MANAGING_MODERATORS)
    await callback_query.answer()

    logger.info(f"Admin {user_id} accessed moderator management")


@router.callback_query(F.data == "admin:add_moderator")
async def add_moderator_start_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика начала процесса добавления модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик add_moderator_start!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_add_moderator_start(callback_query, session, state)


async def _process_add_moderator_start(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика начала процесса добавления модератора
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
        return

    await callback_query.message.edit_text(
        "➕ <b>Добавление нового модератора</b>\n\n"
        "Пожалуйста, отправьте Telegram ID пользователя, "
        "которого вы хотите назначить модератором.\n\n"
        "<i>Пользователь должен быть зарегистрирован в боте.</i>",
        reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
    )

    await state.set_state(AdminStates.ADDING_MODERATOR)
    await callback_query.answer()

    logger.info(f"Admin {user_id} started adding a moderator")


@router.message(AdminStates.ADDING_MODERATOR, F.text)
async def process_add_moderator_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика добавления модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_add_moderator!")
        await message.answer(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        return

    return await _process_add_moderator(message, session, state)


async def _process_add_moderator(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика добавления модератора
    """
    admin_id = message.from_user.id

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await message.answer(_("error_access_denied", admin.language if admin else None))
        return

    # Проверяем, что введенный текст - число
    try:
        new_moderator_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Некорректный ввод. Пожалуйста, введите числовой ID пользователя.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
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
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
        )
        return

    if user.role == UserRole.ADMIN:
        await message.answer(
            f"❌ Пользователь {user.full_name} уже является администратором.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
        )
        return

    if user.role == UserRole.MODERATOR:
        await message.answer(
            f"❌ Пользователь {user.full_name} уже является модератором.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
        )
        return

    # Подтверждение действия
    await message.answer(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Вы действительно хотите назначить пользователя {user.full_name} "
        f"(ID: {user.telegram_id}) модератором?",
        reply_markup=KeyboardFactory.confirmation_keyboard(f"add_mod:{new_moderator_id}", admin.language)
    )


@router.callback_query(F.data.startswith("confirm:add_mod:"))
async def confirm_add_moderator_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика подтверждения добавления модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик confirm_add_moderator!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик confirm_add_moderator!")
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_confirm_add_moderator(callback_query, bot, session, state)


async def _process_confirm_add_moderator(callback_query: CallbackQuery, bot: Bot, session: AsyncSession,
                                         state: FSMContext):
    """
    Реализация обработчика подтверждения добавления модератора
    """
    admin_id = callback_query.from_user.id
    new_moderator_id = int(callback_query.data.split(":")[2])

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
        return

    # Получаем пользователя из БД
    user_query = select(User).where(User.telegram_id == new_moderator_id)
    user_result = await session.execute(user_query)
    user = user_result.scalar_one_or_none()

    if not user:
        await callback_query.message.edit_text(
            f"Пользователь с ID {new_moderator_id} не найден в базе данных.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
        )
        await callback_query.answer()
        return

    # Назначаем пользователя модератором
    user.role = UserRole.MODERATOR
    await session.commit()

    await callback_query.message.edit_text(
        f"✅ Пользователь {user.full_name} (ID: {user.telegram_id}) "
        f"успешно назначен модератором.",
        reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
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
async def remove_moderator_start_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика начала процесса удаления модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик remove_moderator_start!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_remove_moderator_start(callback_query, session, state)


async def _process_remove_moderator_start(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика начала процесса удаления модератора
    """
    user_id = callback_query.from_user.id

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == user_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
        return

    # Получаем список модераторов
    moderators_query = select(User).where(User.role == UserRole.MODERATOR)
    moderators_result = await session.execute(moderators_query)
    moderators = moderators_result.scalars().all()

    if not moderators:
        await callback_query.message.edit_text(
            "В настоящее время нет назначенных модераторов.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
        )
        await callback_query.answer()
        return

    # Формируем сообщение со списком модераторов
    message_text = "❌ <b>Удаление модератора</b>\n\n"
    message_text += "Выберите модератора, которого вы хотите удалить:\n\n"

    # Создаем список модераторов для клавиатуры
    mod_items = []
    for mod in moderators:
        mod_items.append({
            "id": f"confirm_remove_mod:{mod.telegram_id}",
            "text": f"{mod.full_name} (ID: {mod.telegram_id})"
        })

    # Добавляем кнопку "Назад"
    mod_items.append({
        "id": "back_to_manage_mods",
        "text": "🔙 Назад"
    })

    # Отправляем сообщение с клавиатурой
    await callback_query.message.edit_text(
        message_text,
        reply_markup=KeyboardFactory.paginated_list(
            mod_items,
            0,
            action_prefix="admin",
            back_callback="admin:back_to_manage_mods",
            language=admin.language
        )
    )

    await state.set_state(AdminStates.REMOVING_MODERATOR)
    await callback_query.answer()

    logger.info(f"Admin {user_id} started removing a moderator")


@router.callback_query(F.data.startswith("admin:confirm_remove_mod:"))
async def confirm_remove_moderator_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика подтверждения удаления модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик confirm_remove_moderator!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_confirm_remove_moderator(callback_query, session, state)


async def _process_confirm_remove_moderator(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика подтверждения удаления модератора
    """
    admin_id = callback_query.from_user.id
    moderator_id = int(callback_query.data.split(":")[3])

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
        return

    # Получаем модератора из БД
    mod_query = select(User).where(User.telegram_id == moderator_id)
    mod_result = await session.execute(mod_query)
    moderator = mod_result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            f"Модератор с ID {moderator_id} не найден.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
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
        await callback_query.message.edit_text(
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Модератор {moderator.full_name} имеет {active_tickets_count} активных тикетов.\n\n"
            f"Если вы продолжите, все активные тикеты будут возвращены в очередь неназначенных тикетов.\n\n"
            f"Вы уверены, что хотите удалить этого модератора?",
            reply_markup=KeyboardFactory.confirmation_keyboard(f"force_remove_mod:{moderator_id}", admin.language)
        )
        await callback_query.answer()
        return

    # Разжалуем модератора до обычного пользователя
    moderator.role = UserRole.USER
    await session.commit()

    await callback_query.message.edit_text(
        f"✅ Модератор {moderator.full_name} (ID: {moderator.telegram_id}) "
        f"успешно удален из списка модераторов.",
        reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
    )

    # Уведомляем бывшего модератора
    try:
        await callback_query.send_message(
            chat_id=moderator.telegram_id,
            text=f"ℹ️ <b>Уведомление</b>\n\n"
                 f"Ваши права модератора системы поддержки были отозваны администратором.\n\n"
                 f"Вы можете продолжать использовать бота как обычный пользователь."
        )
    except Exception as e:
        logger.error(f"Failed to send notification to former moderator {moderator.telegram_id}: {e}")

    await callback_query.answer()

    logger.info(f"Admin {admin_id} removed moderator {moderator_id}")


async def force_remove_moderator_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика принудительного удаления модератора с активными тикетами
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик force_remove_moderator!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик force_remove_moderator!")
        await callback_query.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_force_remove_moderator(callback_query, bot, session, state)


async def _process_force_remove_moderator(callback_query: CallbackQuery, bot: Bot, session: AsyncSession,
                                          state: FSMContext):
    """
    Реализация обработчика принудительного удаления модератора с активными тикетами
    """
    admin_id = callback_query.from_user.id
    moderator_id = int(callback_query.data.split(":")[2])

    # Получаем админа из БД
    admin_query = select(User).where(User.telegram_id == admin_id)
    admin_result = await session.execute(admin_query)
    admin = admin_result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await callback_query.message.edit_text(
            _("error_access_denied", admin.language if admin else None)
        )
        await callback_query.answer()
        return

    # Получаем модератора из БД
    mod_query = select(User).where(User.telegram_id == moderator_id)
    mod_result = await session.execute(mod_query)
    moderator = mod_result.scalar_one_or_none()

    if not moderator or moderator.role != UserRole.MODERATOR:
        await callback_query.message.edit_text(
            f"Модератор с ID {moderator_id} не найден.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
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
        reply_markup=KeyboardFactory.back_button("admin:back_to_manage_mods", admin.language)
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
async def back_to_menu_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика возврата в главное меню администратора
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
    Реализация обработчика возврата в главное меню администратора
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    language = admin.language if admin else "ru"

    await callback_query.message.edit_text(
        _("admin_main_menu", language),
        reply_markup=KeyboardFactory.main_menu(UserRole.ADMIN, language)
    )

    await state.set_state(AdminStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"Admin {user_id} returned to main menu")


@router.callback_query(F.data == "admin:back_to_manage_mods")
async def back_to_manage_mods_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика возврата в меню управления модераторами
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик back_to_manage_mods!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_manage_moderators(callback_query, session, state)


@router.callback_query(F.data == "admin:mod_menu")
async def switch_to_mod_menu_wrapper(callback_query: CallbackQuery, state: FSMContext, **kwargs):
    """
    Обертка для обработчика переключения на меню модератора
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик switch_to_mod_menu!")
        await callback_query.message.edit_text(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        await callback_query.answer()
        return

    return await _process_switch_to_mod_menu(callback_query, session, state)


async def _process_switch_to_mod_menu(callback_query: CallbackQuery, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика переключения на меню модератора
    """
    user_id = callback_query.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    language = admin.language if admin else "ru"

    await callback_query.message.edit_text(
        _("moderator_main_menu", language),
        reply_markup=KeyboardFactory.main_menu(UserRole.MODERATOR, language)
    )

    await state.set_state(ModeratorStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"Admin {user_id} switched to moderator menu")


@router.callback_query(F.data == "admin:user_menu")
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
    admin = result.scalar_one_or_none()

    language = admin.language if admin else "ru"

    await callback_query.message.edit_text(
        _("user_main_menu", language),
        reply_markup=KeyboardFactory.main_menu(UserRole.USER, language)
    )

    await state.set_state(UserStates.MAIN_MENU)
    await callback_query.answer()

    logger.info(f"Admin {user_id} switched to user menu")


@router.message(F.text == "📈 Общая статистика")
async def admin_stats_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Общая статистика" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик admin_stats_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_admin_stats_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_admin_stats_button(message, session, state)


async def _process_admin_stats_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Общая статистика" на Reply Keyboard
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

    # Симулируем нажатие на Inline кнопку для общей статистики
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "admin:stats"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Здесь создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "Общая статистика"
    await admin_stats_wrapper(fake_callback, state, session=session)

    logger.info(f"Admin {user_id} used Reply button 'General Statistics'")


@router.message(F.text == "👨‍💼 Управление модераторами")
async def manage_mods_button_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика кнопки "Управление модераторами" на Reply Keyboard
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик manage_mods_button!")

        # Пытаемся создать сессию вручную
        from database import async_session_factory
        if async_session_factory:
            async with async_session_factory() as temp_session:
                return await _process_manage_mods_button(message, temp_session, state)
        else:
            # Если не можем создать сессию, отправляем сообщение об ошибке
            await message.answer("Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже.")
            return
    else:
        return await _process_manage_mods_button(message, session, state)


async def _process_manage_mods_button(message: Message, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика кнопки "Управление модераторами" на Reply Keyboard
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

    # Симулируем нажатие на Inline кнопку для управления модераторами
    class FakeCallbackQuery:
        def __init__(self, user_id, message_obj):
            self.from_user = type('obj', (object,), {'id': user_id})
            self.message = message_obj
            self.data = "admin:manage_mods"

        async def answer(self, *args, **kwargs):
            pass

    fake_callback = FakeCallbackQuery(user_id, message)

    # Здесь создаем новое сообщение для вывода результата
    result_message = await message.answer("Загрузка...")
    fake_callback.message = result_message

    # Вызываем обработчик для Inline кнопки "Управление модераторами"
    await manage_moderators_wrapper(fake_callback, state, session=session)

    logger.info(f"Admin {user_id} used Reply button 'Manage Moderators'")


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


@router.message(AdminStates.SEARCHING_TICKET, F.text)
async def process_ticket_search_wrapper(message: Message, state: FSMContext, **kwargs):
    """
    Обертка для обработчика поиска тикета по ID
    """
    session = kwargs.get("session")
    if not session:
        logger.error("Сессия не передана в обработчик process_ticket_search!")
        await message.answer(
            "Произошла ошибка при подключении к базе данных. Пожалуйста, попробуйте позже."
        )
        return

    bot = kwargs.get("bot")
    if not bot:
        logger.error("Bot не передан в обработчик process_ticket_search!")
        await message.answer(
            "Произошла ошибка. Пожалуйста, попробуйте позже."
        )
        return

    return await _process_ticket_search(message, bot, session, state)


async def _process_ticket_search(message: Message, bot: Bot, session: AsyncSession, state: FSMContext):
    """
    Реализация обработчика поиска тикета по ID
    """
    user_id = message.from_user.id

    # Получаем пользователя из БД
    query = select(User).where(User.telegram_id == user_id)
    result = await session.execute(query)
    admin = result.scalar_one_or_none()

    if not admin or admin.role != UserRole.ADMIN:
        await message.answer(_("error_access_denied", admin.language if admin else None))
        return

    # Проверяем, что введенный текст - число
    try:
        ticket_id = int(message.text.strip())
    except ValueError:
        await message.answer(
            "❌ Некорректный ввод. Пожалуйста, введите числовой ID тикета.",
            reply_markup=KeyboardFactory.back_button("admin:back_to_menu", admin.language)
        )
        return

    # Получаем тикет из БД
    ticket_query = select(Ticket).where(Ticket.id == ticket_id).options(
        selectinload(Ticket.user),
        selectinload(Ticket.moderator),
        selectinload(Ticket.messages)
    )
    ticket_result = await session.execute(ticket_query)
    ticket = ticket_result.scalar_one_or_none()

    if not ticket:
        await message.answer(
            _("search_ticket_not_found", admin.language, ticket_id=ticket_id),
            reply_markup=KeyboardFactory.back_button("admin:back_to_menu", admin.language)
        )
        return

    # Отображаем информацию о тикете
    status_texts = {
        TicketStatus.OPEN: "🆕 " + _("status_open", admin.language),
        TicketStatus.IN_PROGRESS: "🔄 " + _("status_in_progress", admin.language),
        TicketStatus.RESOLVED: "✅ " + _("status_resolved", admin.language),
        TicketStatus.CLOSED: "🔒 " + _("status_closed", admin.language)
    }

    message_text = (
        f"🔍 <b>Тикет #{ticket.id}</b>\n\n"
        f"<b>Статус:</b> {status_texts.get(ticket.status, 'Неизвестный статус')}\n"
        f"<b>Создан:</b> {ticket.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"<b>Обновлен:</b> {ticket.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        f"<b>Тема:</b> {ticket.subject or 'Не указана'}\n\n"
        f"<b>Пользователь:</b> {ticket.user.full_name} (ID: {ticket.user.telegram_id})\n"
    )

    if ticket.moderator:
        message_text += f"<b>Модератор:</b> {ticket.moderator.full_name} (ID: {ticket.moderator.telegram_id})\n"

    if ticket.closed_at:
        message_text += f"<b>Закрыт:</b> {ticket.closed_at.strftime('%d.%m.%Y %H:%M')}\n"

    if ticket.rating:
        rating_stars = "⭐" * int(ticket.rating)
        message_text += f"<b>Оценка:</b> {rating_stars} ({ticket.rating}/5)\n"

    await message.answer(message_text)

    # Отправляем историю сообщений
    if ticket.messages:
        await message.answer("<b>История сообщений:</b>")

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
            elif msg.sender_id == ticket.moderator_id:
                sender = "Модератор"
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

    # Показываем админу меню с действиями для тикета
    admin_actions = []

    if ticket.status == TicketStatus.OPEN:
        admin_actions.append(InlineKeyboardButton(
            text="👑 Взять тикет себе",
            callback_data=f"admin:take_ticket:{ticket.id}"
        ))
    elif ticket.status == TicketStatus.IN_PROGRESS:
        admin_actions.append(InlineKeyboardButton(
            text="🔄 Переназначить тикет",
            callback_data=f"admin:reassign_ticket:{ticket.id}"
        ))
        admin_actions.append(InlineKeyboardButton(
            text="✅ Отметить как решенный",
            callback_data=f"admin:resolve_ticket:{ticket.id}"
        ))

    # Добавляем кнопку для перехода в меню администратора
    admin_actions.append(InlineKeyboardButton(
        text=_("action_back", admin.language),
        callback_data="admin:back_to_menu"
    ))

    # Создаем клавиатуру
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [action] for action in admin_actions
    ])

    await message.answer(
        "Выберите действие для этого тикета:",
        reply_markup=keyboard
    )

    # Устанавливаем состояние
    await state.set_state(AdminStates.MAIN_MENU)

    logger.info(f"Admin {user_id} viewed ticket #{ticket.id} details")


def register_handlers(dp: Dispatcher):
    """
    Регистрирует все обработчики данного модуля.

    Args:
        dp: Диспетчер
    """
    dp.include_router(router)
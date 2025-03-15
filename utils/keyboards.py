from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from i18n_setup import gettext as _
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models import TicketStatus, UserRole


def build_language_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора языка.
    """
    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text="🇷🇺 Русский", callback_data="language:ru"))
    kb.add(InlineKeyboardButton(text="🇬🇧 English", callback_data="language:en"))
    kb.add(InlineKeyboardButton(text="🇺🇦 Українська", callback_data="language:uk"))

    return kb.as_markup()


def build_user_main_menu() -> InlineKeyboardMarkup:
    """
    Главное меню для пользователя.
    """
    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text=_("✏️ Создать тикет"), callback_data="user:create_ticket"))
    kb.add(InlineKeyboardButton(text=_("📋 История тикетов"), callback_data="user:ticket_history"))
    kb.add(InlineKeyboardButton(text=_("📝 Активный тикет"), callback_data="user:active_ticket"))
    kb.add(InlineKeyboardButton(text=_("🌐 Изменить язык"), callback_data="user:change_language"))

    # Размещаем кнопки в два столбца
    kb.adjust(2)

    return kb.as_markup()


def build_moderator_main_menu() -> InlineKeyboardMarkup:
    """
    Главное меню для модератора.
    """
    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text=_("📨 Неназначенные тикеты"), callback_data="mod:unassigned_tickets"))
    kb.add(InlineKeyboardButton(text=_("🔄 Переназначить текущий тикет"), callback_data="mod:reassign_ticket"))
    kb.add(InlineKeyboardButton(text=_("📊 Моя статистика"), callback_data="mod:my_stats"))
    kb.add(InlineKeyboardButton(text=_("👤 Меню пользователя"), callback_data="mod:user_menu"))

    # Размещаем кнопки в два столбца
    kb.adjust(2)

    return kb.as_markup()


def build_admin_main_menu() -> InlineKeyboardMarkup:
    """
    Главное меню для админа.
    """
    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text=_("📈 Общая статистика"), callback_data="admin:stats"))
    kb.add(InlineKeyboardButton(text=_("👨‍💼 Управление модераторами"), callback_data="admin:manage_mods"))
    kb.add(InlineKeyboardButton(text=_("🔑 Меню модератора"), callback_data="admin:mod_menu"))
    kb.add(InlineKeyboardButton(text=_("👤 Меню пользователя"), callback_data="admin:user_menu"))

    # Размещаем кнопки в два столбца
    kb.adjust(2)

    return kb.as_markup()


def build_ticket_actions_keyboard(ticket_status: TicketStatus) -> InlineKeyboardMarkup:
    """
    Клавиатура действий с тикетом.
    """
    kb = InlineKeyboardBuilder()

    if ticket_status == TicketStatus.OPEN:
        kb.add(InlineKeyboardButton(text=_("✅ Принять тикет"), callback_data="ticket:take"))
    elif ticket_status == TicketStatus.IN_PROGRESS:
        kb.add(InlineKeyboardButton(text=_("✅ Отметить как решённый"), callback_data="ticket:resolve"))
        kb.add(InlineKeyboardButton(text=_("🔄 Переназначить"), callback_data="ticket:reassign"))
    elif ticket_status == TicketStatus.RESOLVED:
        kb.add(InlineKeyboardButton(text=_("⭐ Оценить и закрыть"), callback_data="ticket:rate"))

    kb.add(InlineKeyboardButton(text=_("🔙 Назад"), callback_data="ticket:back"))

    return kb.as_markup()


def build_rating_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для оценки работы модератора.
    """
    kb = InlineKeyboardBuilder()

    for i in range(1, 6):
        stars = "⭐" * i
        kb.add(InlineKeyboardButton(text=stars, callback_data=f"rating:{i}"))

    return kb.as_markup()


def build_moderator_list_keyboard(moderators: List[dict]) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком модераторов.
    """
    kb = InlineKeyboardBuilder()

    for mod in moderators:
        name = mod.get("full_name", f"ID: {mod.get('telegram_id')}")
        kb.add(InlineKeyboardButton(
            text=name,
            callback_data=f"moderator:{mod.get('id')}"
        ))

    kb.add(InlineKeyboardButton(text=_("🔙 Назад"), callback_data="moderator:back"))

    return kb.as_markup()


def build_tickets_list_keyboard(tickets: List[dict], page: int = 0, page_size: int = 5) -> InlineKeyboardMarkup:
    """
    Клавиатура со списком тикетов с пагинацией.
    """
    kb = InlineKeyboardBuilder()

    # Вычисляем границы текущей страницы
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tickets))

    # Добавляем тикеты текущей страницы
    for i in range(start_idx, end_idx):
        ticket = tickets[i]
        ticket_id = ticket.get("id")
        status = ticket.get("status", TicketStatus.OPEN)

        # Добавляем эмодзи в зависимости от статуса тикета
        status_emoji = {
            TicketStatus.OPEN: "🆕",
            TicketStatus.IN_PROGRESS: "🔄",
            TicketStatus.RESOLVED: "✅",
            TicketStatus.CLOSED: "🔒"
        }.get(status, "❓")

        kb.add(InlineKeyboardButton(
            text=f"{status_emoji} Тикет #{ticket_id}",
            callback_data=f"ticket:{ticket_id}"
        ))

    # Добавляем навигационные кнопки
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"page:{page - 1}"))

    row.append(InlineKeyboardButton(text=_("🔙 Назад"), callback_data="tickets:back"))

    if end_idx < len(tickets):
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"page:{page + 1}"))

    kb.row(*row)

    return kb.as_markup()


def build_back_keyboard(callback_data: str = "back") -> InlineKeyboardMarkup:
    """
    Простая клавиатура с кнопкой "Назад".
    """
    kb = InlineKeyboardBuilder()
    kb.add(InlineKeyboardButton(text=_("🔙 Назад"), callback_data=callback_data))
    return kb.as_markup()


def build_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для подтверждения действия.
    """
    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text=_("✅ Да"), callback_data=f"confirm:{action}"))
    kb.add(InlineKeyboardButton(text=_("❌ Нет"), callback_data=f"cancel:{action}"))

    return kb.as_markup()
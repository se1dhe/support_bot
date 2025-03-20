from typing import List, Optional, Union, Dict, Any
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from models import TicketStatus, UserRole
from utils.i18n import _


class KeyboardFactory:
    """
    Фабрика для создания клавиатур бота.
    Содержит методы для создания различных типов клавиатур.
    """

    @staticmethod
    def language_selection(user_language: str = None) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для выбора языка.

        Args:
            user_language: Текущий язык пользователя (для подсветки выбранного языка)

        Returns:
            InlineKeyboardMarkup: Клавиатура выбора языка
        """
        kb = InlineKeyboardBuilder()

        # Определяем, какой язык сейчас выбран (если указан)
        ru_text = "🇷🇺 Русский" + (" ✓" if user_language == "ru" else "")
        en_text = "🇬🇧 English" + (" ✓" if user_language == "en" else "")
        uk_text = "🇺🇦 Українська" + (" ✓" if user_language == "uk" else "")

        kb.add(InlineKeyboardButton(text=ru_text, callback_data="language:ru"))
        kb.add(InlineKeyboardButton(text=en_text, callback_data="language:en"))
        kb.add(InlineKeyboardButton(text=uk_text, callback_data="language:uk"))

        # Добавляем кнопку "Назад", если пользователь уже выбрал язык
        if user_language:
            kb.add(InlineKeyboardButton(
                text=_("action_back", user_language),
                callback_data="user:back_to_menu"
            ))

        return kb.as_markup()

    @staticmethod
    def main_menu(role: UserRole, language: str = None) -> InlineKeyboardMarkup:
        """
        Создает главное меню в зависимости от роли пользователя.

        Args:
            role: Роль пользователя
            language: Язык пользователя

        Returns:
            InlineKeyboardMarkup: Клавиатура главного меню
        """
        kb = InlineKeyboardBuilder()

        if role == UserRole.USER:
            kb.add(InlineKeyboardButton(
                text=_("menu_create_ticket", language),
                callback_data="user:create_ticket"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_ticket_history", language),
                callback_data="user:ticket_history"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_active_ticket", language),
                callback_data="user:active_ticket"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_change_language", language),
                callback_data="user:change_language"
            ))
        elif role == UserRole.MODERATOR:
            kb.add(InlineKeyboardButton(
                text=_("menu_unassigned_tickets", language),
                callback_data="mod:unassigned_tickets"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_reassign_ticket", language),
                callback_data="mod:reassign_ticket"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_my_stats", language),
                callback_data="mod:my_stats"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_user_menu", language),
                callback_data="mod:user_menu"
            ))
        elif role == UserRole.ADMIN:
            kb.add(InlineKeyboardButton(
                text=_("menu_general_stats", language),
                callback_data="admin:stats"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_manage_moderators", language),
                callback_data="admin:manage_mods"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_moderator_menu", language),
                callback_data="admin:mod_menu"
            ))
            kb.add(InlineKeyboardButton(
                text=_("menu_user_menu", language),
                callback_data="admin:user_menu"
            ))

        # Размещаем кнопки в два столбца
        kb.adjust(2)

        return kb.as_markup()

    @staticmethod
    def main_reply_keyboard(role: UserRole, language: str = None) -> ReplyKeyboardMarkup:
        """
        Создает основную reply-клавиатуру в зависимости от роли пользователя.

        Args:
            role: Роль пользователя
            language: Язык пользователя

        Returns:
            ReplyKeyboardMarkup: Reply-клавиатура
        """
        # Базовая кнопка меню для всех ролей
        buttons = [[KeyboardButton(text="📋 Меню")]]

        # Добавляем кнопки в зависимости от роли
        if role == UserRole.USER:
            buttons[0].append(KeyboardButton(text=_("menu_active_ticket", language)))
            buttons.append([
                KeyboardButton(text=_("menu_create_ticket", language)),
                KeyboardButton(text=_("menu_ticket_history", language))
            ])
        elif role == UserRole.MODERATOR:
            buttons[0].append(KeyboardButton(text=_("menu_active_ticket", language)))
            buttons.append([
                KeyboardButton(text=_("menu_unassigned_tickets", language)),
                KeyboardButton(text=_("menu_my_stats", language))
            ])
        elif role == UserRole.ADMIN:
            buttons[0].append(KeyboardButton(text=_("menu_general_stats", language)))
            buttons.append([
                KeyboardButton(text=_("menu_manage_moderators", language)),
                KeyboardButton(text="🔍 Поиск тикета")
            ])

        # Создаем клавиатуру с resize_keyboard=True, чтобы она не занимала много места
        return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    @staticmethod
    def ticket_actions(ticket_status: TicketStatus, ticket_id: int, language: str = None) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру с действиями для тикета в зависимости от его статуса.

        Args:
            ticket_status: Статус тикета
            ticket_id: ID тикета
            language: Язык пользователя

        Returns:
            InlineKeyboardMarkup: Клавиатура с действиями
        """
        kb = InlineKeyboardBuilder()

        if ticket_status == TicketStatus.OPEN:
            kb.add(InlineKeyboardButton(
                text=_("action_take_ticket", language),
                callback_data=f"mod:take_ticket:{ticket_id}"
            ))
        elif ticket_status == TicketStatus.IN_PROGRESS:
            kb.add(InlineKeyboardButton(
                text=_("action_mark_resolved", language),
                callback_data=f"mod:resolve_ticket:{ticket_id}"
            ))
            kb.add(InlineKeyboardButton(
                text=_("action_reassign", language),
                callback_data=f"mod:reassign_ticket:{ticket_id}"
            ))

        # Добавляем кнопку "Назад"
        kb.add(InlineKeyboardButton(
            text=_("action_back", language),
            callback_data="mod:back_to_menu"
        ))

        # Размещаем кнопки по одной в строке
        kb.adjust(1)

        return kb.as_markup()

    @staticmethod
    def rating_keyboard(language: str = None) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для оценки работы модератора.

        Args:
            language: Язык пользователя

        Returns:
            InlineKeyboardMarkup: Клавиатура с оценками
        """
        kb = InlineKeyboardBuilder()

        for i in range(1, 6):
            kb.add(InlineKeyboardButton(
                text=_(f"rating_{i}", language),
                callback_data=f"rating:{i}"
            ))

        # Размещаем все 5 кнопок в один ряд
        kb.adjust(5)

        return kb.as_markup()

    @staticmethod
    def back_button(callback_data: str = "back_to_menu", language: str = None) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру только с кнопкой "Назад".

        Args:
            callback_data: Callback-данные для кнопки
            language: Язык пользователя

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопкой "Назад"
        """
        kb = InlineKeyboardBuilder()

        kb.add(InlineKeyboardButton(
            text=_("action_back", language),
            callback_data=callback_data
        ))

        return kb.as_markup()

    @staticmethod
    def confirmation_keyboard(action: str, language: str = None) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру для подтверждения действия.

        Args:
            action: Действие, которое нужно подтвердить (callback data)
            language: Язык пользователя

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопками "Да" и "Нет"
        """
        kb = InlineKeyboardBuilder()

        kb.add(InlineKeyboardButton(
            text=_("confirm_yes", language),
            callback_data=f"confirm:{action}"
        ))
        kb.add(InlineKeyboardButton(
            text=_("confirm_no", language),
            callback_data=f"cancel:{action}"
        ))

        # Размещаем кнопки в один ряд
        kb.adjust(2)

        return kb.as_markup()

    @staticmethod
    def paginated_list(
            items: List[Dict[str, Any]],
            current_page: int,
            page_size: int = 5,
            action_prefix: str = "item",
            back_callback: str = "back_to_menu",
            language: str = None
    ) -> InlineKeyboardMarkup:
        """
        Создает клавиатуру со списком элементов и кнопками пагинации.

        Args:
            items: Список элементов для отображения
            current_page: Текущая страница (начиная с 0)
            page_size: Количество элементов на странице
            action_prefix: Префикс для callback данных
            back_callback: Callback данные для кнопки "Назад"
            language: Язык пользователя

        Returns:
            InlineKeyboardMarkup: Клавиатура со списком и пагинацией
        """
        kb = InlineKeyboardBuilder()

        # Вычисляем границы текущей страницы
        total_pages = (len(items) + page_size - 1) // page_size if items else 0
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, len(items))

        # Добавляем элементы текущей страницы
        for i in range(start_idx, end_idx):
            item = items[i]
            item_id = item.get("id")
            item_text = item.get("text", f"Item #{item_id}")

            kb.add(InlineKeyboardButton(
                text=item_text,
                callback_data=f"{action_prefix}:{item_id}"
            ))

        # Добавляем навигационные кнопки
        row = []

        # Кнопка "Назад" (предыдущая страница)
        if current_page > 0:
            row.append(InlineKeyboardButton(
                text="◀️",
                callback_data=f"page:{current_page - 1}"
            ))

        # Кнопка "Назад в меню"
        row.append(InlineKeyboardButton(
            text=_("action_back", language),
            callback_data=back_callback
        ))

        # Кнопка "Вперед" (следующая страница)
        if current_page < total_pages - 1:
            row.append(InlineKeyboardButton(
                text="▶️",
                callback_data=f"page:{current_page + 1}"
            ))

        # Добавляем кнопки навигации одним рядом
        kb.row(*row)

        return kb.as_markup()
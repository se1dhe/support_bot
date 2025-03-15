# states.py
# ---------
from aiogram.fsm.state import State, StatesGroup


class UserStates(StatesGroup):
    """Состояния для пользователя"""
    SELECTING_LANGUAGE = State()   # Пользователь выбирает язык
    MAIN_MENU = State()            # Главное меню пользователя
    CREATING_TICKET = State()      # Создание тикета
    SENDING_MESSAGE = State()      # Отправка сообщения в тикет
    RATING_MODERATOR = State()     # Оценка модератора
    VIEWING_TICKET_HISTORY = State()  # Просмотр истории тикетов


class ModeratorStates(StatesGroup):
    """Состояния для модератора"""
    MAIN_MENU = State()            # Главное меню модератора
    VIEWING_TICKETS = State()      # Просмотр списка тикетов
    WORKING_WITH_TICKET = State()  # Работа с тикетом
    SENDING_MESSAGE = State()      # Отправка сообщения в тикет
    REASSIGNING_TICKET = State()   # Переназначение тикета


class AdminStates(StatesGroup):
    """Состояния для администратора"""
    MAIN_MENU = State()              # Главное меню админа
    VIEWING_STATISTICS = State()     # Просмотр статистики
    MANAGING_MODERATORS = State()    # Управление модераторами
    ADDING_MODERATOR = State()       # Добавление модератора
    REMOVING_MODERATOR = State()     # Удаление модератора

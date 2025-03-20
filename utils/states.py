from aiogram.fsm.state import State, StatesGroup

class UserStates(StatesGroup):
    """Состояния пользовательского интерфейса"""
    SELECTING_LANGUAGE = State()   # Пользователь выбирает язык
    MAIN_MENU = State()            # Главное меню пользователя
    CREATING_TICKET = State()      # Создание тикета
    SENDING_MESSAGE = State()      # Отправка сообщения в тикет
    RATING_MODERATOR = State()     # Оценка модератора
    VIEWING_TICKET_HISTORY = State()  # Просмотр истории тикетов
    VIEWING_TICKET_DETAILS = State()  # Просмотр деталей тикета


class ModeratorStates(StatesGroup):
    """Состояния интерфейса модератора"""
    MAIN_MENU = State()            # Главное меню модератора
    VIEWING_TICKETS = State()      # Просмотр списка тикетов
    WORKING_WITH_TICKET = State()  # Работа с тикетом
    SENDING_MESSAGE = State()      # Отправка сообщения в тикет
    REASSIGNING_TICKET = State()   # Переназначение тикета
    VIEWING_STATISTICS = State()   # Просмотр статистики


class AdminStates(StatesGroup):
    """Состояния интерфейса администратора"""
    MAIN_MENU = State()              # Главное меню админа
    VIEWING_STATISTICS = State()     # Просмотр статистики
    MANAGING_MODERATORS = State()    # Управление модераторами
    ADDING_MODERATOR = State()       # Добавление модератора
    REMOVING_MODERATOR = State()     # Удаление модератора
    SEARCHING_TICKET = State()       # Поиск тикета
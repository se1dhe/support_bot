# emoji.py
# --------
from models import TicketStatus, UserRole


# Эмодзи для разных статусов тикетов
TICKET_STATUS_EMOJI = {
    TicketStatus.OPEN: "🆕",
    TicketStatus.IN_PROGRESS: "🔄",
    TicketStatus.RESOLVED: "✅",
    TicketStatus.CLOSED: "🔒"
}

# Эмодзи для ролей пользователей
USER_ROLE_EMOJI = {
    UserRole.USER: "👤",
    UserRole.MODERATOR: "🔑",
    UserRole.ADMIN: "👑"
}

# Эмодзи для оценок
RATING_EMOJI = {
    1: "⭐",
    2: "⭐⭐",
    3: "⭐⭐⭐",
    4: "⭐⭐⭐⭐",
    5: "⭐⭐⭐⭐⭐"
}

# Эмодзи для клавиатуры
KEYBOARD_EMOJI = {
    "back": "🔙",
    "create": "✏️",
    "history": "📋",
    "active": "📝",
    "language": "🌐",
    "unassigned": "📨",
    "reassign": "🔄",
    "stats": "📊",
    "user_menu": "👤",
    "moderator_menu": "🔑",
    "admin_menu": "👑",
    "take": "✅",
    "resolve": "✅",
    "rate": "⭐",
    "yes": "✅",
    "no": "❌"
}

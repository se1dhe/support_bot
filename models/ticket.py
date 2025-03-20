import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, ForeignKey, Float, func, Text
from sqlalchemy.orm import relationship

from database import Base


class TicketStatus(enum.Enum):
    """Статусы тикетов в системе"""
    OPEN = "open"  # Тикет создан, но не взят модератором
    IN_PROGRESS = "in_progress"  # Тикет взят модератором в работу
    RESOLVED = "resolved"  # Модератор пометил тикет как решенный, ожидается оценка от пользователя
    CLOSED = "closed"  # Пользователь оценил работу модератора, тикет закрыт


class Ticket(Base):
    """Модель тикета поддержки"""
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    moderator_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(Enum(TicketStatus), nullable=False, default=TicketStatus.OPEN)
    subject = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    closed_at = Column(DateTime, nullable=True)
    rating = Column(Float, nullable=True)
    priority = Column(Integer, default=0)  # Приоритет тикета: 0 - обычный, 1 - высокий, 2 - срочный
    is_archived = Column(Boolean, default=False)  # Флаг архивации тикета
    comments = Column(Text, nullable=True)  # Внутренние комментарии для модераторов

    # Отношения
    user = relationship("User", back_populates="tickets", foreign_keys=[user_id])
    moderator = relationship("User", back_populates="assigned_tickets", foreign_keys=[moderator_id])
    messages = relationship("Message", back_populates="ticket", cascade="all, delete-orphan",
                            order_by="Message.sent_at")

    def __repr__(self):
        return f"<Ticket #{self.id}: {self.status.value}>"

    def close(self, rating: float = None):
        """
        Закрывает тикет с указанной оценкой.

        Args:
            rating: Оценка пользователя (от 1 до 5)
        """
        self.status = TicketStatus.CLOSED
        self.closed_at = datetime.now()

        if rating is not None:
            self.rating = rating

    def reopen(self):
        """Переоткрывает закрытый тикет"""
        if self.status == TicketStatus.CLOSED:
            self.status = TicketStatus.OPEN
            self.moderator_id = None
            self.closed_at = None
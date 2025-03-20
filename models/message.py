import enum
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship

from database import Base


class MessageType(enum.Enum):
    """Типы сообщений в тикетах"""
    TEXT = "text"  # Текстовое сообщение
    PHOTO = "photo"  # Фотография
    VIDEO = "video"  # Видео
    DOCUMENT = "document"  # Документ
    AUDIO = "audio"  # Аудиосообщение
    VOICE = "voice"  # Голосовое сообщение
    SYSTEM = "system"  # Системное сообщение


class Message(Base):
    """Модель сообщения в тикете"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.TEXT)
    text = Column(Text, nullable=True)
    file_id = Column(String(255), nullable=True)  # Telegram file_id для медиа-файлов
    sent_at = Column(DateTime, default=func.now())
    is_read = Column(Integer, default=0)  # 0 - не прочитано, 1 - прочитано пользователем, 2 - прочитано модератором
    media_group_id = Column(String(255), nullable=True)  # ID группы медиа (для группы фото/видео)

    # Отношения
    ticket = relationship("Ticket", back_populates="messages")
    sender = relationship("User")

    def __repr__(self):
        return f"<Message #{self.id}: {self.message_type.value}>"

    def mark_as_read(self, by_user: bool = True):
        """
        Отмечает сообщение как прочитанное.

        Args:
            by_user: True если прочитано пользователем, False если модератором
        """
        self.is_read = 1 if by_user else 2
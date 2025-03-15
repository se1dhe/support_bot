# message.py
# ----------
import enum
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import relationship

from database import Base


class MessageType(enum.Enum):
    TEXT = "text"
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    AUDIO = "audio"
    VOICE = "voice"
    SYSTEM = "system"  # Системные сообщения (например, "тикет взят в работу")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_type = Column(Enum(MessageType), nullable=False, default=MessageType.TEXT)
    text = Column(Text, nullable=True)
    file_id = Column(String(255), nullable=True)  # Telegram file_id для медиа-файлов
    sent_at = Column(DateTime, default=func.now())

    # Отношения
    ticket = relationship("Ticket", back_populates="messages")
    sender = relationship("User")

    def __repr__(self):
        return f"<Message #{self.id}: {self.message_type.value}>"

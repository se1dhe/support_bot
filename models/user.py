# user.py
# -------

import enum
from sqlalchemy import Column, Integer, String, Boolean, Enum, DateTime, func
from sqlalchemy.orm import relationship

from database import Base


class UserRole(enum.Enum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language = Column(String(10), nullable=False, default="ru")
    role = Column(Enum(UserRole), nullable=False, default=UserRole.USER)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    # Отношения
    tickets = relationship("Ticket", back_populates="user", cascade="all, delete-orphan")
    assigned_tickets = relationship("Ticket",
                                    foreign_keys="[Ticket.moderator_id]",
                                    back_populates="moderator")

    def __repr__(self):
        return f"<User {self.telegram_id}: {self.username or self.first_name or 'Unknown'}>"

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return self.username
        else:
            return str(self.telegram_id)
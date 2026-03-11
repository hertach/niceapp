# app/models/user.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean
from app.core.database import Base


class User(Base):
    __tablename__ = 'users'

    id:         Mapped[int]  = mapped_column(primary_key=True)
    username:   Mapped[str]  = mapped_column(String(64), unique=True, index=True)
    password:   Mapped[str]  = mapped_column(String(255))  # bcrypt hash
    role:       Mapped[str]  = mapped_column(String(32), default='user')
    is_active:  Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f'<User {self.username} ({self.role})>'
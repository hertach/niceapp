# app/models/role.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from app.core.database import Base


class Role(Base):
    __tablename__ = 'roles'

    id:          Mapped[int] = mapped_column(primary_key=True)
    name:        Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default='')

    def __repr__(self) -> str:
        return f'<Role {self.name}>'
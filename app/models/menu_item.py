# app/models/menu_item.py
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(64))
    icon: Mapped[str] = mapped_column(String(64))
    path: Mapped[str] = mapped_column(String(255))
    roles: Mapped[str] = mapped_column(String(255), default="")
    # Reihenfolge in der Sidebar
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def roles_list(self) -> list[str]:
        """Komma-getrennte Roles als Liste. Leer = alle."""
        if not self.roles:
            return []
        return [r.strip() for r in self.roles.split(",")]

    def __repr__(self) -> str:
        return f"<MenuItem {self.label} ({self.path})>"

# app/core/auth.py
import bcrypt
from nicegui import app as nicegui_app
from nicegui import ui
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.logger import app_logger
from app.models.menu_item import MenuItem
from app.models.user import User


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(
        plain.encode("utf-8"),
        hashed.encode("utf-8"),
    )


def authenticate_user(username: str, password: str, session: Session) -> User | None:
    user = session.query(User).filter_by(username=username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password):
        return None
    app_logger.info(f"{user.username} hat sich eingeloggt")
    return user


def check_access(path: str) -> bool:
    """
    Prüft ob der eingeloggte User Zugriff auf den Pfad hat.
    Leitet automatisch weiter falls nicht. Gibt True zurück wenn OK.
    """

    if not nicegui_app.storage.user.get("authenticated"):
        ui.navigate.to("/login")
        return False

    current_role = nicegui_app.storage.user.get("role", "")

    with get_session() as session:
        item = session.query(MenuItem).filter_by(path=path).first()

    if not item:
        ui.notify("Seite nicht gefunden.", type="negative")
        ui.navigate.to("/")
        return False

    if not item.roles_list():
        return True

    if current_role not in item.roles_list():
        ui.notify("Keine Berechtigung.", type="negative")
        app_logger.warning(
            f"Keine Berechtigung für {nicegui_app.storage.user.get('name')}"
        )
        ui.navigate.to("/")
        return False

    return True

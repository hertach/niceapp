# app/core/auth.py
import bcrypt
from nicegui import ui, app as nicegui_app
from app.core.database import get_session
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.menu_item import MenuItem


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(
        plain.encode('utf-8'),
        hashed.encode('utf-8')
    )


def authenticate_user(username: str, password: str, session: Session) -> User | None:
    user = session.query(User).filter_by(username=username).first()

    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password):
        return None

    return user

def check_access(path: str) -> bool:
    """
    Prüft ob der eingeloggte User Zugriff auf den Pfad hat.
    Leitet automatisch weiter falls nicht. Gibt True zurück wenn OK.
    """
    # Nicht eingeloggt → Login
    if not nicegui_app.storage.user.get('authenticated'):
        ui.navigate.to('/login')
        return False

    current_role = nicegui_app.storage.user.get('role', '')

    # Menüpunkt in DB suchen
    with get_session() as session:
        item = session.query(MenuItem).filter_by(path=path).first()

    # Pfad nicht in DB → kein Zugriff (Sicherheits-Fallback)
    if not item:
        ui.notify('Seite nicht gefunden.', type='negative')
        ui.navigate.to('/')
        return False

    # Keine Rolleneinschränkung → alle dürfen
    if not item.roles_list():
        return True

    # Rolle prüfen
    if current_role not in item.roles_list():
        ui.notify('Keine Berechtigung.', type='negative')
        ui.navigate.to('/')
        return False

    return True
# app/main.py
from pathlib import Path
from nicegui import ui, app as nicegui_app
from app.components.layout import main_layout
from app.config import APP_TITLE
from app.pages.login import login_page
from app.core.database import init_db, get_session
from app.core.auth import hash_password, check_access
from app.models.user import User
from app.pages.admin.users import users_page
from app.pages.admin.roles import roles_page
from app.pages.admin.menu_items import menu_items_page
from app.components.layout import main_layout, _apply_active, _apply_inactive
from typing import Callable

PAGES: dict[str, Callable] = {}

def page(path: str) -> Callable:
    """Decorator der eine Funktion als Seite registriert."""
    def decorator(fn: Callable) -> Callable:
        PAGES[path] = fn
        return fn
    return decorator

# Seiten registrieren – einmal dekorieren, fertig
@page('/')
def _dashboard() -> None:
    username = nicegui_app.storage.user.get('username', '')
    ui.label('Dashboard').style(
        'font-size: 24px; font-weight: 600; color: #1e3a5f;'
    )
    ui.label(f'Willkommen, {username}').style('color: #666;')

@page('/admin/users')
def _admin_users() -> None:
    users_page()

@page('/admin/roles')
def _admin_roles() -> None:
    roles_page()

@page('/admin/menu')
def _admin_menu() -> None:
    menu_items_page()

def _dashboard() -> None:
    username = nicegui_app.storage.user.get('username', '')
    ui.label('Dashboard').style(
        'font-size: 24px; font-weight: 600; color: #1e3a5f;'
    )
    ui.label(f'Willkommen, {username}').style('color: #666;')


def create_test_user() -> None:
    with get_session() as session:
        exists = session.query(User).filter_by(username='admin').first()
        if not exists:
            session.add(User(
                username='admin',
                password=hash_password('admin123'),
                role='admin',
            ))
            session.commit()
            print('✅ Testuser angelegt: admin / admin123')


def main() -> None:
    init_db()
    create_test_user()

    nicegui_app.add_static_files('/static', Path(__file__).parent / 'static')

    css_path = Path(__file__).parent / 'static' / 'style.css'
    ui.add_css(css_path.read_text(), shared=True)

    @ui.page('/login')
    def login() -> None:
        login_page()

    @ui.page('/')
    def index() -> None:
        if not nicegui_app.storage.user.get('authenticated'):
            ui.navigate.to('/login')
            return

        content_ref: list[ui.column] = []
        nav_refs_ref: list[dict[str, ui.row]] = []
        active_path: list[str] = ['/']  # ← aktueller Pfad

        def navigate(path: str) -> None:
            page_fn = PAGES.get(path)
            if not page_fn:
                ui.notify('Seite nicht gefunden.', type='negative')
                return
            if not check_access(path):
                return

            # Alten aktiven Eintrag deaktivieren
            if active_path[0] in nav_refs_ref[0]:
                _apply_inactive(nav_refs_ref[0][active_path[0]])

            # Neuen aktiven Eintrag hervorheben
            if path in nav_refs_ref[0]:
                _apply_active(nav_refs_ref[0][path])

            active_path[0] = path

            # Content neu rendern
            content_ref[0].clear()
            with content_ref[0]:
                page_fn()

        content, nav_refs = main_layout(navigate, active_path[0])
        content_ref.append(content)
        nav_refs_ref.append(nav_refs)

        with content:
            _dashboard()

    ui.run(
        title=APP_TITLE,
        port=8080,
        reload=True,
        favicon='/static/icons/favicon.ico',
        storage_secret='bitte-aendern-in-production-xyz123',
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
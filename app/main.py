# app/main.py
from pathlib import Path
from nicegui import ui, app as nicegui_app
from app.components.layout import main_layout
from app.config import APP_TITLE
from app.pages.login import login_page
from app.core.database import init_db, get_session
from app.core.auth import hash_password
from app.models.user import User
from app.pages.admin.users import users_page
from app.pages.admin.roles import roles_page
from app.pages.admin.menu_items import menu_items_page
from app.core.auth import authenticate_user, check_access

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

def require_role(role: str) -> bool:
    """
    Prüft ob der eingeloggte User die nötige Rolle hat.
    Leitet weiter falls nicht. Gibt True zurück wenn OK.
    """
    if not nicegui_app.storage.user.get('authenticated'):
        ui.navigate.to('/login')
        return False
    if nicegui_app.storage.user.get('role') != role:
        ui.notify('Keine Berechtigung.', type='negative')
        ui.navigate.to('/')
        return False
    return True

def main() -> None:
    init_db()
    create_test_user()

    css_path = Path(__file__).parent / 'static' / 'style.css'
    ui.add_css(css_path.read_text(), shared=True)

    @ui.page('/login')
    def login() -> None:
        login_page()

    @ui.page('/')
    def index() -> None:
        if not check_access('/'):
            return
        with main_layout():
            ui.label('Willkommen im Dashboard').style(
                'font-size: 24px; font-weight: 600; color: #1e3a5f;'
            )
            ui.label(
                f'Eingeloggt als: {nicegui_app.storage.user.get("username")}'
            ).style('color: #666;')

    @ui.page('/admin/users')
    def admin_users() -> None:
        if not check_access('/admin/users'):
            return
        with main_layout():
            users_page()

    @ui.page('/admin/roles')
    def admin_roles() -> None:
        if not check_access('/admin/roles'):
            return
        with main_layout():
            roles_page()

    @ui.page('/admin/menu')
    def admin_menu() -> None:
        if not check_access('/admin/menu'):
            return
        with main_layout():
            menu_items_page()

    @ui.page('/test-logo')
    def test_logo() -> None:
        ui.image('/static/icons/logo.png').style('height: 40px;width: 40px;')
        ui.label('/static/icons/logo.png')

    nicegui_app.add_static_files('/static', Path(__file__).parent / 'static')

    ui.run(
        title=APP_TITLE,
        port=8080,
        reload=True,
        favicon='app/static/icons/favicon.ico',
        storage_secret='bitte-aendern-in-production-xyz123',
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
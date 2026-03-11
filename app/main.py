# app/main.py
from pathlib import Path
from nicegui import ui, app as nicegui_app
from app.config import APP_TITLE
from app.pages.login import login_page
from app.core.database import init_db, get_session
from app.core.auth import hash_password, check_access
from app.models.user import User
from app.pages.admin.users import users_page
from app.pages.admin.roles import roles_page
from app.pages.admin.menu_items import menu_items_page
from app.pages.dashboard import dashboard_page
from app.components.layout import main_layout, _apply_active, _apply_inactive
from typing import Callable
from app.config import APP_TITLE, STORAGE_SECRET, PORT, RELOAD

PAGES: dict[str, Callable] = {}

def page(path: str) -> Callable:
    def decorator(fn: Callable) -> Callable:
        PAGES[path] = fn
        return fn
    return decorator


# ── Seiten registrieren ────────────────────────────────────────────────────────
# WICHTIG: navigate wird erst innerhalb von index() definiert,
# daher als Lambda mit spätem Binding

@page('/')
def _dashboard() -> None:
    pass  # wird unten via _render_page überschrieben – siehe Hinweis

@page('/admin/users')
def _admin_users() -> None:
    users_page()

@page('/admin/roles')
def _admin_roles() -> None:
    roles_page()

@page('/admin/menu')
def _admin_menu() -> None:
    menu_items_page()


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

        content_ref:   list[ui.column]          = []
        nav_refs_ref:  list[dict[str, ui.row]]  = []
        active_path:   list[str]                = ['/']

        def navigate(path: str) -> None:
            page_fn = PAGES.get(path)
            if not page_fn:
                ui.notify('Seite nicht gefunden.', type='negative')
                return
            if not check_access(path):
                return

            if active_path[0] in nav_refs_ref[0]:
                _apply_inactive(nav_refs_ref[0][active_path[0]])
            if path in nav_refs_ref[0]:
                _apply_active(nav_refs_ref[0][path])

            active_path[0] = path
            content_ref[0].clear()
            with content_ref[0]:
                page_fn()

        # navigate ist jetzt definiert → Dashboard korrekt registrieren
        PAGES['/'] = lambda: dashboard_page(navigate)

        content, nav_refs = main_layout(navigate, active_path[0])
        content_ref.append(content)
        nav_refs_ref.append(nav_refs)

        # Initialer Render über die Registry
        with content:
            PAGES['/']()

    ui.run(
        title=APP_TITLE,
        port=PORT,
        reload=RELOAD,
        favicon=Path(__file__).parent / 'static' / 'icons' / 'favicon.ico',
        storage_secret=STORAGE_SECRET,
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
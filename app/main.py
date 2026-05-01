# app/main.py
import asyncio
from pathlib import Path
from nicegui import ui, app as nicegui_app
from app.pages.login import login_page
from app.core.database import init_db, get_session
from app.core.auth import hash_password, check_access
from app.models.user import User
from app.pages.dashboard import dashboard_page
from app.pages.patients import patients_page
from app.pages.admin.settings import settings_page
from app.pages.patient_detail import patient_detail_page
from app.components.layout import main_layout, _apply_active, _apply_inactive
from typing import Callable
from app.config import APP_TITLE, STORAGE_SECRET, PORT, RELOAD
from app.models.log_entry import init_log_db
from app.models.app_setting import AppSetting
from app.core.logger import update_console_logger
from app.core.backup import backup_on_shutdown, backup_scheduler_loop


def apply_initial_settings():
    """Lädt die App-Settings aus der DB und wendet sie an."""
    with get_session() as session:
        setting = session.query(AppSetting).first()
        if not setting:
            setting = AppSetting()
            session.add(setting)
            session.commit()

        # Logger entsprechend konfigurieren
        update_console_logger(setting.log_to_terminal)

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

# @page('/patients')
# def _patients() -> None:
#     patients_page()

@page('/admin/settings')
def _settings()-> None:
    settings_page()

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
    init_log_db()
    apply_initial_settings()
    create_test_user()

    nicegui_app.on_startup(lambda: asyncio.create_task(backup_scheduler_loop()))
    nicegui_app.on_shutdown(backup_on_shutdown)

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

            allowed_sub_pages = ['/patient_detail']
            if path not in allowed_sub_pages:
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
        PAGES['/patients'] = lambda: patients_page(navigate)
        PAGES['/patient_detail'] = lambda: patient_detail_page(navigate)

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
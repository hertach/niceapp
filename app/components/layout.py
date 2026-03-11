# app/components/layout.py
from contextlib import contextmanager
from typing import Generator
from nicegui import ui, app as nicegui_app
from app.core.database import get_session
from app.models.menu_item import MenuItem
from app.config import APP_TITLE, APP_LOGO

COLORS = {
    'sidebar_bg':  '#1e3a5f',
    'header_bg':   '#0f2744',
    'accent':      '#0078d4',
    'text_light':  '#ffffff',
    'text_muted':  '#c7d8ec',
    'content_bg':  '#f3f6f9',
}

def _load_nav_items(current_role: str) -> list[MenuItem]:
    """Lädt Menüpunkte aus DB, gefiltert nach Rolle."""
    with get_session() as session:
        items = (
            session.query(MenuItem)
            .order_by(MenuItem.sort_order)
            .all()
        )
        # Filtern: leer = alle, sonst Rolle prüfen
        return [
            i for i in items
            if not i.roles_list() or current_role in i.roles_list()
        ]

def _header() -> None:
    with ui.header().style(
        f'background-color: {COLORS["header_bg"]}; '
        'height: 48px; padding: 0 16px; '
        'display: flex; align-items: center; justify-content: space-between;'
    ):
        with ui.row().style('align-items: center; gap: 10px;'):
            ui.image(APP_LOGO).style('height: 28px; width: 28px;')
            ui.label(APP_TITLE).style(
                f'color: {COLORS["text_light"]}; '
                'font-size: 18px; font-weight: 600; letter-spacing: 0.5px;'
            )

        with ui.row().style('align-items: center; gap: 16px;'):
            username = nicegui_app.storage.user.get('username', '')
            role     = nicegui_app.storage.user.get('role', '')

            ui.icon('account_circle').style(
                f'color: {COLORS["text_muted"]}; font-size: 24px;'
            )
            ui.label(f'{username} ({role})').style(
                f'color: {COLORS["text_muted"]}; font-size: 13px;'
            )
            ui.separator().style(
                'width: 1px; height: 24px; background-color: rgba(255,255,255,0.2);'
            )

            def handle_logout() -> None:
                nicegui_app.storage.user.clear()
                ui.navigate.to('/login')

            ui.button(
                icon='logout', on_click=handle_logout,
            ).props('flat round').style(
                f'color: {COLORS["text_muted"]};'
            ).tooltip('Abmelden')


def _sidebar() -> None:
    current_role = nicegui_app.storage.user.get('role', '')
    nav_items    = _load_nav_items(current_role)

    with ui.left_drawer(fixed=True).style(
        f'background-color: {COLORS["sidebar_bg"]}; '
        'padding: 8px 0; '
        'width: 220px;'
    ):
        ui.separator().style(
            'background-color: rgba(255,255,255,0.1); margin: 0;'
        )
        # ← ui.space() weg, simples margin stattdessen
        ui.element('div').style('height: 8px;')

        for item in nav_items:
            _nav_item(item.label, item.icon, item.path)


def _nav_item(label: str, icon: str, path: str) -> None:
    with ui.row().style(
        'align-items: center; gap: 12px; padding: 10px 20px; '
        'cursor: pointer; transition: background 0.15s ease;'
    ).classes('nav-item').on('click', lambda p=path: ui.navigate.to(p)):
        ui.icon(icon).style(f'color: {COLORS["text_muted"]}; font-size: 20px;')
        ui.label(label).style(f'color: {COLORS["text_muted"]}; font-size: 14px;')


@contextmanager
def main_layout() -> Generator[None, None, None]:
    _header()
    _sidebar()

    with ui.column().style(
        f'background-color: {COLORS["content_bg"]}; '
        'padding: 24px; '
        'width: 100%; '
        'min-height: 100vh;'
    ):
        yield
# app/components/layout.py
from typing import Callable
from nicegui import ui, app as nicegui_app
from app.core.database import get_session
from app.models.menu_item import MenuItem
from app.config import APP_TITLE, APP_LOGO


COLORS = {
    'sidebar_bg':  '#1e3a5f',
    'header_bg':   '#0f2744',
    'app_title':   '#b2945d',
    'accent':      '#0078d4',
    'text_light':  '#ffffff',
    'text_muted':  '#c7d8ec',
    'content_bg':  '#f3f6f9',
}

# Gemeinsame Basis für aktive/inaktive Nav-Items
_NAV_ROW_BASE = (
    'align-items: center; gap: 12px; padding: 10px 20px; '
    'cursor: pointer; transition: background 0.15s ease; '
)


def _apply_active(row: ui.row) -> None:
    row.style(
        _NAV_ROW_BASE +
        f'background-color: {COLORS["accent"]}; '
        'border-left: 3px solid white;'
    )


def _apply_inactive(row: ui.row) -> None:
    row.style(
        _NAV_ROW_BASE +
        'background-color: transparent; '
        'border-left: 3px solid transparent;'
    )


def _load_nav_items(current_role: str) -> list[MenuItem]:
    with get_session() as session:
        items = (
            session.query(MenuItem)
            .order_by(MenuItem.sort_order)
            .all()
        )
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
                f'color: {COLORS["app_title"]}; '
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
                'width: 1px; height: 24px; '
                'background-color: rgba(255,255,255,0.2);'
            )

            def handle_logout() -> None:
                nicegui_app.storage.user.clear()
                ui.navigate.to('/login')

            ui.button(
                icon='logout', on_click=handle_logout,
            ).props('flat round').style(
                f'color: {COLORS["text_muted"]};'
            ).tooltip('Abmelden')


def _sidebar(navigate: Callable, current_path: str = '/') -> dict[str, ui.row]:
    current_role = nicegui_app.storage.user.get('role', '')
    nav_items    = _load_nav_items(current_role)
    nav_refs: dict[str, ui.row] = {}

    with ui.left_drawer(fixed=True).style(
        f'background-color: {COLORS["sidebar_bg"]}; '
        'padding: 8px 0; width: 220px;'
    ):
        ui.separator().style('background-color: rgba(255,255,255,0.1); margin: 0;')
        ui.element('div').style('height: 8px;')

        for item in nav_items:
            row = _nav_item(
                item.label, item.icon, item.path,
                navigate,
                active=(item.path == current_path),
            )
            nav_refs[item.path] = row

    return nav_refs


def _nav_item(
    label: str,
    icon: str,
    path: str,
    navigate: Callable,
    active: bool = False,
) -> ui.row:
    row = (
        ui.row()
        .style(_NAV_ROW_BASE + 'border-left: 3px solid transparent;')
        .classes('nav-item')
        .on('click', lambda p=path: navigate(p))
    )
    with row:
        ui.icon(icon).style(f'color: {COLORS["text_muted"]}; font-size: 20px;')
        ui.label(label).style(f'color: {COLORS["text_muted"]}; font-size: 14px;')

    if active:
        _apply_active(row)

    return row


def main_layout(
    navigate: Callable,
    current_path: str = '/',
) -> tuple[ui.column, dict[str, ui.row]]:
    _header()
    nav_refs = _sidebar(navigate, current_path)
    content  = ui.column().style(
        f'background-color: {COLORS["content_bg"]}; '
        'padding: 24px; width: 100%; min-height: 100vh;'
    )
    return content, nav_refs
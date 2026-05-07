# app/components/layout.py
from typing import Callable

from nicegui import app as nicegui_app
from nicegui import ui

from app.config import APP_LOGO, APP_TITLE
from app.core.database import get_session
from app.models.menu_item import MenuItem

COLORS = {
    "sidebar_bg": "#1e3a5f",
    "header_bg": "#0f2744",
    "app_title": "#b2945d",
    "accent": "#0078d4",
    "text_light": "#ffffff",
    "text_muted": "#c7d8ec",
    "content_bg": "#f3f6f9",
}

# Gemeinsame Basis-Klassen für die Navigation (Flexbox, Abstände, Cursor, Transition)
_NAV_ROW_BASE_CLASSES = "items-center gap-3 px-5 py-[10px] cursor-pointer transition-colors duration-150 border-l-[3px]"


def _apply_active(row: ui.row) -> None:
    row.classes(
        add=f'bg-[{COLORS["accent"]}] border-white',
        remove="bg-transparent border-transparent",
    )


def _apply_inactive(row: ui.row) -> None:
    row.classes(
        add="bg-transparent border-transparent",
        remove=f'bg-[{COLORS["accent"]}] border-white',
    )


def _load_nav_items(current_role: str) -> list[MenuItem]:
    with get_session() as session:
        items = session.query(MenuItem).order_by(MenuItem.sort_order).all()
        return [
            i for i in items if not i.roles_list() or current_role in i.roles_list()
        ]


def _header() -> None:
    # Der Haupt-Header mit items-center (zentriert beide Child-Rows vertikal)
    with ui.header().classes(
        f'bg-[{COLORS["header_bg"]}] h-[56px] px-[16px] flex items-center justify-between'
    ):
        # LINKE SEITE
        with ui.row().classes("items-center !gap-[10px]", remove="gap-4"):
            ui.image(APP_LOGO).classes("h-[28px] w-[28px]")
            ui.label(APP_TITLE).classes(
                f'text-[{COLORS["app_title"]}] text-[18px] font-semibold tracking-[0.5px] leading-none'
            )

        # RECHTE SEITE
        with ui.row().classes("items-center !gap-[16px]", remove="gap-4"):
            username = nicegui_app.storage.user.get("username", "")
            role = nicegui_app.storage.user.get("role", "")

            ui.icon("account_circle").classes(
                f'text-[{COLORS["app_title"]}] text-[24px] leading-none'
            )
            ui.label(f"{username} ({role})").classes(
                f'text-[{COLORS["app_title"]}] text-[13px] leading-none'
            )

            ui.separator().classes("w-[1px] h-[24px] bg-white/20")

            def handle_logout() -> None:
                nicegui_app.storage.user.clear()
                ui.navigate.to("/login")

            # Der Button ist durch 'dense' von Haus aus kompakt und zentriert sich im items-center Container perfekt mit
            ui.button(icon="logout", on_click=handle_logout, color=None).props(
                "flat round dense"
            ).classes(f'!text-[{COLORS["app_title"]}]').tooltip("Abmelden")


def _sidebar(navigate: Callable, current_path: str = "/") -> dict[str, ui.row]:
    current_role = nicegui_app.storage.user.get("role", "")
    nav_items = _load_nav_items(current_role)
    nav_refs: dict[str, ui.row] = {}

    with ui.left_drawer(fixed=True).classes(
        f'bg-[{COLORS["sidebar_bg"]}] py-2 w-[220px]'
    ):
        ui.separator().classes("bg-white/10 m-0")
        ui.element("div").classes("h-2")

        for item in nav_items:
            row = _nav_item(
                item.label,
                item.icon,
                item.path,
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
        .classes(f"{_NAV_ROW_BASE_CLASSES} bg-transparent border-transparent nav-item")
        .on("click", lambda p=path: navigate(p))
    )
    with row:
        ui.icon(icon).classes(f'text-[{COLORS["text_muted"]}] text-[20px]')
        ui.label(label).classes(f'text-[{COLORS["text_muted"]}] text-[14px]')

    if active:
        _apply_active(row)

    return row


def main_layout(
    navigate: Callable,
    current_path: str = "/",
) -> tuple[ui.column, dict[str, ui.row]]:
    _header()
    nav_refs = _sidebar(navigate, current_path)
    content = ui.column().classes(
        f'bg-[{COLORS["content_bg"]}] p-6 w-full min-h-screen'
    )
    return content, nav_refs

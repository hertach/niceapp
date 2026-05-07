# app/pages/dashboard.py
from nicegui import app, ui
from sqlalchemy import func

from app.core.database import get_session
from app.models.menu_item import MenuItem
from app.models.role import Role
from app.models.user import User

# Farben passend zum COLORS-Dict in layout.py
CARD_COLORS = {
    "users": {"bg": "#EFF6FF", "accent": "#2563EB", "icon_color": "text-blue-600"},
    "roles": {"bg": "#F0FDF4", "accent": "#16A34A", "icon_color": "text-green-600"},
    "menu_items": {
        "bg": "#FFF7ED",
        "accent": "#EA580C",
        "icon_color": "text-orange-600",
    },
}

# Pfade müssen mit Seed-Daten in database.py übereinstimmen
_ADMIN_ACTIONS = [
    ("Benutzer verwalten", "group", "/admin/users"),
    ("Rollen verwalten", "admin_panel_settings", "/admin/roles"),
    ("Menü verwalten", "menu", "/admin/menu"),
]


def _get_stats() -> dict[str, int]:
    """Holt Live-Zahlen aus der DB."""
    with get_session() as session:
        return {
            "users": session.scalar(func.count(User.id)) or 0,
            "roles": session.scalar(func.count(Role.id)) or 0,
            "menu_items": session.scalar(func.count(MenuItem.id)) or 0,
        }


def _stat_card(
    title: str,
    value: int,
    icon: str,
    subtitle: str,
    bg: str,
    accent: str,
    icon_color: str,
) -> None:
    # Stat-Card mit Tailwind-Klassen für 1:1 Design
    with ui.card().classes(
        f"bg-[{bg}] border border-[{accent}33] rounded-[12px] p-4 px-5 border-l-4 border-l-[{accent}] flex-1 min-w-[240px]"
    ):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-0"):
                ui.label(title).classes(
                    "text-[13px] font-medium text-slate-500 uppercase tracking-wider"
                )
                ui.label(str(value)).classes(
                    "text-[32px] font-bold text-slate-800 leading-none mt-1"
                )
            ui.icon(icon).classes(f"{icon_color} text-[40px] opacity-80")

        ui.label(subtitle).classes("text-[12px] text-slate-400 mt-2 italic")


def _section_header(title: str, subtitle: str) -> None:
    with ui.column().classes("gap-0 mb-2"):
        ui.label(title).classes("text-[20px] font-semibold text-[#1e3a5f]")
        ui.label(subtitle).classes("text-[13px] text-[#64748b]")


def _quick_action(label: str, icon: str, path: str, navigate) -> None:
    with (
        ui.card()
        .classes(
            "w-[160px] h-[100px] p-3 bg-white border border-[#e2e8f0] rounded-[8px] cursor-pointer hover:bg-slate-50 transition-colors"
        )
        .on("click", lambda: navigate(path))
    ):
        with ui.column().classes("items-center justify-center w-full h-full gap-1"):
            ui.icon(icon).classes("text-[#0078d4] text-[28px]")
            ui.label(label).classes("text-[12px] font-medium text-center leading-tight")


def dashboard_page(navigate) -> None:
    role = app.storage.user.get("role", "")
    stats = _get_stats()

    with ui.column().classes("w-full gap-6"):
        # Willkommens-Bereich
        _section_header("Dashboard Übersicht", "Aktuelle Kennzahlen und Schnellzugriff")

        # Statistik-Karten
        with ui.row().classes("w-full gap-4 flex-wrap"):
            _stat_card(
                title="Benutzer",
                value=stats["users"],
                icon="people",
                subtitle="registrierte Konten",
                **CARD_COLORS["users"],
            )
            _stat_card(
                title="Rollen",
                value=stats["roles"],
                icon="admin_panel_settings",
                subtitle="Berechtigungsgruppen",
                **CARD_COLORS["roles"],
            )
            _stat_card(
                title="Menüpunkte",
                value=stats["menu_items"],
                icon="menu",
                subtitle="Navigationselemente",
                **CARD_COLORS["menu_items"],
            )

        ui.separator().classes("m-0")

        # Quick Actions – nur für Admins
        if role == "admin":
            _section_header("Schnellzugriff", "Direkt zu den Verwaltungsseiten")
            with ui.row().classes("gap-3 flex-wrap"):
                for label, icon, path in _ADMIN_ACTIONS:
                    _quick_action(label, icon, path, navigate)

        ui.separator().classes("m-0")

        # Info-Banner
        with ui.card().classes(
            "bg-[linear-gradient(135deg,#EFF6FF_0%,#E0E7FF_100%)] rounded-[12px] p-4 px-5 border-none w-full"
        ):
            with ui.row().classes("items-center gap-3"):
                ui.icon("info").classes("text-[#2563EB] text-[22px]")
                ui.label(
                    "Dies ist ein NiceGUI SPA-Template. "
                    "Erweitere das Dashboard nach Bedarf mit deinen eigenen Widgets."
                ).classes("text-[14px] text-blue-900")

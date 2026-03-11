from nicegui import ui, app
from sqlalchemy import func
from app.core.database import get_session
from app.core.auth import check_access


# ── Farben passend zum bestehenden COLORS-Dict im Layout ──────────────────────
CARD_COLORS = {
    "users":      {"bg": "#EFF6FF", "accent": "#2563EB", "icon_color": "text-blue-600"},
    "roles":      {"bg": "#F0FDF4", "accent": "#16A34A", "icon_color": "text-green-600"},
    "menu_items": {"bg": "#FFF7ED", "accent": "#EA580C", "icon_color": "text-orange-600"},
    "sessions":   {"bg": "#FAF5FF", "accent": "#9333EA", "icon_color": "text-purple-600"},
}


def _get_stats() -> dict:
    """Holt Live-Zahlen aus der DB."""
    from app.models.user import User
    from app.models.role import Role
    from app.models.menu_item import MenuItem

    with get_session() as session:
        return {
            "users":      session.scalar(func.count(User.id))      or 0,
            "roles":      session.scalar(func.count(Role.id))      or 0,
            "menu_items": session.scalar(func.count(MenuItem.id))  or 0,
        }


def _stat_card(
    title: str,
    value: int,
    icon: str,
    bg: str,
    accent: str,
    icon_color: str,
    subtitle: str = "",
) -> None:
    """Rendert eine einzelne Statistik-Karte."""
    with ui.card().style(
        f"background:{bg}; border-left:4px solid {accent}; "
        "border-radius:12px; padding:20px; min-width:180px; "
        "flex:1; box-shadow:0 2px 8px rgba(0,0,0,0.06); "
        "transition: box-shadow .2s, transform .2s;"
    ).classes("cursor-default").on(
        "mouseenter",
        js_handler="(e) => { e.currentTarget.style.boxShadow='0 6px 20px rgba(0,0,0,0.12)'; "
                   "e.currentTarget.style.transform='translateY(-2px)'; }",
    ).on(
        "mouseleave",
        js_handler="(e) => { e.currentTarget.style.boxShadow='0 2px 8px rgba(0,0,0,0.06)'; "
                   "e.currentTarget.style.transform='translateY(0)'; }",
    ):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-0"):
                ui.label(title).style(
                    "font-size:12px; font-weight:600; letter-spacing:.06em; "
                    "text-transform:uppercase; color:#6B7280;"
                )
                ui.label(str(value)).style(
                    f"font-size:36px; font-weight:700; color:{accent}; line-height:1.1;"
                )
                if subtitle:
                    ui.label(subtitle).style("font-size:12px; color:#9CA3AF; margin-top:2px;")

            ui.icon(icon, size="40px").classes(icon_color).style("opacity:.75;")


def _section_header(title: str, subtitle: str = "") -> None:
    with ui.column().classes("gap-0 mb-2"):
        ui.label(title).style(
            "font-size:18px; font-weight:700; color:#111827;"
        )
        if subtitle:
            ui.label(subtitle).style("font-size:13px; color:#6B7280;")


def _quick_action(label: str, icon: str, path: str, navigate) -> None:
    """Kleiner klickbarer Quick-Action-Chip."""
    with ui.button(icon=icon, on_click=lambda: navigate(path)).props(
        "flat no-caps"
    ).style(
        "border:1px solid #E5E7EB; border-radius:8px; padding:8px 16px; "
        "color:#374151; background:#fff; font-size:13px; font-weight:500; "
        "gap:6px; transition: background .15s, border-color .15s;"
    ).on(
        "mouseenter",
        js_handler="(e) => { e.currentTarget.style.background='#F9FAFB'; "
                   "e.currentTarget.style.borderColor='#D1D5DB'; }",
    ).on(
        "mouseleave",
        js_handler="(e) => { e.currentTarget.style.background='#fff'; "
                   "e.currentTarget.style.borderColor='#E5E7EB'; }",
    ):
        ui.label(label).style("font-size:13px;")


def dashboard_page(navigate) -> None:
    """
    Haupt-Einstiegspunkt – wird von main.py in der PAGES-Registry registriert.

    Usage in main.py:
        from app.pages.dashboard import dashboard_page

        @page('/')
        def _dashboard() -> None:
            dashboard_page(navigate)
    """
    username: str = app.storage.user.get("username", "Benutzer")
    role: str     = app.storage.user.get("role", "")
    stats         = _get_stats()

    with ui.column().classes("w-full gap-6").style("padding:24px; max-width:960px;"):

        # ── Begrüssung ─────────────────────────────────────────────────────────
        with ui.row().classes("items-center justify-between w-full"):
            with ui.column().classes("gap-0"):
                ui.label(f"Guten Tag, {username} 👋").style(
                    "font-size:24px; font-weight:700; color:#111827;"
                )
                ui.label("Hier ist eine Übersicht über dein System.").style(
                    "font-size:14px; color:#6B7280;"
                )
            ui.badge(role, color="blue").style(
                "font-size:12px; padding:4px 10px; border-radius:999px;"
            )

        ui.separator().style("margin:0;")

        # ── Statistik-Karten ────────────────────────────────────────────────────
        _section_header("System-Übersicht", "Aktuelle Datenbankzahlen")

        with ui.row().classes("w-full gap-4 flex-wrap"):
            _stat_card(
                title="Benutzer",
                value=stats["users"],
                icon="group",
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

        ui.separator().style("margin:0;")

        # ── Quick Actions (nur Admin) ───────────────────────────────────────────
        if role == "admin":
            _section_header("Schnellzugriff", "Direkt zu den Verwaltungsseiten")
            with ui.row().classes("gap-3 flex-wrap"):
                _quick_action("Benutzer verwalten", "group",              "/admin/users",      navigate)
                _quick_action("Rollen verwalten",   "admin_panel_settings","/admin/roles",      navigate)
                _quick_action("Menü verwalten",     "menu",               "/admin/menu_items", navigate)

        ui.separator().style("margin:0;")

        # ── Info-Banner ─────────────────────────────────────────────────────────
        with ui.card().style(
            "background:linear-gradient(135deg,#EFF6FF 0%,#E0E7FF 100%); "
            "border-radius:12px; padding:16px 20px; border:none;"
        ).classes("w-full"):
            with ui.row().classes("items-center gap-3"):
                ui.icon("info", size="22px").style("color:#2563EB;")
                ui.label(
                    "Dies ist ein NiceGUI SPA-Template. "
                    "Erweiter das Dashboard nach Bedarf mit deinen eigenen Widgets."
                ).style("font-size:13px; color:#1E40AF;")
# app/pages/admin/settings.py
from nicegui import ui

from app.pages.admin.app_settings import app_settings_page
from app.pages.admin.company_settings import company_settings_page
from app.pages.admin.finance_settings import finance_settings_page
from app.pages.admin.logs import logs_page
from app.pages.admin.menu_items import menu_items_page
from app.pages.admin.roles import roles_page
from app.pages.admin.template_settings import template_settings_page
from app.pages.admin.users import users_page


def settings_page() -> None:
    # State-Variable, um sich den aktuellen Tab zu merken
    active_tab = "users"

    # ── Hauptlayout der Settings-Seite (Flexbox Row) ──
    # min-w-0 ist wichtig, damit Tabellen den rechten Bereich nicht "sprengen"
    with ui.row().classes("w-full flex-nowrap items-start min-h-[calc(100vh-120px)]"):

        # Linke Sidebar (Kategorien)
        menu_container = ui.column().classes(
            "w-[240px] shrink-0 border-r border-[#e2e8f0] h-full pr-4 gap-1"
        )

        # Rechter Inhaltsbereich
        content_container = ui.column().classes("flex-1 pl-6 min-w-0 w-full")

    def render_menu() -> None:
        """Rendert die linke Navigationsleiste neu, um den aktiven Tab zu markieren."""
        menu_container.clear()
        with menu_container:
            ui.label("Einstellungen").classes(
                "text-[18px] font-semibold text-[#1e3a5f] mb-2 px-3"
            )

            def menu_item(tab_id: str, label: str, icon: str):
                is_active = active_tab == tab_id

                # PyCharm-ähnliches Styling für aktive/inaktive Tabs
                bg_class = (
                    "bg-[#eef2ff] text-[#0078d4]"
                    if is_active
                    else "text-[#475569] hover:bg-slate-100"
                )
                font_weight = "font-semibold" if is_active else "font-medium"

                with (
                    ui.row()
                    .classes(
                        f"w-full items-center gap-3 px-3 py-2 rounded-[6px] cursor-pointer transition-colors {bg_class}"
                    )
                    .on("click", lambda: load_tab(tab_id))
                ):
                    ui.icon(icon).classes("text-[20px]")
                    ui.label(label).classes(f"text-[14px] {font_weight}")

            # Hier definieren wir unsere Menüpunkte
            menu_item("users", "Benutzer", "people")
            menu_item("roles", "Rollen", "admin_panel_settings")
            menu_item("menu", "Menüpunkte", "menu")
            menu_item("company_settings", "Firmenangaben", "business")
            menu_item("template_settings", "Vorlagen", "description")
            menu_item("finance_settings", "Finanz-Einstellungen", "price_change")
            menu_item("app_settings", "App-Einstellungen", "settings_applications")
            menu_item("logs", "System-Logs", "list_alt")

    def load_tab(tab_id: str) -> None:
        """Wechselt den Tab und lädt den entsprechenden Inhalt im rechten Bereich."""
        nonlocal active_tab
        active_tab = tab_id

        # 1. Menü neu rendern (damit die blaue Markierung wechselt)
        render_menu()

        # 2. Rechten Bereich leeren und die bestehenden Admin-Seiten reinladen
        content_container.clear()
        with content_container:
            if tab_id == "users":
                users_page()
            elif tab_id == "roles":
                roles_page()
            elif tab_id == "menu":
                menu_items_page()
            elif tab_id == "company_settings":
                company_settings_page()
            elif tab_id == "template_settings":
                template_settings_page()
            elif tab_id == "finance_settings":
                finance_settings_page()
            elif tab_id == "app_settings":
                app_settings_page()
            elif tab_id == "logs":
                logs_page()

    # Initianlen Start-Tab laden
    load_tab("users")

# app/components/inputs.py
import json
from typing import Callable

from nicegui import ui

from app.config import GERMAN_LOCALE  # Wir verschieben die Config gleich


def new_button(on_click: Callable, label: str = "Neu") -> ui.button:
    """Einheitlicher 'Neu'-Button (outline, blau, mit Plus-Icon)."""
    return (
        ui.button(label, icon="add", on_click=on_click)
        .props("outline dense")
        .classes("text-[#0078d4] px-2")
    )


def date_input(label: str, value: str = "", placeholder: str = "TT.MM.JJJJ"):
    """Erstellt ein deutsches Datums-Eingabefeld mit Kalender-Picker."""
    with (
        ui.input(label=label, value=value, placeholder=placeholder)
        .props("dense")
        .classes("flex-1") as i
    ):
        with i.add_slot("append"):
            ui.icon("edit_calendar").on("click", lambda: menu.open()).classes(
                "cursor-pointer"
            )
        with ui.menu() as menu:
            ui.date(mask="DD.MM.YYYY").bind_value(i).props(
                f":locale='{json.dumps(GERMAN_LOCALE)}'"
            )
    return i

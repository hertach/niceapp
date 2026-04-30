import json
from nicegui import ui
from app.config import GERMAN_LOCALE # Wir verschieben die Config gleich

def date_input(label: str, value: str = '', placeholder: str = 'TT.MM.JJJJ'):
    """Erstellt ein deutsches Datums-Eingabefeld mit Kalender-Picker."""
    with ui.input(label=label, value=value, placeholder=placeholder).props('dense').style('flex: 1;') as i:
        with i.add_slot('append'):
            ui.icon('edit_calendar').on('click', lambda: menu.open()).classes('cursor-pointer')
        with ui.menu() as menu:
            ui.date(mask='DD.MM.YYYY') \
                .bind_value(i) \
                .props(f':locale=\'{json.dumps(GERMAN_LOCALE)}\'')
    return i
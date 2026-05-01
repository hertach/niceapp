# app/components/directory_picker.py
from pathlib import Path
from nicegui import ui


class DirectoryPicker(ui.dialog):
    def __init__(self, initial_path: str = '.'):
        super().__init__()

        # Versuche den Startpfad aufzulösen, ansonsten nimm das aktuelle Verzeichnis
        try:
            self.path = Path(initial_path).resolve()
        except Exception:
            self.path = Path('.').resolve()

        with self, ui.card().classes('w-[500px] h-[600px] flex flex-col p-6'):
            ui.label('Verzeichnis auswählen').classes('text-[18px] font-semibold text-[#1e3a5f] mb-2')

            # Zeigt den aktuell ausgewählten Pfad an
            self.path_label = ui.label(str(self.path)).classes('text-[13px] text-gray-500 mb-4 truncate w-full')

            # Container für die Ordner-Liste (scrollbar)
            self.container = ui.column().classes(
                'w-full flex-1 overflow-y-auto border border-gray-200 rounded p-2 gap-0')

            with ui.row().classes('w-full justify-end mt-4 gap-2'):
                ui.button('Abbrechen', on_click=self.close).props('flat text-color="grey"')
                ui.button('Auswählen', on_click=lambda: self.submit(str(self.path))).props('unelevated').classes(
                    'bg-[#0078d4] text-white')

        self.update_list()

    def update_list(self):
        """Lädt die Ordner des aktuellen Verzeichnisses."""
        self.container.clear()
        self.path_label.set_text(str(self.path))

        with self.container:
            # "Nach oben" (..) Button
            if self.path.parent != self.path:
                with ui.row().classes(
                        'items-center gap-2 cursor-pointer hover:bg-blue-50 w-full p-2 rounded transition-colors').on(
                        'click', lambda: self.navigate(self.path.parent)):
                    ui.icon('folder_open', color='primary').classes('text-[20px]')
                    ui.label('.. (Eine Ebene nach oben)').classes('text-[14px]')

            try:
                # Lese alle Unterordner (ignoriere versteckte Ordner und Dateien)
                dirs = [d for d in self.path.iterdir() if d.is_dir() and not d.name.startswith('.')]

                # Alphabetisch sortieren
                for d in sorted(dirs, key=lambda x: x.name.lower()):
                    with ui.row().classes(
                            'items-center gap-2 cursor-pointer hover:bg-blue-50 w-full p-2 rounded transition-colors').on(
                            'click', lambda p=d: self.navigate(p)):
                        ui.icon('folder', color='primary').classes('text-[20px]')
                        ui.label(d.name).classes('text-[14px]')

            except PermissionError:
                ui.label('Zugriff verweigert').classes('text-red-500 text-[14px] p-2')
            except Exception as e:
                ui.label(f'Fehler: {str(e)}').classes('text-red-500 text-[14px] p-2')

    def navigate(self, new_path: Path):
        """Wechselt das Verzeichnis und rendert die Liste neu."""
        self.path = new_path
        self.update_list()
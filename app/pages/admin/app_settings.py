# app/pages/admin/app_settings.py
from nicegui import ui
from app.core.database import get_session
from app.models.app_setting import AppSetting
from app.core.logger import update_console_logger

# NEU: Den Picker importieren
from app.components.directory_picker import DirectoryPicker


def app_settings_page() -> None:
    ui.label('System-Einstellungen').classes('text-[24px] font-semibold text-[#1e3a5f] mb-4')

    with get_session() as session:
        setting = session.query(AppSetting).first()
        if not setting:
            setting = AppSetting()
            session.add(setting)
            session.commit()
            session.refresh(setting)

        current_backup_path = setting.backup_path
        current_log_terminal = setting.log_to_terminal

    with ui.card().classes('w-full max-w-3xl p-8 shadow-sm border border-slate-200'):

        with ui.column().classes('w-full gap-6'):
            ui.label('Backup-Konfiguration').classes('font-medium text-slate-700')
            async def open_picker():
                # Wir übergeben den aktuell eingetippten Pfad als Startpunkt
                result = await DirectoryPicker(backup_input.value or '.')
                if result:
                    backup_input.value = result  # Schreibt den gewählten Pfad ins Textfeld

            backup_input = ui.input(
                label='Backup-Verzeichnis (Pfad)',
                value=current_backup_path,
                placeholder='./backups'
            ).classes('w-full').props('outlined dense')

            # ── NEU: Der Button direkt im Input-Feld ──
            with backup_input.add_slot('append'):
                ui.button(icon='folder', on_click=open_picker).props('flat round dense')

            ui.separator().props('dense')
            ui.label('Log-Konfiguration').classes('font-medium text-slate-700')
            terminal_toggle = ui.switch(
                'Logs zusätzlich im Terminal ausgeben',
                value=current_log_terminal
            ).classes('text-slate-700')

        def save_settings():
            with get_session() as session:
                s = session.query(AppSetting).first()
                s.backup_path = backup_input.value
                s.log_to_terminal = terminal_toggle.value
                session.commit()

            update_console_logger(terminal_toggle.value)
            ui.notify('Einstellungen erfolgreich gespeichert ✅', type='positive')

        with ui.row().classes('w-full justify-end mt-8'):
            ui.button('Speichern', icon='save', on_click=save_settings).props('unelevated').classes(
                'bg-[#0078d4] text-white')
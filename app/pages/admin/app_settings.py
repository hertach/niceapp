# app/pages/admin/app_settings.py
from nicegui import ui
from app.core.database import get_session
from app.models.app_setting import AppSetting
from app.core.logger import update_console_logger
from app.components.directory_picker import DirectoryPicker
from app.core.backup import perform_backup


def app_settings_page() -> None:
    ui.label('System-Einstellungen').classes('text-[24px] font-semibold text-[#1e3a5f] mb-4')

    with get_session() as session:
        setting = session.query(AppSetting).first()
        if not setting:
            setting = AppSetting()
            session.add(setting)
            session.commit()
            session.refresh(setting)

        # BACKUP
        current_backup_path = setting.backup_path
        current_backup_on_close = setting.backup_on_close
        current_backup_schedule = setting.backup_schedule
        # LOGGING
        current_log_terminal = setting.log_to_terminal
        # STREAMING INTERVAL
        current_streaming_interval = setting.streaming_interval

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

            with backup_input.add_slot('append'):
                ui.button(icon='folder', on_click=open_picker).props('flat round dense')

            backup_on_close_toggle = ui.switch(
                'Backup beim Schließen der App erstellen (Nativ / Server-Stop)',
                value=current_backup_on_close
            ).classes('text-slate-700')

            schedule_select = ui.select(
                options={'none': 'Nie (Nur manuell)', 'daily': 'Täglich', 'weekly': 'Wöchentlich'},
                label='Automatischer Backup-Plan (Hintergrund)',
                value=current_backup_schedule
            ).classes('w-full max-w-[300px]').props('outlined dense')

            def trigger_manual_backup():
                if perform_backup():
                    ui.notify('Backup erfolgreich erstellt ✅', type='positive')
                else:
                    ui.notify('Fehler beim Backup. Prüfe die Logs.', type='negative')

            ui.button('Backup jetzt erstellen', icon='save_alt', on_click=trigger_manual_backup).props(
                'outline').classes('text-[#0078d4]')

            #-- LOGGING--
            ui.separator().props('dense')
            ui.label('Log-Konfiguration').classes('font-medium text-slate-700')
            terminal_toggle = ui.switch(
                'Logs zusätzlich im Terminal ausgeben',
                value=current_log_terminal
            ).classes('text-slate-700')
            # -- STREAMING INTERVAL --
            ui.separator().props('dense')
            ui.label('Spracherkennung').classes('font-medium text-slate-700')
            streaming_interval = ui.input(
                label='Interval',
                value=current_streaming_interval,
                placeholder='0.5'
            ).classes('w-full').props('outlined dense type="number" step="0.05"')


        def save_settings():
            with get_session() as session:
                s = session.query(AppSetting).first()
                s.backup_path = backup_input.value
                s.backup_on_close = backup_on_close_toggle.value
                s.backup_schedule = schedule_select.value
                s.log_to_terminal = terminal_toggle.value
                s.streaming_interval = ''
                session.commit()

            update_console_logger(terminal_toggle.value)
            ui.notify('Einstellungen erfolgreich gespeichert ✅', type='positive')

        with ui.row().classes('w-full justify-end mt-8'):
            ui.button('Speichern', icon='save', on_click=save_settings).props('unelevated').classes(
                'bg-[#0078d4] text-white')
# app/pages/admin/app_settings.py
from nicegui import ui

from app.components.directory_picker import DirectoryPicker
from app.core.backup import perform_backup
from app.core.database import get_session
from app.core.logger import set_log_level, update_console_logger
from app.models.app_setting import AppSetting


def app_settings_page() -> None:
    ui.label("System-Einstellungen").classes(
        "text-[24px] font-semibold text-[#1e3a5f] mb-4"
    )

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
        current_log_level = setting.log_level or "WARNING"
        # STREAMING INTERVAL
        current_streaming_interval = setting.streaming_interval
        # UPLOAD DIRECTORIES
        current_upload_logos = setting.upload_path_logos or "./data/uploads/logos"
        current_upload_templates = (
            setting.upload_path_templates or "./data/uploads/templates"
        )
        current_upload_patient_documents = (
                setting.upload_path_patient_documents or "./data/uploads/client_files"
        )
        current_upload_misc = (
                setting.upload_path_misc or "./data/uploads/misc"
        )
        # PDF-PASSWORT
        current_pdf_password = setting.pdf_password or ""

    with ui.card().classes("w-full max-w-3xl p-8 shadow-sm border border-slate-200"):

        with ui.column().classes("w-full gap-6"):

            async def open_picker():
                # Wir übergeben den aktuell eingetippten Pfad als Startpunkt
                result = await DirectoryPicker(backup_input.value or ".")
                if result:
                    backup_input.value = (
                        result  # Schreibt den gewählten Pfad ins Textfeld
                    )

            async def pick_dir(input_element):
                result = await DirectoryPicker(input_element.value or ".")
                if result:
                    input_element.value = result

            ui.label("Upload-Pfade Logos & Vorlagen").classes("font-medium text-slate-700")
            # Logos
            logo_input = (
                ui.input("Verzeichnis für Logos", value=current_upload_logos)
                .classes("w-full")
                .props("outlined dense")
            )
            with logo_input.add_slot("append"):
                ui.button(icon="folder", on_click=lambda: pick_dir(logo_input)).props(
                    "flat round dense"
                )

            # Vorlagen
            template_input = (
                ui.input("Verzeichnis für Vorlagen", value=current_upload_templates)
                .classes("w-full")
                .props("outlined dense")
            )
            with template_input.add_slot("append"):
                ui.button(
                    icon="folder", on_click=lambda: pick_dir(template_input)
                ).props("flat round dense")

            ui.separator().props("dense")
            ui.label("Upload/Speicher-Pfad Klienten-Dateien").classes("font-medium text-slate-700")
            # Path Patient Documents
            patient_documents_input = (
                ui.input("Verzeichnis für Klienten-Files", value=current_upload_patient_documents)
                .classes("w-full")
                .props("outlined dense")
            )
            with patient_documents_input.add_slot("append"):
                ui.button(
                    icon="folder", on_click=lambda: pick_dir(patient_documents_input)
                ).props("flat round dense")

            ui.separator().props("dense")
            ui.label("Upload-Pfad sonstige Dateien").classes("font-medium text-slate-700")
            # Path uploads misc
            misc_uploads_input = (
                ui.input("Verzeichnis für Uploads von sonstigen Dateien", value=current_upload_misc)
                .classes("w-full")
                .props("outlined dense")
            )
            with misc_uploads_input.add_slot("append"):
                ui.button(
                    icon="folder", on_click=lambda: pick_dir(misc_uploads_input)
                ).props("flat round dense")
            ui.separator().props("dense")

            ui.label("PDF-Dateiverschlüsselung").classes("font-medium text-slate-700")
            ui.label(
                "Dieses Passwort wird für alle neu erstellten Patienten-PDFs verwendet "
                "(Rechnungen, Quittungen, Stornos). "
                "Leer lassen = automatisch pro Patient abgeleitet."
            ).classes("text-xs text-slate-500 mb-1")
            ui.label(
                "⚠️  Passwortänderung gilt nur für neue Dateien. "
                "Bestehende Dateien behalten ihr ursprüngliches Passwort."
            ).classes("text-xs text-amber-700 bg-amber-50 p-2 rounded mb-2")
            pdf_password_input = (
                ui.input("Globales PDF-Passwort", value=current_pdf_password,
                         password=True, password_toggle_button=True)
                .classes("w-full max-w-sm")
                .props("outlined dense")
            )

            ui.separator().props("dense")
            ui.label("Backup-Konfiguration").classes("font-medium text-slate-700")
            backup_input = (
                ui.input(
                    label="Backup-Verzeichnis (Pfad)",
                    value=current_backup_path,
                    placeholder="./backups",
                )
                .classes("w-full")
                .props("outlined dense")
            )

            with backup_input.add_slot("append"):
                ui.button(icon="folder", on_click=open_picker).props("flat round dense")

            backup_on_close_toggle = ui.switch(
                "Backup beim Schließen der App erstellen (Nativ / Server-Stop)",
                value=current_backup_on_close,
            ).classes("text-slate-700")

            schedule_select = (
                ui.select(
                    options={
                        "none": "Nie (Nur manuell)",
                        "daily": "Täglich",
                        "weekly": "Wöchentlich",
                    },
                    label="Automatischer Backup-Plan (Hintergrund)",
                    value=current_backup_schedule,
                )
                .classes("w-full max-w-[300px]")
                .props("outlined dense")
            )

            def trigger_manual_backup():
                if perform_backup():
                    ui.notify("Backup erfolgreich erstellt ✅", type="positive")
                else:
                    ui.notify("Fehler beim Backup. Prüfe die Logs.", type="negative")

            ui.button(
                "Backup jetzt erstellen",
                icon="save_alt",
                on_click=trigger_manual_backup,
            ).props("outline").classes("text-[#0078d4]")

            # -- LOGGING--
            ui.separator().props("dense")
            ui.label("Log-Konfiguration").classes("font-medium text-slate-700")
            log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            level_select = (
                ui.select(
                    options=log_levels,
                    label="Aktives Log-Level",
                    value=current_log_level,
                    # Sofortige Anpassung bei Wechsel:
                    on_change=lambda e: set_log_level(e.value),
                )
                .classes("w-48")
                .props("outlined dense")
            )
            terminal_toggle = ui.switch(
                "Logs zusätzlich im Terminal ausgeben", value=current_log_terminal
            ).classes("text-slate-700")
            # -- STREAMING INTERVAL --
            ui.separator().props("dense")
            ui.label("Spracherkennung").classes("font-medium text-slate-700")
            streaming_interval = (
                ui.input(
                    label="Interval",
                    value=current_streaming_interval,
                    placeholder="0.5",
                )
                .classes("w-[150px]")
                .props('outlined dense type="number" step="0.05"')
            )

        def save_settings():
            with get_session() as session:
                s = session.query(AppSetting).first()
                s.upload_path_logos = logo_input.value
                s.upload_path_templates = template_input.value
                s.upload_path_patient_documents = patient_documents_input.value
                s.upload_path_misc = misc_uploads_input.value
                s.pdf_password = pdf_password_input.value.strip() or None
                s.backup_path = backup_input.value
                s.backup_on_close = backup_on_close_toggle.value
                s.backup_schedule = schedule_select.value
                s.log_level = level_select.value
                s.log_to_terminal = terminal_toggle.value
                s.streaming_interval = streaming_interval.value
                session.commit()

            update_console_logger(terminal_toggle.value)
            ui.notify("Einstellungen erfolgreich gespeichert ✅", type="positive")

        with ui.row().classes("w-full justify-end mt-8"):
            ui.button("Speichern", icon="save", on_click=save_settings).props(
                "unelevated"
            ).classes("bg-[#0078d4] text-white")

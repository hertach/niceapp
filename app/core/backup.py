# app/core/backup.py
import os
import shutil
import asyncio
from datetime import datetime, timedelta
from app.core.database import get_session
from app.models.app_setting import AppSetting
from app.core.logger import app_logger
from app.config import LOG_PATH, DB_PATH


def perform_backup() -> bool:
    """Führt das physische Backup der Datenbanken durch."""
    with get_session() as session:
        setting = session.query(AppSetting).first()
        if not setting or not setting.backup_path:
            app_logger.warning("Kein Backup-Pfad konfiguriert.")
            return False
        backup_dir = setting.backup_path

    # Ordner erstellen, falls er nicht existiert
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    try:
        # Haupt-Datenbank kopieren
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, os.path.join(backup_dir, f'app_backup_{timestamp}.db'))

        # Log-Datenbank kopieren
        if os.path.exists(LOG_PATH):
            shutil.copy2(LOG_PATH, os.path.join(backup_dir, f'log_backup_{timestamp}.db'))

        app_logger.info(f"Backup erfolgreich erstellt in: {backup_dir}")
        return True
    except Exception as e:
        app_logger.error(f"Fehler beim Erstellen des Backups: {e}")
        return False


def backup_on_shutdown():
    """Wird aufgerufen, wenn die NiceGUI-App geschlossen/beendet wird."""
    with get_session() as session:
        setting = session.query(AppSetting).first()
        if setting and setting.backup_on_close:
            app_logger.info("Auto-Backup beim Schließen der App gestartet...")
            perform_backup()


async def backup_scheduler_loop():
    """Hintergrund-Schleife, die periodisch prüft, ob ein Backup fällig ist."""
    while True:
        await asyncio.sleep(3600)  # Prüft jede Stunde (3600 Sekunden)
        try:
            with get_session() as session:
                setting = session.query(AppSetting).first()
                if not setting or setting.backup_schedule == 'none':
                    continue

                now = datetime.now()
                last = setting.last_backup

                needs_backup = False
                if setting.backup_schedule == 'daily':
                    if not last or now - last >= timedelta(days=1):
                        needs_backup = True
                elif setting.backup_schedule == 'weekly':
                    if not last or now - last >= timedelta(weeks=1):
                        needs_backup = True

                if needs_backup:
                    app_logger.info(f"Führe geplantes Backup aus ({setting.backup_schedule})...")
                    if perform_backup():
                        # Letzten Backup-Zeitpunkt in DB aktualisieren
                        setting.last_backup = now
                        session.commit()
        except Exception as e:
            app_logger.error(f"Fehler im Backup-Scheduler: {e}")
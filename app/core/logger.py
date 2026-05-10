# app/core/logger.py
import logging
import os
import shutil
from datetime import datetime

from sqlalchemy import text

from app.config import LOG_PATH
from app.models.log_entry import LogBase, LogEntry, LogSessionLocal, log_engine


class DatabaseLogHandler(logging.Handler):
    """Speichert Logs direkt in der separaten log.db."""

    def emit(self, record):
        try:
            with LogSessionLocal() as session:
                log_entry = LogEntry(
                    level=record.levelname,
                    module=record.name,
                    filename=record.filename,  # <-- Neu ausgelesen
                    func_name=record.funcName,  # <-- Neu ausgelesen
                    message=self.format(record),
                )
                session.add(log_entry)
                session.commit()
        except Exception:
            self.handleError(record)


console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("[%(levelname)s] [%(filename)s:%(funcName)s] %(message)s")
)


def set_log_level(level: str) -> None:
    """Ändert das Log-Level des globalen Loggers zur Laufzeit."""
    logger = logging.getLogger("niceapp")

    # Mapping von String auf die tatsächlichen logging Konstanten
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    # Sicherstellen, dass das Level gültig ist, ansonsten Fallback auf WARNING
    numeric_level = level_map.get(level.upper(), logging.WARNING)
    logger.setLevel(numeric_level)

    logger.info(f"Loglevel wurde auf {level} geändert.")


def setup_logger():
    """Initialisiert den globalen Logger der App."""
    logger = logging.getLogger("niceapp")
    logger.setLevel(logging.WARNING)
    if not logger.handlers:
        db_handler = DatabaseLogHandler()
        formatter = logging.Formatter("%(message)s")
        db_handler.setFormatter(formatter)
        logger.addHandler(db_handler)

        # Standardmäßig Konsole an (wird beim App-Start aus der DB überschrieben)
        logger.addHandler(console_handler)

    return logger


app_logger = setup_logger()


def update_console_logger(enable: bool):
    """Aktiviert oder deaktiviert den Output im Terminal zur Laufzeit."""
    logger = logging.getLogger("niceapp")
    if enable and console_handler not in logger.handlers:
        logger.addHandler(console_handler)
    elif not enable and console_handler in logger.handlers:
        logger.removeHandler(console_handler)


# ── Wartungs-Funktionen für die Datenbank ──


def clear_logs() -> None:
    """Löscht alle Einträge aus der Log-Tabelle."""
    with LogSessionLocal() as session:
        session.query(LogEntry).delete()
        session.commit()
    app_logger.info("Log-Datenbank wurde manuell geleert.")


def vacuum_logs() -> None:
    """Führt einen VACUUM-Befehl aus, um die Datenbank-Datei zu schrumpfen."""
    with log_engine.connect() as connection:
        # VACUUM muss außerhalb einer Transaktion laufen
        connection.execution_options(isolation_level="AUTOCOMMIT").execute(
            text("VACUUM")
        )
    app_logger.info("Log-Datenbank wurde komprimiert (VACUUM).")


def archive_logs() -> str:
    """Kopiert die log.db in ein Archiv und leert anschließend die aktuelle Tabelle."""
    db_path = LOG_PATH
    if not os.path.exists(db_path):
        return "Keine Datenbank zum Archivieren gefunden."

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = f"data/log_archive_{timestamp}.db"

    # Datei kopieren
    shutil.copy2(db_path, archive_path)

    # Aktuelle Tabelle leeren (nicht die Datei löschen, sonst bricht die SQLAlchemy Engine!)
    clear_logs()

    app_logger.info(f"Logs wurden archiviert nach: {archive_path}")
    return archive_path

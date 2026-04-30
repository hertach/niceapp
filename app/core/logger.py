# app/core/logger.py
import logging
from app.models.log_entry import LogEntry, LogSessionLocal


class DatabaseLogHandler(logging.Handler):
    """Speichert Logs direkt in der separaten log.db."""

    def emit(self, record):
        try:
            with LogSessionLocal() as session:
                log_entry = LogEntry(
                    level=record.levelname,
                    module=record.name,
                    message=self.format(record)
                )
                session.add(log_entry)
                session.commit()
        except Exception:
            self.handleError(record)


def setup_logger():
    """Initialisiert den globalen Logger der App."""
    logger = logging.getLogger('niceapp')
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        db_handler = DatabaseLogHandler()
        formatter = logging.Formatter('%(message)s')
        db_handler.setFormatter(formatter)
        logger.addHandler(db_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(name)s: %(message)s'))
        logger.addHandler(console_handler)

    return logger


app_logger = setup_logger()
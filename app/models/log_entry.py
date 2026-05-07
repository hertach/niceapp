# app/models/log_entry.py
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import LOG_PATH

# Eigene Base und Engine NUR für die Logs
LogBase = declarative_base()
log_engine = create_engine(
    f"sqlite:///{LOG_PATH}",
    connect_args={"check_same_thread": False},
)
LogSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=log_engine)


class LogEntry(LogBase):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20), index=True)
    module = Column(String(100))
    filename = Column(String(100))  # <-- Neu: Dateiname
    func_name = Column(String(100))  # <-- Neu: Funktionsname
    message = Column(Text)


def init_log_db():
    """Erstellt die log.db und die Tabelle, falls sie noch nicht existieren."""
    LogBase.metadata.create_all(bind=log_engine)

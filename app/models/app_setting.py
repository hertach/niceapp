# app/models/app_setting.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.core.database import Base
from datetime import datetime

class AppSetting(Base):
    __tablename__ = 'app_settings'

    id = Column(Integer, primary_key=True, index=True)
    # ── BACKUP ──
    backup_path = Column(String(255), default='./backups')
    backup_on_close = Column(Boolean, default=False)
    backup_schedule = Column(String(50), default='none')  # Optionen: 'none', 'daily', 'weekly'
    last_backup = Column(DateTime, nullable=True)  # Merkt sich, wann das letzte Auto-Backup lief
    # ── LOGGING ──
    log_to_terminal = Column(Boolean, default=True)

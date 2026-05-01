# app/models/app_setting.py
from sqlalchemy import Column, Integer, String, Boolean
from app.core.database import Base

class AppSetting(Base):
    __tablename__ = 'app_settings'

    id = Column(Integer, primary_key=True, index=True)
    backup_path = Column(String(255), default='./backups')
    log_to_terminal = Column(Boolean, default=True)
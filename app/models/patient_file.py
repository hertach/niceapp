import enum
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.core.database import Base


class FileCategory(str, enum.Enum):
    RECHNUNG = "rechnungen"
    STORNO = "stornos"
    QUITTUNG = "quittungen"
    UPLOAD = "uploads"


class PatientFile(Base):
    __tablename__ = "patient_files"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("patient_sessions.id"), nullable=True)

    file_uuid = Column(String(36), unique=True, nullable=False)  # Dateiname auf Disk
    original_name = Column(String(255), nullable=False)           # Originalname für UI
    category = Column(Enum(FileCategory), nullable=False)
    mime_type = Column(String(100))
    file_size_bytes = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    patient = relationship("Patient")
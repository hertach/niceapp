import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class FileCategory(str, enum.Enum):
    RECHNUNG = "rechnungen"
    STORNO   = "stornos"
    QUITTUNG = "quittungen"
    UPLOAD   = "uploads"


class EncryptionType(str, enum.Enum):
    PDF_PASSWORD = "pdf_password"   # PDF AES-256, in Finder mit Passwort öffenbar
    AES_GCM      = "aes_gcm"        # Custom AES-256-GCM, nur über App zugänglich


class PatientFile(Base):
    __tablename__ = "patient_files"

    id         = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    session_id = Column(Integer, ForeignKey("patient_sessions.id"), nullable=True)

    # Identifikation auf Disk & in der UI
    file_uuid       = Column(String(36), unique=True, nullable=False)
    disk_filename   = Column(String(41), nullable=True)    # uuid oder uuid.pdf
    original_name   = Column(String(255), nullable=False)
    category        = Column(Enum(FileCategory), nullable=False)
    mime_type       = Column(String(100))
    file_size_bytes = Column(Integer)

    # Verschlüsselungstyp — bestimmt wie entschlüsselt wird
    encryption_type = Column(
        Enum(EncryptionType),
        nullable=False,
        default=EncryptionType.PDF_PASSWORD,
    )

    # Audit-Felder
    created_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Soft-Delete
    is_deleted         = Column(Boolean, default=False, nullable=False)
    deleted_at         = Column(DateTime, nullable=True)
    deleted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    patient = relationship("Patient")

    @property
    def effective_disk_filename(self) -> str:
        """Tatsächlicher Dateiname auf Disk (Fallback auf file_uuid für ältere Einträge)."""
        return self.disk_filename or self.file_uuid

    def __repr__(self) -> str:
        return f"<PatientFile {self.original_name} [{self.category}/{self.encryption_type}]>"

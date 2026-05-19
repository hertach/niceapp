import base64
import mimetypes
import os
import uuid as uuid_lib
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import PATIENT_STORAGE_PATH
from app.core.database import get_session
from app.core.file_crypto import (
    decrypt_bytes,
    decrypt_pdf,
    derive_patient_password,
    encrypt_bytes,
    encrypt_pdf,
    encrypt_pdf_with_transfer_password,
)
from app.core.logger import app_logger
from app.models.app_setting import AppSetting
from app.models.patient_file import EncryptionType, FileCategory, PatientFile


def _get_storage_path() -> str:
    """Liest Speicherpfad aus AppSetting → .env → Default."""
    with get_session() as session:
        setting = session.query(AppSetting).first()
        if setting and setting.upload_path_patient_documents:
            return setting.upload_path_patient_documents
    return PATIENT_STORAGE_PATH


def _get_global_pdf_password() -> str | None:
    """Gibt das globale PDF-Passwort aus den Settings zurück, oder None."""
    with get_session() as session:
        setting = session.query(AppSetting).first()
        if setting and setting.pdf_password:
            return setting.pdf_password
    return None


class FileManager:
    """
    Verwaltet verschlüsselte Patientendateien.

    Passwort-Priorität für PDFs:
      1. AppSetting.pdf_password  (globales Passwort aus den Settings)
      2. Patient.custom_pdf_password  (patientenspezifisches Passwort)
      3. derive_patient_password()  (automatisch abgeleitet, immer verfügbar)

    Das verwendete Passwort wird AES-verschlüsselt pro Datei gespeichert
    (PatientFile.pdf_password_enc), damit Passwortänderungen bestehende
    Dateien nicht kaputt machen.
    """

    def __init__(self, patient: "Patient") -> None:  # noqa: F821
        if not hasattr(patient, "storage_uuid") or not patient.storage_uuid:
            raise ValueError(
                f"Patient {patient.id} hat keine storage_uuid. "
                "Bitte die Alembic-Migration ausführen."
            )
        self.patient      = patient
        self.storage_uuid = patient.storage_uuid
        self.base_path    = Path(_get_storage_path()) / self.storage_uuid

    # ── Ordner ────────────────────────────────────────────────────────────────

    def ensure_folders(self) -> None:
        for category in FileCategory:
            (self.base_path / category.value).mkdir(parents=True, exist_ok=True)

    # ── Passwort-Auflösung ────────────────────────────────────────────────────

    def resolve_pdf_password(self) -> str:
        """
        Gibt das aktuell aktive PDF-Passwort zurück.
        Reihenfolge: global (Settings) → custom (Patient) → abgeleitet (HKDF).
        """
        global_pw = _get_global_pdf_password()
        if global_pw:
            return global_pw
        custom = getattr(self.patient, "custom_pdf_password", None)
        if custom:
            return custom
        return derive_patient_password(self.storage_uuid)

    def derived_pdf_password(self) -> str:
        """Gibt immer das HKDF-abgeleitete Passwort zurück (unabhängig von Settings)."""
        return derive_patient_password(self.storage_uuid)

    # ── Passwort aus gespeichertem Blob lesen ─────────────────────────────────

    def _store_password(self, password: str) -> str:
        """Verschlüsselt das Passwort mit dem Patientenschlüssel → base64-String."""
        encrypted = encrypt_bytes(self.storage_uuid, password.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")

    def _load_password(self, pdf_password_enc: str) -> str:
        """Entschlüsselt das gespeicherte Passwort."""
        encrypted = base64.b64decode(pdf_password_enc)
        return decrypt_bytes(self.storage_uuid, encrypted).decode("utf-8")

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(
        self,
        plaintext: bytes,
        original_filename: str,
        category: FileCategory,
        db: Session,
        user_id: int,
        session_id: int | None = None,
        doc_type: str | None = None,
    ) -> PatientFile:
        self.ensure_folders()

        file_uuid = str(uuid_lib.uuid4())
        mime_type, _ = mimetypes.guess_type(original_filename)
        is_pdf = (mime_type == "application/pdf")

        if is_pdf:
            password        = self.resolve_pdf_password()
            encrypted       = encrypt_pdf(plaintext, password)
            disk_filename   = f"{file_uuid}.pdf"
            encryption_type = EncryptionType.PDF_PASSWORD
            pdf_password_enc = self._store_password(password)
        else:
            encrypted       = encrypt_bytes(self.storage_uuid, plaintext)
            disk_filename   = file_uuid
            encryption_type = EncryptionType.AES_GCM
            pdf_password_enc = None

        dest = self.base_path / category.value / disk_filename
        dest.write_bytes(encrypted)

        record = PatientFile(
            patient_id       = self.patient.id,
            session_id       = session_id,
            file_uuid        = file_uuid,
            disk_filename    = disk_filename,
            original_name    = original_filename,
            category         = category,
            doc_type         = doc_type,
            mime_type        = mime_type or "application/octet-stream",
            file_size_bytes  = len(plaintext),
            encryption_type  = encryption_type,
            pdf_password_enc = pdf_password_enc,
            created_by_user_id = user_id,
        )
        db.add(record)
        db.flush()

        app_logger.info(
            f"Upload: '{original_filename}' [{encryption_type.value}] → "
            f"Patient {self.patient.id} / {category.value}"
        )
        return record

    # ── Download ──────────────────────────────────────────────────────────────

    def download(self, file_uuid: str, db: Session) -> tuple[bytes, PatientFile]:
        """Entschlüsselt im RAM, gibt Klartextbytes zurück. Nie auf Disk schreiben."""
        record = (
            db.query(PatientFile)
            .filter_by(file_uuid=file_uuid, patient_id=self.patient.id, is_deleted=False)
            .first()
        )
        if not record:
            raise FileNotFoundError(f"Datei nicht gefunden: {file_uuid}")

        encrypted_path = self.base_path / record.category.value / record.effective_disk_filename
        if not encrypted_path.exists():
            raise FileNotFoundError(f"Datei auf Disk fehlt: {encrypted_path}")

        encrypted = encrypted_path.read_bytes()

        if record.encryption_type == EncryptionType.PDF_PASSWORD:
            # Gespeichertes Passwort verwenden → robust bei Passwortänderungen
            if record.pdf_password_enc:
                password = self._load_password(record.pdf_password_enc)
            else:
                password = self.resolve_pdf_password()
            plaintext = decrypt_pdf(encrypted, password)
        else:
            plaintext = decrypt_bytes(self.storage_uuid, encrypted)

        app_logger.info(f"Download: '{record.original_name}' / Patient {self.patient.id}")
        return plaintext, record

    # ── Export mit Transfer-Passwort (E-Mail / Patientenübergabe) ─────────────

    def download_with_transfer_password(
        self,
        file_uuid: str,
        db: Session,
        transfer_password: str,
    ) -> tuple[bytes, PatientFile]:
        """
        Entschlüsselt und verschlüsselt mit einem Transfer-Passwort (z.B. für E-Mail).
        """
        plaintext, record = self.download(file_uuid, db)
        if record.encryption_type == EncryptionType.PDF_PASSWORD:
            export_bytes = encrypt_pdf_with_transfer_password(plaintext, transfer_password)
        else:
            export_bytes = plaintext
        return export_bytes, record

    # ── Löschen ──────────────────────────────────────────────────────────────

    def delete(self, file_uuid: str, db: Session, user_id: int) -> None:
        record = (
            db.query(PatientFile)
            .filter_by(file_uuid=file_uuid, patient_id=self.patient.id)
            .first()
        )
        if not record or record.is_deleted:
            raise FileNotFoundError(f"Datei nicht gefunden: {file_uuid}")

        record.is_deleted         = True
        record.deleted_at         = datetime.utcnow()
        record.deleted_by_user_id = user_id

        encrypted_path = self.base_path / record.category.value / record.effective_disk_filename
        if encrypted_path.exists():
            _secure_overwrite(encrypted_path)

        app_logger.info(f"Gelöscht: '{record.original_name}' von User {user_id}")

    # ── Liste ────────────────────────────────────────────────────────────────

    def list_files(
        self,
        db: Session,
        category: FileCategory | None = None,
    ) -> list[PatientFile]:
        q = db.query(PatientFile).filter_by(patient_id=self.patient.id, is_deleted=False)
        if category:
            q = q.filter_by(category=category)
        return q.order_by(PatientFile.created_at.desc()).all()


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _secure_overwrite(path: Path) -> None:
    size = path.stat().st_size
    with open(path, "r+b") as f:
        f.write(b"\x00" * size)
        f.flush()
        os.fsync(f.fileno())
    path.unlink()

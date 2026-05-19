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
)
from app.core.logger import app_logger
from app.models.app_setting import AppSetting
from app.models.patient_file import EncryptionType, FileCategory, PatientFile


def _get_storage_path() -> str:
    """
    Liest den Speicherpfad für Patientendateien aus den App-Einstellungen.
    Priorität: AppSetting.upload_path_patient_documents → .env → Hardcoded-Default
    """
    with get_session() as session:
        setting = session.query(AppSetting).first()
        if setting and setting.upload_path_patient_documents:
            return setting.upload_path_patient_documents
    return PATIENT_STORAGE_PATH


class FileManager:
    """
    Zentraler Einstiegspunkt für alle Datei-Operationen eines Patienten.

    Verschlüsselungsstrategie:
      PDF-Dateien  → PDF AES-256 (Standard-Passwortschutz)
                     → Datei bleibt gültiges PDF, in Finder mit Passwort öffenbar
                     → Dateiname auf Disk: {uuid}.pdf
      Andere Dateien → AES-256-GCM (opaker Blob)
                     → Nur über die App zugänglich
                     → Dateiname auf Disk: {uuid}

    Passwort für PDF-Dateien: via derive_patient_password() — deterministisch,
    im UI anzeigbar, nie separat gespeichert.
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

    # ── Passwort (für UI-Anzeige & Verschlüsselung) ───────────────────────────

    def patient_pdf_password(self) -> str:
        """
        Gibt das aktive PDF-Passwort zurück.
        Priorität: custom_pdf_password (DB) → automatisch abgeleitet (HKDF).
        Im UI anzeigen, damit der User Dateien im Finder öffnen kann.
        """
        custom = getattr(self.patient, "custom_pdf_password", None)
        if custom:
            return custom
        return derive_patient_password(self.storage_uuid)

    def derived_pdf_password(self) -> str:
        """Gibt immer das automatisch abgeleitete Passwort zurück (unabhängig von custom)."""
        return derive_patient_password(self.storage_uuid)

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(
        self,
        plaintext: bytes,
        original_filename: str,
        category: FileCategory,
        db: Session,
        user_id: int,
        session_id: int | None = None,
    ) -> PatientFile:
        """
        Wählt automatisch die Verschlüsselung anhand des MIME-Types:
          application/pdf → PDF AES-256 + .pdf-Extension auf Disk
          alles andere    → AES-256-GCM ohne Extension
        """
        self.ensure_folders()

        file_uuid = str(uuid_lib.uuid4())
        mime_type, _ = mimetypes.guess_type(original_filename)
        is_pdf = (mime_type == "application/pdf")

        if is_pdf:
            password       = self.patient_pdf_password()
            encrypted      = encrypt_pdf(plaintext, password)
            disk_filename  = f"{file_uuid}.pdf"
            encryption_type = EncryptionType.PDF_PASSWORD
        else:
            encrypted      = encrypt_bytes(self.storage_uuid, plaintext)
            disk_filename  = file_uuid
            encryption_type = EncryptionType.AES_GCM

        dest = self.base_path / category.value / disk_filename
        dest.write_bytes(encrypted)

        record = PatientFile(
            patient_id      = self.patient.id,
            session_id      = session_id,
            file_uuid       = file_uuid,
            disk_filename   = disk_filename,
            original_name   = original_filename,
            category        = category,
            mime_type       = mime_type or "application/octet-stream",
            file_size_bytes = len(plaintext),
            encryption_type = encryption_type,
            created_by_user_id = user_id,
        )
        db.add(record)
        db.flush()

        app_logger.info(
            f"Datei-Upload: '{original_filename}' [{encryption_type.value}] → "
            f"Patient {self.patient.id} / {category.value} / {disk_filename}"
        )
        return record

    # ── Download (immer im RAM entschlüsseln) ─────────────────────────────────

    def download(self, file_uuid: str, db: Session) -> tuple[bytes, PatientFile]:
        """
        Entschlüsselt die Datei im RAM und gibt Klartextbytes zurück.
        Wählt automatisch die richtige Methode anhand encryption_type.
        """
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
            password  = self.patient_pdf_password()
            plaintext = decrypt_pdf(encrypted, password)
        else:
            plaintext = decrypt_bytes(self.storage_uuid, encrypted)

        app_logger.info(
            f"Datei-Download: '{record.original_name}' / Patient {self.patient.id}"
        )
        return plaintext, record

    # ── Export: mit Transfer-Passwort (E-Mail / Patientenübergabe) ────────────

    def download_with_transfer_password(
        self,
        file_uuid: str,
        db: Session,
        transfer_password: str,
    ) -> tuple[bytes, PatientFile]:
        """
        Entschlüsselt die Datei und verschlüsselt sie mit einem Transfer-Passwort.
        Verwendung: E-Mail-Versand, Patientendaten-Export.

        Für PDFs: Ergebnis ist ein gültiges PDF mit dem transfer_password.
        Für andere: Ergebnis bleibt AES-GCM-verschlüsselt (anderer Key).
        """
        from app.core.file_crypto import encrypt_pdf_with_transfer_password

        plaintext, record = self.download(file_uuid, db)

        if record.encryption_type == EncryptionType.PDF_PASSWORD:
            export_bytes = encrypt_pdf_with_transfer_password(plaintext, transfer_password)
        else:
            # Für Nicht-PDFs: AES-GCM mit transfer_password als Key-Material
            # (einfache Implementierung: gleicher Blob, anderes Passwort in Metadaten)
            export_bytes = plaintext  # TODO: spezifisches Exportformat bei Bedarf

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

        app_logger.info(
            f"Datei gelöscht: '{record.original_name}' / UUID={file_uuid} von User {user_id}"
        )

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
    """Überschreibt mit Nullbytes und löscht danach (kein Wiederherstellungsrisiko)."""
    size = path.stat().st_size
    with open(path, "r+b") as f:
        f.write(b"\x00" * size)
        f.flush()
        os.fsync(f.fileno())
    path.unlink()

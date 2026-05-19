import mimetypes
import os
import uuid as uuid_lib
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import PATIENT_STORAGE_PATH
from app.core.file_crypto import decrypt_bytes, encrypt_bytes
from app.core.logger import app_logger
from app.models.patient_file import FileCategory, PatientFile


class FileManager:
    """
    Zentraler Einstiegspunkt für alle Datei-Operationen eines Patienten.
    Verschlüsselung/Entschlüsselung findet ausschließlich im RAM statt.
    """

    def __init__(self, patient: "Patient"):
        self.patient = patient
        self.storage_uuid: str = patient.storage_uuid
        self.base_path = Path(PATIENT_STORAGE_PATH) / self.storage_uuid

    # ── Ordner ────────────────────────────────────────────────────────────────

    def ensure_folders(self) -> None:
        """Legt die Ordnerstruktur an, falls sie noch nicht existiert."""
        for category in FileCategory:
            (self.base_path / category.value).mkdir(parents=True, exist_ok=True)

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
        Verschlüsselt plaintext und schreibt das Ergebnis auf Disk.
        Der Klartext verlässt nie diese Methode in Richtung Dateisystem.
        """
        self.ensure_folders()

        file_uuid = str(uuid_lib.uuid4())
        encrypted = encrypt_bytes(self.storage_uuid, plaintext)

        dest = self.base_path / category.value / file_uuid
        dest.write_bytes(encrypted)

        mime_type, _ = mimetypes.guess_type(original_filename)
        record = PatientFile(
            patient_id=self.patient.id,
            session_id=session_id,
            file_uuid=file_uuid,
            original_name=original_filename,
            category=category,
            mime_type=mime_type or "application/octet-stream",
            file_size_bytes=len(plaintext),  # Originalgröße, nicht verschlüsselt
            created_by_user_id=user_id,
        )
        db.add(record)
        db.flush()

        app_logger.info(
            f"Datei-Upload: '{original_filename}' → Patient {self.patient.id} "
            f"/ {category.value} / UUID={file_uuid}"
        )
        return record

    # ── Download / Anzeige ───────────────────────────────────────────────────

    def download(self, file_uuid: str, db: Session) -> tuple[bytes, PatientFile]:
        """
        Lädt eine Datei in den RAM, entschlüsselt sie dort und gibt Bytes zurück.
        Wird niemals unverschlüsselt auf Disk geschrieben.
        """
        record = (
            db.query(PatientFile)
            .filter_by(
                file_uuid=file_uuid,
                patient_id=self.patient.id,
                is_deleted=False,
            )
            .first()
        )
        if not record:
            raise FileNotFoundError(f"Datei nicht gefunden: {file_uuid}")

        encrypted_path = self.base_path / record.category.value / file_uuid
        if not encrypted_path.exists():
            raise FileNotFoundError(
                f"Verschlüsselte Datei auf Disk fehlt: {encrypted_path}"
            )

        encrypted = encrypted_path.read_bytes()
        plaintext = decrypt_bytes(self.storage_uuid, encrypted)

        app_logger.info(
            f"Datei-Download: '{record.original_name}' von Patient {self.patient.id}"
        )
        return plaintext, record

    # ── Löschen ──────────────────────────────────────────────────────────────

    def delete(self, file_uuid: str, db: Session, user_id: int) -> None:
        """
        Soft-Delete in DB + sicheres Überschreiben der verschlüsselten Datei.
        """
        record = (
            db.query(PatientFile)
            .filter_by(file_uuid=file_uuid, patient_id=self.patient.id)
            .first()
        )
        if not record or record.is_deleted:
            raise FileNotFoundError(f"Datei nicht gefunden: {file_uuid}")

        record.is_deleted = True
        record.deleted_at = datetime.utcnow()
        record.deleted_by_user_id = user_id

        encrypted_path = self.base_path / record.category.value / file_uuid
        if encrypted_path.exists():
            _secure_overwrite(encrypted_path)

        app_logger.info(
            f"Datei gelöscht: '{record.original_name}' / UUID={file_uuid} "
            f"von User {user_id}"
        )

    # ── Liste ────────────────────────────────────────────────────────────────

    def list_files(
        self, db: Session, category: FileCategory | None = None
    ) -> list[PatientFile]:
        q = db.query(PatientFile).filter_by(
            patient_id=self.patient.id, is_deleted=False
        )
        if category:
            q = q.filter_by(category=category)
        return q.order_by(PatientFile.created_at.desc()).all()


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _secure_overwrite(path: Path) -> None:
    """
    Überschreibt eine Datei mit Nullen vor dem Löschen.
    Mindert das Risiko einer Wiederherstellung (kein Ersatz für FDE!).
    """
    size = path.stat().st_size
    with open(path, "r+b") as f:
        f.write(b"\x00" * size)
        f.flush()
        os.fsync(f.fileno())
    path.unlink()
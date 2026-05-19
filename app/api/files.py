# app/api/files.py
"""
HTTP-Endpunkt für verschlüsselte Datei-Downloads.

Warum ein eigener FastAPI-Endpunkt statt ui.download()?
  - ui.download() benötigt einen Dateipfad auf der Disk.
  - Verschlüsselte Dateien dürfen NICHT im Klartext auf Disk erscheinen.
  - Dieser Endpunkt entschlüsselt in-memory und streamt Bytes direkt zum Browser.

Auth-Strategie:
  - Kurzlebige Single-Use-Tokens (30s TTL) aus app/core/download_tokens.py
  - NiceGUI-Code erzeugt den Token; Endpunkt prüft und verbraucht ihn.
"""

from fastapi import Request
from fastapi.responses import Response
from nicegui import app as nicegui_app

from app.core.database import get_session
from app.core.download_tokens import consume_token
from app.core.file_manager import FileManager
from app.core.logger import app_logger
from app.models.patient import Patient
from app.models.patient_file import PatientFile


def register_file_routes() -> None:
    """
    Registriert alle Datei-Endpunkte auf nicegui_app (= FastAPI-Instanz).
    Muss in app/main.py VOR ui.run() aufgerufen werden.
    """

    @nicegui_app.get("/files/download/{file_uuid}")
    async def download_encrypted_file(
        file_uuid: str,
        token: str,
        request: Request,
    ) -> Response:
        """
        GET /files/download/{file_uuid}?token={token}

        Schritte:
          1. Token validieren (Single-Use, 30s TTL, file_uuid-Bindung)
          2. PatientFile-Datensatz aus DB laden
          3. FileManager.download() → AES-256-GCM entschlüsseln im RAM
          4. Bytes als HTTP-Response senden (inline oder attachment)
        """
        # ── 1. Auth via Download-Token ────────────────────────────────────────
        entry = consume_token(token)
        if not entry:
            app_logger.warning(
                f"Download abgelehnt: ungültiger/abgelaufener Token für {file_uuid}"
            )
            return Response(status_code=401, content="Ungültiger oder abgelaufener Token.")

        # Sicherheits-Check: Token muss zur angefragten Datei gehören
        if entry["file_uuid"] != file_uuid:
            app_logger.warning(
                f"Download abgelehnt: Token-file_uuid stimmt nicht überein "
                f"(erwartet={entry['file_uuid']}, erhalten={file_uuid})"
            )
            return Response(status_code=401, content="Token passt nicht zur Datei.")

        # ── 2. Datensatz laden & entschlüsseln ────────────────────────────────
        try:
            with get_session() as db:
                record = (
                    db.query(PatientFile)
                    .filter_by(file_uuid=file_uuid, is_deleted=False)
                    .first()
                )
                if not record:
                    return Response(status_code=404, content="Datei nicht gefunden.")

                patient = db.query(Patient).filter_by(id=record.patient_id).first()
                if not patient:
                    return Response(status_code=404, content="Patient nicht gefunden.")

                fm = FileManager(patient)
                plaintext, meta = fm.download(file_uuid, db)  # Entschlüsselung im RAM

            # ── 3. Sicher zum Browser senden ──────────────────────────────────
            app_logger.info(
                f"Download: '{meta.original_name}' von User {entry['user_id']} "
                f"(Patient {patient.id})"
            )
            return Response(
                content=plaintext,
                media_type=meta.mime_type or "application/octet-stream",
                headers={
                    # "inline" → Browser öffnet PDF direkt; "attachment" → Download-Dialog
                    "Content-Disposition": f'inline; filename="{meta.original_name}"',
                    # Kein Browser-Caching für sensible Gesundheitsdaten
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                    "Pragma": "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        except FileNotFoundError as e:
            app_logger.error(f"Download-Fehler (not found): {e}")
            return Response(status_code=404, content=str(e))
        except Exception as e:
            app_logger.error(f"Download-Fehler (intern) für {file_uuid}: {e}")
            return Response(status_code=500, content="Interner Serverfehler.")

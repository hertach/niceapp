# app/components/document_dialog.py
from pathlib import Path

from nicegui import app as nicegui_app
from nicegui import ui

from app.core.database import get_session
from app.core.document_engine import DocumentEngine
from app.core.download_tokens import create_download_token
from app.core.file_manager import FileManager
from app.models.company_setting import DocumentTemplate
from app.models.patient import Patient
from app.models.patient_file import FileCategory

def _category_for_doc_type(doc_type: str) -> FileCategory:
    """
    Leitet die Speicherkategorie aus dem Dokumenttyp ab (case-insensitiv,
    Teilstring-Matching). Neue Vorlagen-Typen aus der DB werden automatisch
    erkannt, solange sie eines der Schlüsselwörter enthalten:
      • 'storno'   → stornos/
      • 'quittung' → quittungen/
      • 'rechnung' → rechnungen/
      • sonst      → uploads/
    """
    name = doc_type.lower()
    if "storno" in name:
        return FileCategory.STORNO
    if "quittung" in name:
        return FileCategory.QUITTUNG
    if "rechnung" in name:
        return FileCategory.RECHNUNG
    return FileCategory.UPLOAD


def open_document_dialog(
    doc_type: str, patient_id: int, session_ids: list[int], on_success=None
):
    """
    Zentrale Funktion zur Vorlagenauswahl und Dokumentengenerierung.
    - doc_type: 'Rechnung', 'Quittung' etc.
    - patient_id: ID des Patienten
    - session_ids: Liste der zu druckenden Sitzungs-IDs
    - on_success: Optionale Funktion, die nach erfolgreichem Druck ausgeführt wird (z.B. UI Refresh)

    Ablauf nach der Generierung:
      1. PDF-Bytes lesen
      2. Via FileManager verschlüsselt im Patientenordner speichern
      3. Beide Temp-Dateien (.docx + .pdf) löschen
      4. Download über den Token-Endpunkt triggern (kein ui.download!)
    """
    with get_session() as session:
        # Nur aktive Vorlagen für diesen Typ suchen
        templates = (
            session.query(DocumentTemplate)
            .filter_by(doc_type=doc_type, is_active=True)
            .all()
        )

    if not templates:
        ui.notify(f'Keine aktive Vorlage für "{doc_type}" gefunden!', type="negative")
        return

    # Die eigentliche Druck-Logik
    def run_generation(tpl_id: int):
        ui.notify(f"Generiere {doc_type}...", type="info")
        try:
            engine = DocumentEngine()
            filepath = engine.generate_document(
                doc_type, patient_id, session_ids, specific_template_id=tpl_id
            )

            # ── Verschlüsselt speichern & Temp-Dateien bereinigen ─────────────
            pdf_path  = Path(filepath)
            docx_path = pdf_path.with_suffix(".docx")

            plaintext  = pdf_path.read_bytes()
            category   = _category_for_doc_type(doc_type)
            user_id    = nicegui_app.storage.user.get("user_id", 0)
            # Bei genau einer Sitzung verknüpfen; bei Sammelrechnung None
            session_id = session_ids[0] if len(session_ids) == 1 else None

            with get_session() as db:
                patient = db.query(Patient).filter_by(id=patient_id).first()
                fm      = FileManager(patient)
                record  = fm.upload(
                    plaintext=plaintext,
                    original_filename=pdf_path.name,
                    category=category,
                    db=db,
                    user_id=user_id,
                    session_id=session_id,
                    doc_type=doc_type,
                )
                db.commit()
                # file_uuid VOR dem Session-Close sichern —
                # nach db.commit() ist das Objekt sonst detached
                file_uuid = record.file_uuid

            # Temp-Dateien löschen (Klartext darf nicht auf Disk bleiben)
            pdf_path.unlink(missing_ok=True)
            docx_path.unlink(missing_ok=True)

            # ── Download über Token-Endpunkt triggern ─────────────────────────
            token = create_download_token(file_uuid, user_id)
            ui.navigate.to(
                f"/files/download/{file_uuid}?token={token}",
                new_tab=True,
            )

            ui.notify(f"{doc_type} erfolgreich generiert!", type="positive")

            # Falls die aufrufende Seite etwas aufräumen will (z.B. Tabellen-Auswahl löschen)
            if on_success:
                on_success()

        except Exception as e:
            ui.notify(f"Fehler bei der Generierung: {e}", type="negative")
            print(f"Dokumenten-Fehler: {e}")

    # FALL 1: Nur eine Vorlage -> Ohne Rückfrage sofort drucken
    if len(templates) == 1:
        # ui.timer entkoppelt den Prozess kurz, damit die UI nicht einfriert
        ui.timer(0.1, lambda: run_generation(templates[0].id), once=True)

    # FALL 2: Mehrere Vorlagen -> Auswahldialog anzeigen
    else:
        with ui.dialog() as diag, ui.card().classes("p-6 min-w-[350px] shadow-sm"):
            ui.label(f"{doc_type} Vorlage wählen").classes(
                "text-lg font-bold text-[#1e3a5f] mb-4"
            )

            # Standardvorlage (oder die Erste) vorauswählen
            default_tpl = next((t for t in templates if t.is_default), templates[0])
            options = {t.id: t.name for t in templates}

            sel = (
                ui.select(options, value=default_tpl.id, label="Verfügbare Designs")
                .classes("w-full mb-6")
                .props("outlined dense")
            )

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Abbrechen", on_click=diag.close).props(
                    'flat text-color="grey"'
                )

                # Beim Klick: Drucken und Dialog schließen
                ui.button(
                    "PDF Generieren",
                    on_click=lambda: [run_generation(sel.value), diag.close()],
                ).props('unelevated color="primary"')
        diag.open()

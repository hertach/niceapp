# app/components/document_dialog.py
from nicegui import ui

from app.core.database import get_session
from app.core.document_engine import DocumentEngine
from app.models.company_setting import DocumentTemplate


def open_document_dialog(
    doc_type: str, patient_id: int, session_ids: list[int], on_success=None
):
    """
    Zentrale Funktion zur Vorlagenauswahl und Dokumentengenerierung.
    - doc_type: 'Rechnung', 'Quittung' etc.
    - patient_id: ID des Patienten
    - session_ids: Liste der zu druckenden Sitzungs-IDs
    - on_success: Optionale Funktion, die nach erfolgreichem Druck ausgeführt wird (z.B. UI Refresh)
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

            ui.download(filepath)
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

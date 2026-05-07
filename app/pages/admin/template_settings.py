# app/pages/admin/template_settings.py
import asyncio
import os
import time

from nicegui import ui

from app.core.database import get_session
from app.core.logger import app_logger
from app.models.app_setting import AppSetting
from app.models.company_setting import DocumentTemplate


def template_settings_page() -> None:
    ui.label("Vorlagenverwaltung").classes(
        "text-[24px] font-semibold text-[#1e3a5f] mb-4"
    )

    # Platzhalter-Definition
    PLACEHOLDERS = {
        "Allgemein (Firma)": [
            "{{firma_name}}",
            "{{firma_strasse}}",
            "{{firma_ort}}",
            "{{firma_iban}}",
            "{{firma_bank}}",
        ],
        "Patient": [
            "{{p_vorname}}",
            "{{p_nachname}}",
            "{{p_strasse}}",
            "{{p_plz}}",
            "{{p_ort}}",
            "{{p_geburtsdatum}}",
        ],
        "Sitzung / Finanzen": [
            "{{s_datum}}",
            "{{s_betrag_netto}}",
            "{{s_mwst_satz}}",
            "{{s_betrag_brutto}}",
            "{{s_anliegen}}",
        ],
    }

    with get_session() as session:
        app_settings = session.query(AppSetting).first()
        TEMPLATE_DIR = (
            app_settings.upload_path_templates
            if app_settings and app_settings.upload_path_templates
            else "./data/uploads/templates"
        )

    os.makedirs(TEMPLATE_DIR, exist_ok=True)

    # ── 1. KUGELSICHERE UPLOAD-HILFSFUNKTIONEN ──
    def get_upload_filename(e) -> str:
        """Extrahiert den echten Dateinamen aus dem neuen NiceGUI 'file' Objekt."""
        # Fall 1: Falls der Name direkt auf dem Event liegt (alte Versionen)
        if getattr(e, "name", None):
            return e.name

        # Fall 2: In neuen Versionen liegt alles unter e.file
        file_obj = getattr(e, "file", None)
        if file_obj:
            # Wir prüfen die beiden gängigsten Attribute für Datei-Objekte
            if getattr(file_obj, "name", None):
                return file_obj.name
            if getattr(file_obj, "filename", None):
                return file_obj.filename

            # Falls wir ihn NOCH IMMER nicht finden, lassen wir uns anzeigen, was in file_obj steckt
            app_logger.debug(f"DEBUG - Attribute in e.file: {dir(file_obj)}")

        # Fall 3: Frontend-Fallback (Vue/Quasar)
        args = getattr(e, "args", None)
        if isinstance(args, dict):
            return args.get("name") or args.get("filename") or "unbekannte_vorlage.docx"

        return "unbekannte_vorlage.docx"

    async def get_upload_content(e) -> bytes:
        if hasattr(e, "content") and hasattr(e.content, "read"):
            data = e.content.read()
        elif hasattr(e, "file") and hasattr(e.file, "read"):
            data = e.file.read()
        else:
            return b""
        return await data if asyncio.iscoroutine(data) else data

    # ── 2. MODAL ZUM BEARBEITEN (Wieder da!) ──
    edit_dialog = ui.dialog()
    edit_state = {"id": None, "name": "", "doc_type": "Rechnung", "is_default": False}

    with edit_dialog, ui.card().classes("min-w-[400px] p-6"):
        ui.label("Vorlage bearbeiten").classes("text-lg font-bold mb-4")

        ui.input("Anzeigename / Dateiname").bind_value(edit_state, "name").classes(
            "w-full mb-2"
        ).props("outlined dense")
        ui.select(
            ["Rechnung", "Quittung", "Begleitbrief", "Mahnung"], label="Zuweisungstyp"
        ).bind_value(edit_state, "doc_type").classes("w-full mb-2").props(
            "outlined dense"
        )
        ui.checkbox("Als Standard für diesen Typ festlegen").bind_value(
            edit_state, "is_default"
        ).classes("mb-4")

        def save_edit():
            with get_session() as session:
                t = (
                    session.query(DocumentTemplate)
                    .filter_by(id=edit_state["id"])
                    .first()
                )
                if t:
                    t.name = edit_state["name"]
                    t.doc_type = edit_state["doc_type"]
                    t.is_default = edit_state["is_default"]

                    if edit_state["is_default"]:
                        session.query(DocumentTemplate).filter(
                            DocumentTemplate.doc_type == edit_state["doc_type"],
                            DocumentTemplate.id != t.id,
                        ).update({DocumentTemplate.is_default: False})

                    session.commit()
            edit_dialog.close()
            template_table_refresh.refresh()
            ui.notify("Vorlage erfolgreich aktualisiert!", type="positive")

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=edit_dialog.close).props(
                'flat text-color="grey"'
            )
            ui.button("Speichern", on_click=save_edit).props(
                'unelevated color="primary"'
            )

    def open_edit(row):
        edit_state.update(
            {
                "id": row["id"],
                "name": row["name"],
                "doc_type": row["doc_type"],
                "is_default": row["is_default"],
            }
        )
        edit_dialog.open()

    # ── 3. TABELLE ──
    @ui.refreshable
    def template_table_refresh():
        with get_session() as session:
            templates = (
                session.query(DocumentTemplate)
                .order_by(DocumentTemplate.doc_type)
                .all()
            )

        rows = [
            {
                "id": t.id,
                "name": t.name,
                "doc_type": t.doc_type,
                "is_default": t.is_default,
            }
            for t in templates
        ]

        columns = [
            {
                "name": "doc_type",
                "label": "Typ",
                "field": "doc_type",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "name",
                "label": "Dateiname / Bezeichnung",
                "field": "name",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "is_default",
                "label": "Standard",
                "field": "is_default",
                "align": "center",
                "sortable": True,
            },
            {"name": "actions", "label": "Aktionen", "field": "id", "align": "right"},
        ]

        table = ui.table(columns=columns, rows=rows, row_key="id").classes(
            "w-full shadow-sm border border-slate-200 bg-white"
        )

        table.add_slot(
            "body-cell-is_default",
            r"""
            <q-td :props="props">
                <q-btn v-if="props.row.is_default" flat round dense icon="star" color="amber" @click="$parent.$emit('set_default', props.row)">
                    <q-tooltip>Dies ist die Standardvorlage</q-tooltip>
                </q-btn>
                <q-btn v-else flat round dense icon="star_border" color="grey-4" @click="$parent.$emit('set_default', props.row)">
                    <q-tooltip>Als Standard setzen</q-tooltip>
                </q-btn>
            </q-td>
        """,
        )

        # Edit Button ist wieder da!
        table.add_slot(
            "body-cell-actions",
            r"""
            <q-td :props="props">
                <div class="row items-center justify-end no-wrap gap-1">
                    <q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit('edit_row', props.row)">
                        <q-tooltip>Bearbeiten</q-tooltip>
                    </q-btn>
                    <q-btn flat round dense icon="delete" color="negative" @click="$parent.$emit('delete_row', props.row.id)">
                        <q-tooltip>Löschen</q-tooltip>
                    </q-btn>
                </div>
            </q-td>
        """,
        )

        # Event-Bindings für die Tabelle
        table.on(
            "set_default", lambda msg: set_default(msg.args["id"], msg.args["doc_type"])
        )
        table.on("edit_row", lambda msg: open_edit(msg.args))
        table.on("delete_row", lambda msg: delete_tpl(msg.args))

    # ── 4. LOGIK-FUNKTIONEN ──
    async def handle_upload(e):
        if not selected_type.value:
            return ui.notify("Bitte erst einen Typ auswählen!", type="warning")

        original_name = get_upload_filename(e)

        timestamp = int(time.time())
        safe_filename = (
            f"{selected_type.value}_{timestamp}_{original_name.replace(' ', '_')}"
        )
        path = os.path.join(TEMPLATE_DIR, safe_filename)

        content = await get_upload_content(e)
        with open(path, "wb") as f:
            f.write(content)

        with get_session() as session:
            existing_default = (
                session.query(DocumentTemplate)
                .filter_by(doc_type=selected_type.value, is_default=True)
                .first()
            )

            new_tpl = DocumentTemplate(
                doc_type=selected_type.value,
                name=original_name,
                file_path=path,
                is_default=(existing_default is None),
            )
            session.add(new_tpl)
            session.commit()

        template_table_refresh.refresh()
        ui.notify(f'"{original_name}" erfolgreich hochgeladen', type="positive")

    def set_default(tpl_id, t_type):
        with get_session() as session:
            session.query(DocumentTemplate).filter_by(doc_type=t_type).update(
                {DocumentTemplate.is_default: False}
            )
            session.query(DocumentTemplate).filter_by(id=tpl_id).update(
                {DocumentTemplate.is_default: True}
            )
            session.commit()
        template_table_refresh.refresh()
        ui.notify("Standard-Vorlage geändert", type="info")

    def delete_tpl(tpl_id):
        with get_session() as session:
            t = session.query(DocumentTemplate).filter_by(id=tpl_id).first()
            if t:
                if os.path.exists(t.file_path):
                    os.remove(t.file_path)
                session.delete(t)
                session.commit()
        template_table_refresh.refresh()
        ui.notify("Vorlage gelöscht", type="info")

    # ── 5. UI LAYOUT ──
    with ui.row().classes("w-full gap-8 items-start"):
        with ui.column().classes("flex-1 min-w-0"):
            # Upload Card
            with ui.card().classes(
                "w-full p-6 mb-6 shadow-sm border border-slate-200 bg-blue-50/20"
            ):
                ui.label("Vorlage hochladen").classes("font-bold text-[#1e3a5f] mb-2")
                with ui.row().classes("items-center w-full gap-4"):
                    selected_type = (
                        ui.select(
                            ["Rechnung", "Quittung", "Begleitbrief", "Mahnung"],
                            label="Zuweisung",
                        )
                        .classes("w-48")
                        .props("outlined dense bg-white")
                    )
                    ui.upload(
                        on_upload=handle_upload, auto_upload=True, label="Datei wählen"
                    ).props('flat bordered bg-white accept=".docx,.odt"').classes(
                        "flex-1"
                    )

            template_table_refresh()

        # Platzhalter-Liste Rechts
        with ui.column().classes("w-80 shrink-0"):
            with ui.card().classes(
                "w-full p-6 shadow-sm border border-slate-200 sticky top-4"
            ):
                ui.label("Mögliche Platzhalter").classes(
                    "font-bold text-lg text-[#1e3a5f] mb-1"
                )
                ui.label("Klicke auf ein Icon, um den Tag zu kopieren.").classes(
                    "text-xs text-slate-500 mb-6"
                )

                def copy_tag(t):
                    ui.clipboard.write(t)
                    ui.notify(f"{t} kopiert", position="top", type="positive")

                for cat, tags in PLACEHOLDERS.items():
                    ui.label(cat).classes(
                        "text-sm font-bold mt-2 border-b w-full pb-1 text-slate-700"
                    )
                    for tag in tags:
                        with ui.row().classes(
                            "w-full justify-between items-center py-1 group"
                        ):
                            ui.label(tag).classes("text-xs font-mono text-[#0078d4]")
                            ui.button(
                                icon="content_copy", on_click=lambda t=tag: copy_tag(t)
                            ).props('flat round dense size=xs color="grey"').classes(
                                "opacity-0 group-hover:opacity-100 transition-opacity"
                            )

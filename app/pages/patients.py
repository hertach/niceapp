# app/pages/patients.py
from nicegui import app as nicegui_app
from nicegui import ui

from app.core.database import get_session
from app.models.patient import Patient


def patients_page(navigate) -> None:
    ui.label("Patientenverwaltung").classes(
        "text-[24px] font-semibold text-[#1e3a5f] mb-4"
    )

    # ── Navigation-Hilfsfunktion ──
    def open_patient_detail(patient_id: int | None = None):
        """Speichert die ID in der Session und navigiert zur Detailseite."""
        nicegui_app.storage.user["current_patient_id"] = patient_id
        navigate("/patient_detail")

    # ── Action-Bar (Suche & Neuer Patient) ──
    with ui.row().classes("w-full justify-between items-center mb-6"):
        # Suchfeld
        search_input = (
            ui.input("Patient suchen...")
            .classes("w-[300px]")
            .props("outlined dense clearable")
        )
        with search_input.add_slot("append"):
            ui.icon("search")

        # Button: Neuer Patient
        ui.button(
            "Neuer Patient", icon="add", on_click=lambda: open_patient_detail(None)
        ).props("unelevated").classes("bg-[#0078d4] text-white px-4")

    # ── Daten laden ──
    def fetch_patients():
        with get_session() as session:
            query = session.query(Patient)

            # Suchfilter anwenden, falls Text eingegeben wurde
            if search_input.value:
                search_term = f"%{search_input.value}%"
                query = query.filter(
                    Patient.first_name.ilike(search_term)
                    | Patient.last_name.ilike(search_term)
                )

            patients = query.all()
            return [
                {
                    "id": p.id,
                    "first_name": p.first_name,
                    "last_name": p.last_name,
                    "birthdate": (
                        p.birthdate.strftime("%d.%m.%Y") if p.birthdate else "-"
                    ),
                    "gender": p.gender or "-",
                }
                for p in patients
            ]

    def update_table():
        table.rows = fetch_patients()
        table.update()

    # Tabelle aktualisieren, wenn im Suchfeld getippt wird
    search_input.on("update:model-value", update_table)

    # ── Tabelle ──
    columns = [
        {"name": "id", "label": "ID", "field": "id", "align": "left", "sortable": True},
        {
            "name": "first_name",
            "label": "Vorname",
            "field": "first_name",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "last_name",
            "label": "Nachname",
            "field": "last_name",
            "align": "left",
            "sortable": True,
        },
        {
            "name": "birthdate",
            "label": "Geburtsdatum",
            "field": "birthdate",
            "align": "left",
        },
        {"name": "gender", "label": "Geschlecht", "field": "gender", "align": "left"},
        {"name": "actions", "label": "Aktionen", "field": "actions", "align": "right"},
    ]

    table = ui.table(columns=columns, rows=fetch_patients(), row_key="id").classes(
        "w-full shadow-sm border border-slate-200"
    )

    # ── Vue-Slot für die Action-Buttons (Bearbeiten / Löschen) ──
    table.add_slot(
        "body-cell-actions",
        """
            <q-td :props="props">
                <q-btn flat round dense color="primary" icon="edit" @click="$parent.$emit('edit', props.row)" >
                    <q-tooltip>Akte öffnen</q-tooltip>
                </q-btn>
                <q-btn flat round dense color="negative" icon="delete" @click="$parent.$emit('delete', props.row)" >
                    <q-tooltip>Löschen</q-tooltip>
                </q-btn>
            </q-td>
        """,
    )

    # ── Event-Handler für die Tabelle ──
    table.on("edit", lambda e: open_patient_detail(e.args["id"]))

    def delete_patient(patient_id: int):
        with get_session() as session:
            p = session.query(Patient).filter_by(id=patient_id).first()
            if p:
                session.delete(p)
                session.commit()
                ui.notify("Patient wurde gelöscht", type="info")
                update_table()

    table.on("delete", lambda e: delete_patient(e.args["id"]))

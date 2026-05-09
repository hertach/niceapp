# app/pages/admin/accounting_settings.py
from nicegui import ui
from sqlalchemy import asc

from app.core.database import get_session
from app.models.accounting import Account, FiscalYear


def accounting_settings_page() -> None:
    ui.label("Buchhaltung: Kontenplan & Perioden").classes("text-[24px] font-semibold text-[#1e3a5f] mb-4")

    # ── 1. DIALOGE ZUM BEARBEITEN UND LÖSCHEN ──
    def open_edit_dialog(row_data: dict):
        with ui.dialog() as dialog, ui.card().classes("p-6 w-[400px]"):
            ui.label(f"Konto {row_data['number']} bearbeiten").classes("text-lg font-bold text-[#1e3a5f] mb-4")

            # Die Kontonummer ändern wir nicht (das gäbe ein Chaos in den Buchungen), nur den Namen
            new_name = ui.input("Bezeichnung", value=row_data['name']).classes("w-full mb-4").props("outlined")

            def save():
                if not new_name.value:
                    ui.notify("Bezeichnung darf nicht leer sein.", type="warning")
                    return

                with get_session() as session:
                    acc = session.query(Account).get(row_data['id'])
                    if acc:
                        acc.name = new_name.value
                        session.commit()

                ui.notify("Konto erfolgreich aktualisiert", type="positive")
                dialog.close()
                account_table.refresh()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Abbrechen", on_click=dialog.close).props("flat")
                ui.button("Speichern", on_click=save).props("unelevated").classes("bg-[#0078d4] text-white")

        dialog.open()

    def confirm_delete(row_data: dict):
        with ui.dialog() as dialog, ui.card().classes("p-6 w-[400px]"):
            ui.label("Konto löschen").classes("text-lg font-bold text-[#1e3a5f] mb-2")
            ui.label(f"Möchtest du das Konto '{row_data['number']} - {row_data['name']}' wirklich löschen?").classes(
                "text-slate-600 mb-4")

            def do_delete():
                with get_session() as session:
                    acc = session.query(Account).get(row_data['id'])
                    if acc:
                        session.delete(acc)
                        session.commit()
                ui.notify("Konto gelöscht", type="warning")
                dialog.close()
                account_table.refresh()

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Abbrechen", on_click=dialog.close).props("flat")
                ui.button("Löschen", on_click=do_delete).props("unelevated color=negative")

        dialog.open()

    # ── 2. DIE TABELLE MIT DEN DATEN ──
    @ui.refreshable
    def account_table():
        with get_session() as session:
            accounts = session.query(Account).order_by(asc(Account.account_number)).all()

            rows = [
                {
                    "number": a.account_number,
                    "name": a.name,
                    "class": a.account_class,
                    "id": a.id
                } for a in accounts
            ]

        columns = [
            {"name": "number", "label": "Konto-Nr", "field": "number", "align": "left", "sortable": True},
            {"name": "name", "label": "Bezeichnung", "field": "name", "align": "left", "sortable": True},
            {"name": "class", "label": "Klasse", "field": "class", "align": "center"},
            {"name": "actions", "label": "Aktionen", "field": "id", "align": "right"},
        ]

        table = ui.table(columns=columns, rows=rows, row_key="number").classes(
            "w-full shadow-sm border border-slate-200")

        # Einfügen der Buttons in die Spalte "Aktionen"
        table.add_slot("body-cell-actions", r"""
            <q-td :props="props">
                <q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit('edit', props.row)">
                    <q-tooltip>Bearbeiten</q-tooltip>
                </q-btn>
                <q-btn flat round dense icon="delete" color="negative" @click="$parent.$emit('delete', props.row)">
                    <q-tooltip>Löschen</q-tooltip>
                </q-btn>
            </q-td>
        """)

        # Events mit den Dialogen verknüpfen
        table.on("edit", lambda e: open_edit_dialog(e.args))
        table.on("delete", lambda e: confirm_delete(e.args))

    # ── 3. FORMULAR FÜR NEUES KONTO ──
    with ui.row().classes("w-full gap-4 mb-6"):
        with ui.card().classes("flex-1 p-6 shadow-sm border border-slate-200 bg-blue-50/20"):
            ui.label("Neues Konto hinzufügen").classes("font-bold mb-2 text-[#1e3a5f]")
            with ui.row().classes("w-full gap-4 items-end"):
                acc_num = ui.number("Konto-Nummer", format="%.0f").classes("w-32").props("outlined dense bg-white")
                acc_name = ui.input("Bezeichnung").classes("flex-1").props("outlined dense bg-white")

                def add_account():
                    if not acc_num.value or not acc_name.value:
                        return ui.notify("Bitte alle Felder ausfüllen", type="warning")

                    with get_session() as session:
                        # Prüfen ob Nummer schon existiert
                        existing = session.query(Account).filter_by(account_number=int(acc_num.value)).first()
                        if existing:
                            return ui.notify(f"Konto {int(acc_num.value)} existiert bereits!", type="negative")

                        # Automatische Berechnung von Klasse (1. Ziffer) und Gruppe (1.+2. Ziffer)
                        num_str = str(int(acc_num.value))
                        a_class = int(num_str[0])
                        a_group = int(num_str[:2]) if len(num_str) >= 2 else a_class * 10

                        new_acc = Account(
                            account_number=int(acc_num.value),
                            name=acc_name.value,
                            account_class=a_class,
                            account_group=a_group
                        )
                        session.add(new_acc)
                        session.commit()

                    # Formular leeren und Tabelle aktualisieren
                    acc_num.value = None
                    acc_name.value = ""
                    ui.notify("Konto erfolgreich hinzugefügt", type="positive")
                    account_table.refresh()

                ui.button("Hinzufügen", icon="add", on_click=add_account).props("unelevated").classes(
                    "bg-[#0078d4] text-white")

    account_table()
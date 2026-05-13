# app/pages/admin/finance_settings.py
from datetime import date, datetime

from nicegui import ui

from app.components.inputs import date_input
from app.core.database import get_session
from app.core.logger import app_logger
from app.models.accounting import Account
from app.models.finance_setting import PaymentMethod, VATSetting, InvoiceFormatSetting


def finance_settings_page() -> None:
    # ── INVOICE FORMAT: Hilfsfunktionen ─────────────────────────────
    def get_or_create_invoice_format():
        with get_session() as session:
            fmt = session.query(InvoiceFormatSetting).first()
            if not fmt:
                fmt = InvoiceFormatSetting(prefix="RE-", include_year=True, padding=3)
                session.add(fmt)
                session.commit()
                session.refresh(fmt)
            return fmt

    async def save_invoice_format():
        try:
            with get_session() as session:
                fmt = session.query(InvoiceFormatSetting).first()
                if not fmt:
                    fmt = InvoiceFormatSetting()
                    session.add(fmt)

                fmt.prefix = prefix_input.value
                fmt.include_year = year_toggle.value
                fmt.padding = int(padding_input.value)
                session.commit()
            ui.notify("Rechnungsformat erfolgreich gespeichert", type="positive")
        except Exception as e:
            ui.notify(f"Fehler beim Speichern: {e}", type="negative")

    def update_preview():
        """Generiert eine Live-Vorschau der Rechnungsnummer."""
        current_year = date.today().year
        pref = prefix_input.value or ""

        # Logik exakt wie in accounting_logic.py
        if year_toggle.value:
            demo_prefix = f"{pref}{current_year}-"
        else:
            demo_prefix = pref

        demo_num = f"{1:0{int(padding_input.value or 3)}d}"
        preview_label.set_text(f"Vorschau: {demo_prefix}{demo_num}")
    # ── VAT: Hilfsfunktionen ───────────────────────────────────────
    def get_vat_data() -> list[dict]:
        today = date.today()
        with get_session() as session:
            vats = session.query(VATSetting).all()
            rows = []
            for r in vats:
                # Dynamische Status-Berechnung[cite: 11]
                is_expired = r.end_date and r.end_date < today
                is_effectively_active = r.is_active and not is_expired

                rows.append(
                    {
                        "id": r.id,
                        "description": r.description,
                        "rate": f"{r.rate}%",
                        "start_date": r.start_date.strftime("%d.%m.%Y"),
                        "end_date": (
                            r.end_date.strftime("%d.%m.%Y")
                            if r.end_date
                            else "Unbegrenzt"
                        ),
                        "is_active": is_effectively_active,
                        "status_label": "Aktiv" if is_effectively_active else "Inaktiv",
                    }
                )
            return rows

    def set_vat_end_date(vat_id: int, new_end_date: str):
        """Setzt ein Enddatum. Erwartet DD.MM.YYYY von der Tabelle."""
        if not new_end_date:
            return

        try:
            # Parsing angepasst auf DD.MM.YYYY[cite: 10, 11]
            end_dt = datetime.strptime(new_end_date, "%d.%m.%Y").date()
            with get_session() as session:
                vat = session.query(VATSetting).filter_by(id=vat_id).first()
                if vat:
                    vat.end_date = end_dt
                    if end_dt < date.today():
                        vat.is_active = False
                    session.commit()
                    ui.notify(
                        f'Enddatum für "{vat.description}" auf {new_end_date} gesetzt.'
                    )
                    app_logger.info(
                        f'Enddatum für "{vat.description}" auf {new_end_date} gesetzt.'
                    )
                    table.rows = get_vat_data()
        except ValueError:
            app_logger.info(f'Ungültiges Datum für "{vat.description}"')
            ui.notify("Ungültiges Datum", type="negative")

    async def save_new_vat():
        """Validiert und speichert einen neuen MWSt-Satz."""
        try:
            rate_val = float(rate_input.value)
            # Parsing angepasst auf DD.MM.YYYY[cite: 10, 11]
            start_dt = datetime.strptime(start_date_input.value, "%d.%m.%Y").date()
            end_dt = (
                datetime.strptime(end_date_input.value, "%d.%m.%Y").date()
                if end_date_input.value
                else None
            )

            with get_session() as session:
                new_vat = VATSetting(
                    rate=rate_val,
                    description=desc_input.value,
                    start_date=start_dt,
                    end_date=end_dt,
                    is_active=True,
                )
                session.add(new_vat)
                session.commit()

            ui.notify("MWSt-Satz erfolgreich hinzugefügt", type="positive")
            vat_dialog.close()
            table.rows = get_vat_data()
        except ValueError:
            ui.notify(
                "Bitte prüfen Sie die Eingaben (Format TT.MM.JJJJ)", type="negative"
            )

    # ── PAYMENT METHOD: Hilfsfunktionen ─────────────────────────────
    pm_state = {"id": None}

    def get_pm_data() -> list[dict]:
        with get_session() as session:
            pms = session.query(PaymentMethod).all()
            rows = []
            for r in pms:
                rows.append(
                    {
                        "id": r.id,
                        "title": r.title,
                        "is_active": r.is_active,
                        "account_number": (
                            r.account.account_number if r.account else "-"
                        ),
                        "account_name": (
                            r.account.name if r.account else "Kein Konto zugewiesen"
                        ),
                        "account_id": r.account_id,
                        "status_label": "Aktiv" if r.is_active else "Inaktiv",
                    }
                )
            return rows

    def toggle_pm_status(pm_id: int):
        """Aktiviert oder deaktiviert eine Bezahlmethode im Wechsel."""
        with get_session() as session:
            pm = session.query(PaymentMethod).filter_by(id=pm_id).first()
            if pm:
                # Kehrt den aktuellen Status um (True -> False, False -> True)
                pm.is_active = not pm.is_active
                session.commit()

                status_text = "aktiviert" if pm.is_active else "deaktiviert"
                ui.notify(f'Bezahlmethode "{pm.title}" {status_text}.', type="info")
                pm_table.rows = get_pm_data()

    async def save_pm():
        """Speichert eine neue Bezahlmethode oder updatet eine bestehende."""
        try:
            with get_session() as session:
                if pm_state["id"]:
                    # Bestehenden Eintrag updaten
                    pm = (
                        session.query(PaymentMethod)
                        .filter_by(id=pm_state["id"])
                        .first()
                    )
                    if pm:
                        pm.title = title_input.value
                        ui.notify("Bezahlmethode aktualisiert", type="positive")
                else:
                    # Neuen Eintrag anlegen
                    new_pm = PaymentMethod(title=title_input.value, is_active=True)
                    session.add(new_pm)
                    ui.notify("Bezahlmethode hinzugefügt", type="positive")

                session.commit()

            pm_dialog.close()
            pm_table.rows = get_pm_data()
        except Exception as e:
            ui.notify(f"Fehler beim Speichern: {e}", type="negative")

    def open_pm_dialog(pm_id=None, current_title="", current_account_id=None):
        with ui.dialog() as diag, ui.card().classes("w-96"):
            ui.label("Zahlart bearbeiten" if pm_id else "Neue Zahlart").classes(
                "text-lg font-bold"
            )

            # 1. Name der Zahlart
            name_input = (
                ui.input("Bezeichnung", value=current_title)
                .classes("w-full")
                .props("outlined dense")
            )

            # 2. Konten für das Suchfeld laden
            with get_session() as session:
                accounts = session.query(Account).order_by(Account.account_number).all()
                # Wir erstellen ein Dictionary für das Dropdown: {ID: "Nummer - Name"}
                acc_options = {a.id: f"{a.account_number} - {a.name}" for a in accounts}

            # 3. Das Suchfeld (Searchable Select)
            account_selection = (
                ui.select(
                    options=acc_options,
                    label="Buchungskonto",
                    value=current_account_id,
                    with_input=True,  # Macht es zum Suchfeld
                )
                .classes("w-full")
                .props("outlined dense")
            )

            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("Abbrechen", on_click=diag.close).props("flat")

                def save():
                    with get_session() as session:
                        if pm_id:
                            pm = session.query(PaymentMethod).get(pm_id)
                            pm.title = name_input.value
                            pm.account_id = account_selection.value
                        else:
                            new_pm = PaymentMethod(
                                title=name_input.value,
                                account_id=account_selection.value,
                            )
                            session.add(new_pm)
                        session.commit()
                    diag.close()
                    ui.notify("Zahlart gespeichert")
                    # Hier müsste ggf. die Tabelle aktualisiert werden

                ui.button("Speichern", on_click=save).props("unelevated color=primary")
        diag.open()

    # ── VAT: Modal / Dialog ─────────────────────────────────────────
    with ui.dialog() as vat_dialog, ui.card().classes("w-[400px]"):
        ui.label("Neuen MWSt-Satz anlegen").classes("text-lg font-bold mb-2")
        with ui.column().classes("w-full gap-4"):
            desc_input = ui.input("Beschreibung (z.B. Regelsatz)").classes("w-full")
            rate_input = ui.number("Satz (%)", value=19.0, format="%.1f").classes(
                "w-full"
            )

            # Nutzung deiner date_input Komponente[cite: 10]
            start_date_input = date_input("Startdatum (Ab)")
            end_date_input = date_input("Enddatum (Optional)")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Abbrechen", on_click=vat_dialog.close).props("flat")
            ui.button("Speichern", on_click=save_new_vat)
    # ── PAYMENT METHOD: Modal / Dialog ──────────────────────────────
    with ui.dialog() as pm_dialog, ui.card().classes("w-[400px]"):
        ui.label("Neuen Bezahlmethode anlegen").classes("text-lg font-bold mb-2")
        with ui.column().classes("w-full gap-4"):
            title_input = ui.input("Beschreibung").classes("w-full")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Abbrechen", on_click=pm_dialog.close).props("flat")
            ui.button("Speichern", on_click=save_pm)
    # ── Hauptseite ──────────────────────────────────────────────────
    ui.label("Finanz-Einstellungen").classes(
        "text-[24px] font-semibold text-[#1e3a5f] mb-4"
    )
    with ui.card().classes("w-full max-w-4xl p-8 shadow-sm border border-slate-200"):
        # ── INVOICE FORMAT: UI ───────────────────────────────────
        with ui.column().classes("w-full gap-4"):
            ui.label("Rechnungsformat").classes("font-medium text-slate-700 text-lg")

            # Lade aktuelle Settings
            current_fmt = get_or_create_invoice_format()

            with ui.row().classes("w-full items-center gap-6"):
                # on_change triggert die Live-Vorschau bei jedem Tastendruck/Klick
                prefix_input = ui.input("Präfix", value=current_fmt.prefix, on_change=update_preview).props(
                    "outlined dense")
                padding_input = ui.number("Stellenanzahl", value=current_fmt.padding, min=1, max=10, format="%d",
                                          on_change=update_preview).props("outlined dense")
                year_toggle = ui.checkbox("Jahr integrieren (z.B. -2026-)", value=current_fmt.include_year,
                                          on_change=update_preview)

            with ui.row().classes("w-full items-center justify-between mt-2"):
                preview_label = ui.label("Vorschau: ").classes(
                    "text-md font-mono text-slate-500 bg-slate-100 p-2 rounded")
                ui.button("Format speichern", icon="save", on_click=save_invoice_format).props(
                    "unelevated color=primary size=sm")

            update_preview()  # Initiales Rendern der Vorschau
            ui.separator().props("dense").classes("my-4")
        # ── VAT: UI / TABLE ──────────────────────────────────────────
        with ui.column().classes("w-full gap-6"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("MWSt-Sätze").classes("font-medium text-slate-700 text-lg")
                ui.button(
                    "MWSt hinzufügen", icon="add", on_click=vat_dialog.open
                ).props("outline size=sm")

            # --- UI Tabelle ---
            table = ui.table(
                columns=[
                    {
                        "name": "description",
                        "label": "Beschreibung",
                        "field": "description",
                        "align": "left",
                    },
                    {"name": "rate", "label": "Satz", "field": "rate", "align": "left"},
                    {
                        "name": "start_date",
                        "label": "Gültig ab",
                        "field": "start_date",
                        "align": "left",
                    },
                    {
                        "name": "end_date",
                        "label": "Gültig bis",
                        "field": "end_date",
                        "align": "left",
                    },
                    {
                        "name": "status",
                        "label": "Status",
                        "field": "status_label",
                        "align": "left",
                    },
                    {
                        "name": "actions",
                        "label": "Enddatum setzen",
                        "field": "id",
                        "align": "right",
                    },
                ],
                rows=get_vat_data(),
                row_key="id",
            ).classes("w-full border-none shadow-none")

            table.add_slot(
                "body-cell-actions",
                r"""
                                <q-td :props="props">
                                    <q-btn v-if="props.row.is_active" flat round dense icon="event" color="primary">
                                        <q-popup-proxy cover transition-show="scale" transition-hide="scale">
                                            <q-date mask="DD.MM.YYYY" @update:model-value="val => $parent.$emit('set_date', {id: props.row.id, date: val})">
                                                <div class="row items-center justify-end">
                                                    <q-btn v-close-popup label="Schließen" color="primary" flat />
                                                </div>
                                            </q-date>
                                        </q-popup-proxy>
                                        <q-tooltip>Ablaufdatum wählen</q-tooltip>
                                    </q-btn>
                                    <q-icon v-else name="lock" color="grey" />
                                </q-td>
                            """,
            )

            table.on(
                "set_date",
                lambda msg: set_vat_end_date(msg.args["id"], msg.args["date"]),
            )

            # Styling für inaktive Zeilen (optional)
            table.add_slot(
                "body-row",
                r"""
                                <q-tr :props="props" :class="props.row.is_active ? '' : 'bg-slate-50 text-slate-400'">
                                    <q-td v-for="col in props.cols" :key="col.name" :props="props">
                                        {{ col.value }}
                                    </q-td>
                                </q-tr>
                            """,
            )

            ui.separator().props("dense")
        # ── PAYMENT METHODS: UI / TABLE ──────────────────────────────
        with ui.column().classes("w-full gap-6 mt-8"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("Bezahlmethoden").classes("font-medium text-slate-700 text-lg")
                # Button öffnet Dialog nun immer als "Neu" (pm_id=None)
                ui.button(
                    "Bezahlmethode hinzufügen",
                    icon="add",
                    on_click=lambda: open_pm_dialog(),
                ).props("outline size=sm")

            # --- UI Tabelle (pm_table) ---
            pm_table = ui.table(
                columns=[
                    {
                        "name": "title",
                        "label": "Bezahlmethode",
                        "field": "title",
                        "align": "left",
                    },
                    {
                        "name": "account_number",
                        "label": "Konto",
                        "field": "account_number",
                        "align": "left",
                    },
                    {
                        "name": "account_name",
                        "label": "Kontobezeichnung",
                        "field": "account_name",
                        "align": "left",
                    },
                    {
                        "name": "status",
                        "label": "Status",
                        "field": "status_label",
                        "align": "left",
                    },
                    {
                        "name": "actions",
                        "label": "Aktionen",
                        "field": "id",
                        "align": "right",
                    },
                ],
                rows=get_pm_data(),
                row_key="id",
            ).classes("w-full border-none shadow-none")

            # Slot für Edit- und Deaktivieren-Buttons
            pm_table.add_slot(
                "body-cell-actions",
                r"""
                            <q-td :props="props">
                                <div class="row items-center justify-end no-wrap gap-1">
                                    <!-- Bearbeiten (immer möglich) -->
                                    <q-btn flat round dense icon="edit" color="primary"
                                           @click="$parent.$emit('edit_pm', props.row)">
                                        <q-tooltip>Bearbeiten</q-tooltip>
                                    </q-btn>

                                    <!-- Toggle Button (Icon und Farbe ändern sich je nach Status) -->
                                    <q-btn flat round dense 
                                           :icon="props.row.is_active ? 'block' : 'restore'" 
                                           :color="props.row.is_active ? 'negative' : 'positive'"
                                           @click="$parent.$emit('toggle_pm', props.row.id)">
                                        <q-tooltip>{{ props.row.is_active ? 'Deaktivieren' : 'Wieder aktivieren' }}</q-tooltip>
                                    </q-btn>
                                </div>
                            </q-td>
                        """,
            )

            # Event-Listener für die Table-Actions
            pm_table.on(
                "edit_pm",
                lambda msg: open_pm_dialog(
                    msg.args["id"],
                    msg.args["title"],
                    msg.args.get("account_id"),  # Hier die ID mitgeben
                ),
            )
            pm_table.on("toggle_pm", lambda msg: toggle_pm_status(msg.args))

            # Styling für inaktive Zeilen
            pm_table.add_slot(
                "body-row",
                r"""
                            <q-tr :props="props" :class="props.row.is_active ? '' : 'bg-slate-50 text-slate-400'">
                                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                                    {{ col.value }}
                                </q-td>
                            </q-tr>
                        """,
            )

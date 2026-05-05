# app/pages/admin/finance_settings.py
from nicegui import ui
from app.core.database import get_session
from app.core.logger import app_logger
from app.components.inputs import date_input
from app.models.finance_setting import VATSetting, PaymentMethod
from datetime import datetime, date


def finance_settings_page() -> None:
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

                rows.append({
                    'id': r.id,
                    'description': r.description,
                    'rate': f"{r.rate}%",
                    'start_date': r.start_date.strftime('%d.%m.%Y'),
                    'end_date': r.end_date.strftime('%d.%m.%Y') if r.end_date else 'Unbegrenzt',
                    'is_active': is_effectively_active,
                    'status_label': 'Aktiv' if is_effectively_active else 'Inaktiv'
                })
            return rows

    def set_vat_end_date(vat_id: int, new_end_date: str):
        """Setzt ein Enddatum. Erwartet DD.MM.YYYY von der Tabelle."""
        if not new_end_date:
            return

        try:
            # Parsing angepasst auf DD.MM.YYYY[cite: 10, 11]
            end_dt = datetime.strptime(new_end_date, '%d.%m.%Y').date()
            with get_session() as session:
                vat = session.query(VATSetting).filter_by(id=vat_id).first()
                if vat:
                    vat.end_date = end_dt
                    if end_dt < date.today():
                        vat.is_active = False
                    session.commit()
                    ui.notify(f'Enddatum für "{vat.description}" auf {new_end_date} gesetzt.')
                    app_logger.info(f'Enddatum für "{vat.description}" auf {new_end_date} gesetzt.')
                    table.rows = get_vat_data()
        except ValueError:
            app_logger.info(f'Ungültiges Datum für "{vat.description}"')
            ui.notify('Ungültiges Datum', type='negative')

    async def save_new_vat():
        """Validiert und speichert einen neuen MWSt-Satz."""
        try:
            rate_val = float(rate_input.value)
            # Parsing angepasst auf DD.MM.YYYY[cite: 10, 11]
            start_dt = datetime.strptime(start_date_input.value, '%d.%m.%Y').date()
            end_dt = datetime.strptime(end_date_input.value, '%d.%m.%Y').date() if end_date_input.value else None

            with get_session() as session:
                new_vat = VATSetting(
                    rate=rate_val,
                    description=desc_input.value,
                    start_date=start_dt,
                    end_date=end_dt,
                    is_active=True
                )
                session.add(new_vat)
                session.commit()

            ui.notify('MWSt-Satz erfolgreich hinzugefügt', type='positive')
            vat_dialog.close()
            table.rows = get_vat_data()
        except ValueError:
            ui.notify('Bitte prüfen Sie die Eingaben (Format TT.MM.JJJJ)', type='negative')

    # ── PAYMENT METHOD: Hilfsfunktionen ─────────────────────────────
    pm_state = {'id': None}
    def get_pm_data() -> list[dict]:
        with get_session() as session:
            pms = session.query(PaymentMethod).all()
            rows = []
            for r in pms:
                rows.append({
                    'id': r.id,
                    'title': r.title,
                    'is_active': r.is_active,
                    # Wichtig: status_label hinzufügen, da deine UI-Tabelle danach sucht!
                    'status_label': 'Aktiv' if r.is_active else 'Inaktiv'
                })
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
                ui.notify(f'Bezahlmethode "{pm.title}" {status_text}.', type='info')
                pm_table.rows = get_pm_data()

    async def save_pm():
        """Speichert eine neue Bezahlmethode oder updatet eine bestehende."""
        try:
            with get_session() as session:
                if pm_state['id']:
                    # Bestehenden Eintrag updaten
                    pm = session.query(PaymentMethod).filter_by(id=pm_state['id']).first()
                    if pm:
                        pm.title = title_input.value
                        ui.notify('Bezahlmethode aktualisiert', type='positive')
                else:
                    # Neuen Eintrag anlegen
                    new_pm = PaymentMethod(title=title_input.value, is_active=True)
                    session.add(new_pm)
                    ui.notify('Bezahlmethode hinzugefügt', type='positive')

                session.commit()

            pm_dialog.close()
            pm_table.rows = get_pm_data()
        except Exception as e:
            ui.notify(f'Fehler beim Speichern: {e}', type='negative')

    def open_pm_dialog(pm_id=None, current_title=''):
        """Öffnet den Dialog und füllt ihn ggf. mit bestehenden Daten."""
        pm_state['id'] = pm_id
        title_input.value = current_title
        pm_dialog.open()

    # ── VAT: Modal / Dialog ─────────────────────────────────────────
    with ui.dialog() as vat_dialog, ui.card().classes('w-[400px]'):
        ui.label('Neuen MWSt-Satz anlegen').classes('text-lg font-bold mb-2')
        with ui.column().classes('w-full gap-4'):
            desc_input = ui.input('Beschreibung (z.B. Regelsatz)').classes('w-full')
            rate_input = ui.number('Satz (%)', value=19.0, format='%.1f').classes('w-full')

            # Nutzung deiner date_input Komponente[cite: 10]
            start_date_input = date_input('Startdatum (Ab)')
            end_date_input = date_input('Enddatum (Optional)')

        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Abbrechen', on_click=vat_dialog.close).props('flat')
            ui.button('Speichern', on_click=save_new_vat)
    # ── PAYMENT METHOD: Modal / Dialog ──────────────────────────────
    with ui.dialog() as pm_dialog, ui.card().classes('w-[400px]'):
        ui.label('Neuen Bezahlmethode anlegen').classes('text-lg font-bold mb-2')
        with ui.column().classes('w-full gap-4'):
            title_input = ui.input('Beschreibung').classes('w-full')

        with ui.row().classes('w-full justify-end mt-4'):
            ui.button('Abbrechen', on_click=pm_dialog.close).props('flat')
            ui.button('Speichern', on_click=save_pm)
    # ── Hauptseite ──────────────────────────────────────────────────
    ui.label('Finanz-Einstellungen').classes('text-[24px] font-semibold text-[#1e3a5f] mb-4')
    with ui.card().classes('w-full max-w-4xl p-8 shadow-sm border border-slate-200'):
        # ── VAT: UI / TABLE ──────────────────────────────────────────
        with ui.column().classes('w-full gap-6'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('MWSt-Sätze').classes('font-medium text-slate-700 text-lg')
                ui.button('MWSt hinzufügen', icon='add', on_click=vat_dialog.open).props('outline size=sm')

            # --- UI Tabelle ---
            table = ui.table(
                columns=[
                    {'name': 'description', 'label': 'Beschreibung', 'field': 'description', 'align': 'left'},
                    {'name': 'rate', 'label': 'Satz', 'field': 'rate', 'align': 'left'},
                    {'name': 'start_date', 'label': 'Gültig ab', 'field': 'start_date', 'align': 'left'},
                    {'name': 'end_date', 'label': 'Gültig bis', 'field': 'end_date', 'align': 'left'},
                    {'name': 'status', 'label': 'Status', 'field': 'status_label', 'align': 'left'},
                    {'name': 'actions', 'label': 'Enddatum setzen', 'field': 'id', 'align': 'right'},
                ],
                rows=get_vat_data(),
                row_key='id',
            ).classes('w-full border-none shadow-none')

            table.add_slot('body-cell-actions', r'''
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
                            ''')

            table.on('set_date', lambda msg: set_vat_end_date(msg.args['id'], msg.args['date']))

            # Styling für inaktive Zeilen (optional)
            table.add_slot('body-row', r'''
                                <q-tr :props="props" :class="props.row.is_active ? '' : 'bg-slate-50 text-slate-400'">
                                    <q-td v-for="col in props.cols" :key="col.name" :props="props">
                                        {{ col.value }}
                                    </q-td>
                                </q-tr>
                            ''')

            ui.separator().props('dense')
        # ── PAYMENT METHODS: UI / TABLE ──────────────────────────────
        with ui.column().classes('w-full gap-6 mt-8'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Bezahlmethoden').classes('font-medium text-slate-700 text-lg')
                # Button öffnet Dialog nun immer als "Neu" (pm_id=None)
                ui.button('Bezahlmethode hinzufügen', icon='add', on_click=lambda: open_pm_dialog()).props(
                    'outline size=sm')

            # --- UI Tabelle (pm_table) ---
            pm_table = ui.table(
                columns=[
                    {'name': 'title', 'label': 'Bezahlmethode', 'field': 'title', 'align': 'left'},
                    {'name': 'status', 'label': 'Status', 'field': 'status_label', 'align': 'left'},
                    {'name': 'actions', 'label': 'Aktionen', 'field': 'id', 'align': 'right'},
                ],
                rows=get_pm_data(),
                row_key='id',
            ).classes('w-full border-none shadow-none')

            # Slot für Edit- und Deaktivieren-Buttons
            pm_table.add_slot('body-cell-actions', r'''
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
                        ''')

            # Event-Listener für die Table-Actions
            pm_table.on('edit_pm', lambda msg: open_pm_dialog(msg.args['id'], msg.args['title']))
            pm_table.on('toggle_pm', lambda msg: toggle_pm_status(msg.args))

            # Styling für inaktive Zeilen
            pm_table.add_slot('body-row', r'''
                            <q-tr :props="props" :class="props.row.is_active ? '' : 'bg-slate-50 text-slate-400'">
                                <q-td v-for="col in props.cols" :key="col.name" :props="props">
                                    {{ col.value }}
                                </q-td>
                            </q-tr>
                        ''')
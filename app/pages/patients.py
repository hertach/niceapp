# app/pages/patients.py
from datetime import date
from nicegui import ui
from app.core.database import get_session
from app.models.patient import Patient
from app.components.inputs import date_input


_GENDER_OPTIONS = {'': '—', 'm': 'Männlich', 'f': 'Weiblich', 'divers': 'Divers'}


def patients_page() -> None:

    ui.label('Patienten').style(
        'font-size: 24px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
    )

    # ── Daten laden ──────────────────────────────────────────
    def get_patient_data() -> list[dict]:
        with get_session() as session:
            patients = (
                session.query(Patient)
                .order_by(Patient.last_name, Patient.first_name)
                .all()
            )
            return [
                {
                    'id':         p.id,
                    'last_name':  p.last_name,
                    'first_name': p.first_name,
                    'dob':        p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '—',
                    'city':       p.city       or '—',
                    'phone':      p.phone      or '—',
                    'email':      p.email      or '—',
                    'is_active':  '✅' if p.is_active else '❌',
                }
                for p in patients
            ]

    def load_patients() -> None:
        table.rows = get_patient_data()
        table.update()

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog().props('full-width')

    def open_dialog(patient_id: int | None = None) -> None:
        dialog.clear()

        existing: Patient | None = None
        if patient_id:
            with get_session() as session:
                existing = session.get(Patient, patient_id)

        title = 'Neuer Patient' if not existing else f'{existing.first_name} {existing.last_name} bearbeiten'

        with dialog, ui.card().style('width: 680px; padding: 32px;'):
            ui.label(title).style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f; margin-bottom: 20px;'
            )

            def _section(label: str) -> None:
                ui.label(label).style(
                    'font-size: 13px; font-weight: 600; color: #0078d4; '
                    'text-transform: uppercase; letter-spacing: .05em; margin-bottom: 4px;'
                )

            # Personalien
            _section('Personalien')
            with ui.row().style('gap: 12px; width: 100%;'):
                first_name_input = ui.input(
                    label='Vorname',
                    value=existing.first_name if existing else '',
                ).style('flex: 1;')
                last_name_input = ui.input(
                    label='Nachname',
                    value=existing.last_name if existing else '',
                ).style('flex: 1;')

            with ui.row().style('gap: 12px; width: 100%; margin-top: 8px;'):
                dob_input = date_input(
                    label='Geburtsdatum',
                    value=existing.date_of_birth.strftime('%d.%m.%Y') if existing and existing.date_of_birth else ''
                )
                gender_select = ui.select(
                    label='Geschlecht',
                    options=_GENDER_OPTIONS,
                    value=existing.gender if existing else '',
                ).style('flex: 1;')

            ui.separator().style('margin: 16px 0 8px;')

            # Kontakt
            _section('Kontakt')
            with ui.row().style('gap: 12px; width: 100%;'):
                phone_input = ui.input(
                    label='Telefon',
                    value=existing.phone if existing else '',
                    placeholder='+41 79 000 00 00',
                ).style('flex: 1;')
                email_input = ui.input(
                    label='E-Mail',
                    value=existing.email if existing else '',
                    placeholder='name@beispiel.ch',
                ).style('flex: 1;')

            ui.separator().style('margin: 16px 0 8px;')

            # Adresse
            _section('Adresse')
            street_input = ui.input(
                label='Strasse & Hausnummer',
                value=existing.street if existing else '',
            ).style('width: 100%;')
            with ui.row().style('gap: 12px; width: 100%; margin-top: 8px;'):
                postal_code_input = ui.input(
                    label='PLZ',
                    value=existing.postal_code if existing else '',
                ).style('width: 90px;')
                city_input = ui.input(
                    label='Ort',
                    value=existing.city if existing else '',
                ).style('flex: 1;')

            ui.separator().style('margin: 16px 0 8px;')

            # Versicherung
            _section('Versicherung')
            with ui.row().style('gap: 12px; width: 100%;'):
                insurance_name_input = ui.input(
                    label='Krankenkasse',
                    value=existing.insurance_name if existing else '',
                    placeholder='z.B. Helsana',
                ).style('flex: 1;')
                insurance_number_input = ui.input(
                    label='Versichertennummer',
                    value=existing.insurance_number if existing else '',
                ).style('flex: 1;')

            ui.separator().style('margin: 16px 0 8px;')

            # Notizen
            _section('Interne Notizen')
            notes_input = ui.textarea(
                label='Notizen',
                value=existing.notes if existing else '',
            ).style('width: 100%; min-height: 80px;')

            is_active_toggle = ui.switch(
                'Patient aktiv',
                value=existing.is_active if existing else True,
            ).style('margin-top: 12px;')

            error = ui.label('').style(
                'color: #d32f2f; font-size: 12px; min-height: 18px; margin-top: 8px;'
            )

            def save() -> None:
                if not first_name_input.value or not last_name_input.value:
                    error.set_text('Vor- und Nachname sind Pflichtfelder.')
                    return

                # Geburtsdatum parsen (TT.MM.JJJJ)
                dob: date | None = None
                if dob_input.value:
                    try:
                        day, month, year = dob_input.value.split('.')
                        dob = date(int(year), int(month), int(day))
                    except (ValueError, TypeError):
                        error.set_text('Geburtsdatum ungültig – Format: TT.MM.JJJJ')
                        return

                with get_session() as session:
                    p = session.get(Patient, patient_id) if patient_id else Patient()
                    if not patient_id:
                        session.add(p)

                    p.first_name       = first_name_input.value.strip()
                    p.last_name        = last_name_input.value.strip()
                    p.date_of_birth    = dob
                    p.gender           = gender_select.value or ''
                    p.phone            = phone_input.value.strip()
                    p.email            = email_input.value.strip()
                    p.street           = street_input.value.strip()
                    p.postal_code      = postal_code_input.value.strip()
                    p.city             = city_input.value.strip()
                    p.insurance_name   = insurance_name_input.value.strip()
                    p.insurance_number = insurance_number_input.value.strip()
                    p.notes            = notes_input.value.strip()
                    p.is_active        = is_active_toggle.value
                    session.commit()

                ui.notify('Gespeichert ✅', type='positive')
                dialog.close()
                load_patients()

            with ui.row().style('margin-top: 24px; gap: 8px; justify-content: flex-end;'):
                ui.button('Abbrechen', on_click=dialog.close).props('flat')
                ui.button('Speichern', on_click=save).props('unelevated').style(
                    'background-color: #0078d4; color: white;'
                )

        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(patient_id: int, last_name: str, first_name: str) -> None:
        full_name = f'{first_name} {last_name}'
        with ui.dialog() as confirm_dialog, ui.card().style('padding: 32px; width: 380px;'):
            ui.label('Patient löschen').style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f;'
            )
            ui.label(f'Soll "{full_name}" wirklich gelöscht werden?').style(
                'margin-top: 12px; color: #444; font-size: 14px;'
            )
            ui.label('Alle zugehörigen Termine, Protokolle und Rechnungen gehen verloren.').style(
                'color: #d32f2f; font-size: 12px; margin-top: 4px;'
            )

            def do_delete() -> None:
                with get_session() as session:
                    p = session.get(Patient, patient_id)
                    if p:
                        session.delete(p)
                        session.commit()
                confirm_dialog.close()
                ui.notify(f'"{full_name}" gelöscht.', type='warning')
                load_patients()

            with ui.row().style('margin-top: 24px; gap: 8px; justify-content: flex-end;'):
                ui.button('Abbrechen', on_click=confirm_dialog.close).props('flat')
                ui.button('Löschen', icon='delete', on_click=do_delete).props('unelevated').style(
                    'background-color: #d32f2f; color: white;'
                )
        confirm_dialog.open()

    # ── Tabelle (nach open_dialog definiert → kein NameError) ────────────────
    with ui.row().style('margin-bottom: 16px;'):
        ui.button(
            'Neuer Patient', icon='person_add',
            on_click=lambda: open_dialog(),
        ).props('unelevated').style('background-color: #0078d4; color: white;')

    table = ui.table(
        columns=[
            {'name': 'id',         'label': 'ID',         'field': 'id',         'align': 'left', 'sortable': True},
            {'name': 'last_name',  'label': 'Nachname',   'field': 'last_name',  'align': 'left', 'sortable': True},
            {'name': 'first_name', 'label': 'Vorname',    'field': 'first_name', 'align': 'left', 'sortable': True},
            {'name': 'dob',        'label': 'Geb.-Datum', 'field': 'dob',        'align': 'left'},
            {'name': 'city',       'label': 'Ort',        'field': 'city',       'align': 'left'},
            {'name': 'phone',      'label': 'Telefon',    'field': 'phone',      'align': 'left'},
            {'name': 'email',      'label': 'E-Mail',     'field': 'email',      'align': 'left'},
            {'name': 'is_active',  'label': 'Aktiv',      'field': 'is_active',  'align': 'left'},
            {'name': 'actions',    'label': 'Aktionen',   'field': 'actions',    'align': 'left'},
        ],
        rows=get_patient_data(),
        row_key='id',
    ).style('width: 100%;')

    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn flat round icon="edit"   color="primary"  size="sm"
                @click="$parent.$emit('edit',   props.row)" />
            <q-btn flat round icon="delete" color="negative" size="sm"
                @click="$parent.$emit('delete', props.row)" />
        </q-td>
    ''')

    table.on('edit',   lambda e: open_dialog(e.args['id']))
    table.on('delete', lambda e: confirm_delete(e.args['id'], e.args['last_name'], e.args['first_name']))
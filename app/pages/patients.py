# app/pages/patients.py
from datetime import date
from nicegui import ui
from app.core.database import get_session
from app.models.patient import Patient
from app.components.inputs import date_input

_GENDER_OPTIONS = {'': '—', 'm': 'Männlich', 'f': 'Weiblich', 'divers': 'Divers'}


def patients_page() -> None:
    ui.label('Patienten').classes(
        'text-[24px] font-semibold text-[#1e3a5f] mb-4'
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
                    'id': p.id,
                    'last_name': p.last_name,
                    'first_name': p.first_name,
                    'dob': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '—',
                    'city': p.city or '—',
                    'phone': p.phone or '—',
                    'email': p.email or '—',
                    'is_active': '✅' if p.is_active else '❌',
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

        # Die alte Klasse p-2 wurde hier durch p-6 ersetzt, da das style-Attribut 24px Padding gefordert hat
        with dialog, ui.card().props('dense').classes('w-[680px] p-6'):
            ui.label(title).props('dense').classes(
                'text-[18px] font-semibold text-[#1e3a5f]'
            )

            def _section(label: str) -> None:
                ui.label(label).props('dense').classes(
                    'text-[13px] font-semibold text-[#0078d4] uppercase tracking-[.05em]'
                )

            # Personalien
            _section('Personalien')
            with ui.row().classes('gap-3 w-full'):
                first_name_input = ui.input(
                    label='Vorname',
                    value=existing.first_name if existing else '',
                ).props('dense').classes('flex-1')
                last_name_input = ui.input(
                    label='Nachname',
                    value=existing.last_name if existing else '',
                ).props('dense').classes('flex-1')

            with ui.row().classes('gap-3 w-full'):
                dob_input = date_input(
                    label='Geburtsdatum',
                    value=existing.date_of_birth.strftime('%d.%m.%Y') if existing and existing.date_of_birth else ''
                )
                gender_select = ui.select(
                    label='Geschlecht',
                    options=_GENDER_OPTIONS,
                    value=existing.gender if existing else '',
                ).props('dense').classes('flex-1')

            ui.separator()

            # Kontakt
            _section('Kontakt')
            with ui.row().props('dense').classes('gap-3 w-full'):
                phone_input = ui.input(
                    label='Telefon',
                    value=existing.phone if existing else '',
                    placeholder='+41 79 000 00 00',
                ).props('dense').classes('flex-1')
                email_input = ui.input(
                    label='E-Mail',
                    value=existing.email if existing else '',
                    placeholder='name@beispiel.ch',
                ).props('dense').classes('flex-1')

            ui.separator()

            # Adresse
            _section('Adresse')
            street_input = ui.input(
                label='Strasse & Hausnummer',
                value=existing.street if existing else '',
            ).props('dense').classes('w-full')

            with ui.row().classes('gap-3 w-full'):
                postal_code_input = ui.input(
                    label='PLZ',
                    value=existing.postal_code if existing else '',
                ).props('dense').classes('w-[90px]')
                city_input = ui.input(
                    label='Ort',
                    value=existing.city if existing else '',
                ).props('dense').classes('flex-1')

            ui.separator()

            # Versicherung
            _section('Versicherung')
            with ui.row().props('dense').classes('gap-3 w-full'):
                insurance_name_input = ui.input(
                    label='Krankenkasse',
                    value=existing.insurance_name if existing else '',
                    placeholder='z.B. Helsana',
                ).props('dense').classes('flex-1')
                insurance_number_input = ui.input(
                    label='Versichertennummer',
                    value=existing.insurance_number if existing else '',
                ).props('dense').classes('flex-1')

            ui.separator()

            # Notizen
            _section('Interne Notizen')
            with ui.row().classes('gap-3 w-full'):
                notes_input = ui.textarea(
                    label='Notizen',
                    value=existing.notes if existing else '',
                ).props('dense').classes('w-full min-h-[80px]')

            with ui.row().classes('gap-3 w-full'):
                is_active_toggle = ui.switch(
                    'Patient aktiv',
                    value=existing.is_active if existing else True,
                ).props('dense')

            error = ui.label('').classes(
                'text-[#d32f2f] text-[12px] min-h-[18px] mt-2'
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

                    p.first_name = first_name_input.value.strip()
                    p.last_name = last_name_input.value.strip()
                    p.date_of_birth = dob
                    p.gender = gender_select.value or ''
                    p.phone = phone_input.value.strip()
                    p.email = email_input.value.strip()
                    p.street = street_input.value.strip()
                    p.postal_code = postal_code_input.value.strip()
                    p.city = city_input.value.strip()
                    p.insurance_name = insurance_name_input.value.strip()
                    p.insurance_number = insurance_number_input.value.strip()
                    p.notes = notes_input.value.strip()
                    p.is_active = is_active_toggle.value
                    session.commit()

                ui.notify('Gespeichert ✅', type='positive')
                dialog.close()
                load_patients()

            with ui.row().props('dense').classes('gap-2 justify-end w-full'):
                ui.button('Abbrechen', on_click=dialog.close).props('flat')
                ui.button('Speichern', on_click=save).props('unelevated').classes(
                    'bg-[#0078d4] text-white'
                )

        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(patient_id: int, last_name: str, first_name: str) -> None:
        full_name = f'{first_name} {last_name}'
        with ui.dialog() as confirm_dialog, ui.card().classes('p-8 w-[380px]'):
            ui.label('Patient löschen').classes(
                'text-[18px] font-semibold text-[#1e3a5f]'
            )
            ui.label(f'Soll "{full_name}" wirklich gelöscht werden?').classes(
                'mt-3 text-[#444] text-[14px]'
            )
            ui.label('Alle zugehörigen Termine, Protokolle und Rechnungen gehen verloren.').classes(
                'text-[#d32f2f] text-[12px] mt-1'
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

            with ui.row().classes('mt-6 gap-2 justify-end w-full'):
                ui.button('Abbrechen', on_click=confirm_dialog.close).props('flat')
                ui.button('Löschen', icon='delete', on_click=do_delete).props('unelevated').classes(
                    'bg-[#d32f2f] text-white'
                )
        confirm_dialog.open()

    # ── Tabelle ──────────────────────────────────────────────
    with ui.row().classes('mb-4'):
        ui.button(
            'Neuer Patient', icon='person_add',
            on_click=lambda: open_dialog(),
        ).props('unelevated').classes('bg-[#0078d4] text-white')

    table = ui.table(
        columns=[
            {'name': 'id', 'label': 'ID', 'field': 'id', 'align': 'left', 'sortable': True},
            {'name': 'last_name', 'label': 'Nachname', 'field': 'last_name', 'align': 'left', 'sortable': True},
            {'name': 'first_name', 'label': 'Vorname', 'field': 'first_name', 'align': 'left', 'sortable': True},
            {'name': 'dob', 'label': 'Geb.-Datum', 'field': 'dob', 'align': 'left'},
            {'name': 'city', 'label': 'Ort', 'field': 'city', 'align': 'left'},
            {'name': 'phone', 'label': 'Telefon', 'field': 'phone', 'align': 'left'},
            {'name': 'email', 'label': 'E-Mail', 'field': 'email', 'align': 'left'},
            {'name': 'is_active', 'label': 'Aktiv', 'field': 'is_active', 'align': 'left'},
            {'name': 'actions', 'label': 'Aktionen', 'field': 'actions', 'align': 'left'},
        ],
        rows=get_patient_data(),
        row_key='id',
    ).classes('w-full')

    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn flat round icon="edit"   color="primary"  size="sm"
                @click="$parent.$emit('edit',   props.row)" />
            <q-btn flat round icon="delete" color="negative" size="sm"
                @click="$parent.$emit('delete', props.row)" />
        </q-td>
    ''')

    table.on('edit', lambda e: open_dialog(e.args['id']))
    table.on('delete', lambda e: confirm_delete(e.args['id'], e.args['last_name'], e.args['first_name']))
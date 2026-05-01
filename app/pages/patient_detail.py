# app/pages/patient_detail.py
from datetime import datetime
from nicegui import ui, app as nicegui_app
from app.core.database import get_session
from app.models.patient import Patient, PatientInsurance


def patient_detail_page(navigate) -> None:
    patient_id = nicegui_app.storage.user.get('current_patient_id')

    # ── State Variablen ──
    state = {
        'first_name': '', 'last_name': '', 'birthdate': '', 'gender': '', 'notes': '',
        'active_insurance': None,
        'insurance_history': []
    }

    # ── Daten aus DB laden ──
    def load_data():
        if not patient_id:
            return
        with get_session() as session:
            p = session.query(Patient).filter_by(id=patient_id).first()
            if p:
                state['first_name'] = p.first_name
                state['last_name'] = p.last_name
                state['birthdate'] = p.birthdate.strftime('%Y-%m-%d') if p.birthdate else ''
                state['gender'] = p.gender or ''
                state['notes'] = p.notes or ''

                # Versicherungen trennen (Aktiv vs. Historie)
                active = next((i for i in p.insurances if not i.is_deleted), None)
                state['active_insurance'] = {'id': active.id, 'name': active.name,
                                             'number': active.insurance_number} if active else None
                state['insurance_history'] = [{'id': i.id, 'name': i.name, 'number': i.insurance_number} for i in
                                              p.insurances if i.is_deleted]

    load_data()

    # ── Haupt-Speichern Funktion ──
    def save_patient():
        with get_session() as session:
            if patient_id:
                p = session.query(Patient).filter_by(id=patient_id).first()
            else:
                p = Patient()
                session.add(p)

            p.first_name = state['first_name']
            p.last_name = state['last_name']
            p.gender = state['gender']
            p.notes = state['notes']

            if state['birthdate']:
                try:
                    p.birthdate = datetime.strptime(state['birthdate'], '%Y-%m-%d').date()
                except ValueError:
                    ui.notify('Bitte das Format YYYY-MM-DD für das Datum nutzen.', type='negative')
                    return
            else:
                p.birthdate = None

            session.commit()

            if not patient_id:
                nicegui_app.storage.user['current_patient_id'] = p.id
                navigate('/patient_detail')
                return

            ui.notify('Patientendaten gespeichert', type='positive')

    # ── UI Header ──
    with ui.row().classes('items-center w-full mb-6 gap-4'):
        ui.button(icon='arrow_back', on_click=lambda: navigate('/patients')).props('flat round').classes(
            'text-gray-600 hover:bg-gray-100')
        ui.label("Patientenakte" if patient_id else "Neuer Patient").classes('text-[24px] font-semibold text-[#1e3a5f]')
        ui.space()
        ui.button('Speichern', icon='save', on_click=save_patient).props('unelevated').classes(
            'bg-[#0078d4] text-white')

    # ── LAYOUT: Splitter für vertikale Tabs ──
    with ui.splitter(value=20).classes('w-full') as splitter:

        # Linke Seite: Die Tabs (vertikal, icon-links, linksbündig, ohne Caps)
        with splitter.before:
            # Gemeinsame CSS-Klassen für alle Tabs (Linksbündig, volle Breite, kleinere Schrift)
            tab_classes = 'justify-start w-full text-[14px] text-slate-600 px-4'

            # props: 'vertical' = vertikal, 'inline-label' = Icon links vom Text, 'no-caps' = normale Groß-/Kleinschreibung
            with ui.tabs().props('vertical inline-label no-caps').classes('w-full mt-2') as tabs:
                personalien_tab = ui.tab('Personalien', icon='badge').classes(tab_classes)
                kontakt_tab = ui.tab('Kontaktangaben', icon='contact_mail').classes(tab_classes).set_enabled(
                    bool(patient_id))
                sitzungen_tab = ui.tab('Sitzungen', icon='event').classes(tab_classes).set_enabled(bool(patient_id))
                abrechnungen_tab = ui.tab('Abrechnungen', icon='receipt').classes(tab_classes).set_enabled(
                    bool(patient_id))

        # Rechte Seite: Der Inhalt
        with splitter.after:
            with ui.tab_panels(tabs, value=personalien_tab).classes('w-full bg-transparent pl-6'):

                # TAB 1: PERSONALIEN & VERSICHERUNG
                with ui.tab_panel(personalien_tab):

                    # Stammdaten
                    with ui.card().classes('w-full max-w-3xl p-6 shadow-sm mb-6'):
                        ui.label('Stammdaten').classes('text-[18px] font-medium mb-4 text-[#1e3a5f]')

                        with ui.row().classes('w-full gap-4 mb-4'):
                            ui.input('Vorname').bind_value(state, 'first_name').classes('flex-1').props(
                                'outlined dense')
                            ui.input('Nachname').bind_value(state, 'last_name').classes('flex-1').props(
                                'outlined dense')

                        with ui.row().classes('w-full gap-4 mb-4'):
                            ui.input('Geburtsdatum (YYYY-MM-DD)').bind_value(state, 'birthdate').classes(
                                'flex-1').props('outlined dense type="date"')
                            ui.select(['Männlich', 'Weiblich', 'Divers', 'Keine Angabe'],
                                      label='Geschlecht').bind_value(state, 'gender').classes('flex-1').props(
                                'outlined dense')

                        ui.textarea('Bemerkungen').bind_value(state, 'notes').classes('w-full').props('outlined')

                    # ── VERSICHERUNGSDIALOG & LOGIK ──
                    dialog_state = {'id': None}
                    dialog = ui.dialog()
                    with dialog, ui.card().classes('p-6 min-w-[400px]'):
                        ui.label('Krankenkasse').classes('text-lg font-bold mb-4')
                        new_name = ui.input('Name der Krankenkasse').classes('w-full mb-2').props('outlined dense')
                        new_number = ui.input('Versichertennummer').classes('w-full mb-4').props('outlined dense')

                        def save_insurance():
                            if not new_name.value:
                                return ui.notify('Name wird benötigt', type='warning')

                            with get_session() as session:
                                if dialog_state['id']:
                                    # EDITIEREN
                                    ins = session.query(PatientInsurance).filter_by(id=dialog_state['id']).first()
                                    if ins:
                                        ins.name = new_name.value
                                        ins.insurance_number = new_number.value
                                else:
                                    # NEU ANLEGEN
                                    p = session.query(Patient).filter_by(id=patient_id).first()
                                    for ins in p.insurances:
                                        ins.is_deleted = True
                                    new_ins = PatientInsurance(
                                        patient_id=patient_id,
                                        name=new_name.value,
                                        insurance_number=new_number.value,
                                        is_deleted=False
                                    )
                                    session.add(new_ins)
                                session.commit()

                            ui.notify('Versicherung gespeichert', type='positive')
                            dialog.close()
                            load_data()
                            render_insurance_section.refresh()

                        with ui.row().classes('w-full justify-end gap-2'):
                            ui.button('Abbrechen', on_click=dialog.close).props('flat text-color="grey"')
                            ui.button('Speichern', on_click=save_insurance).props('unelevated color="primary"')

                    def open_insurance_dialog(ins_id=None, name='', number=''):
                        dialog_state['id'] = ins_id
                        new_name.value = name
                        new_number.value = number
                        dialog.open()

                    def delete_insurance(ins_id):
                        with get_session() as session:
                            ins = session.query(PatientInsurance).filter_by(id=ins_id).first()
                            if ins:
                                session.delete(ins)
                                session.commit()
                        ui.notify('Versicherung permanent gelöscht', type='info')
                        load_data()
                        render_insurance_section.refresh()

                    # ── VERSICHERUNG UI BLOCK ──
                    @ui.refreshable
                    def render_insurance_section():
                        if not patient_id: return
                        with ui.card().classes('w-full max-w-3xl p-6 shadow-sm border-l-4 border-[#0078d4]'):
                            with ui.row().classes('w-full items-center justify-between mb-4'):
                                ui.label('Krankenversicherung').classes('text-[18px] font-medium text-[#1e3a5f]')
                                ui.button('Neu', icon='add', on_click=lambda: open_insurance_dialog()).props(
                                    'outline dense').classes('text-[#0078d4]')

                            if state['active_insurance']:
                                act = state['active_insurance']
                                with ui.row().classes(
                                        'w-full items-center justify-between bg-blue-50 p-3 rounded mb-4'):
                                    with ui.column().classes('gap-0'):
                                        ui.label(act['name']).classes('font-semibold text-slate-800')
                                        ui.label(f"Versicherten-Nr: {act['number']}").classes('text-sm text-slate-500')
                                    with ui.row().classes('gap-1'):
                                        ui.button(icon='edit',
                                                  on_click=lambda: open_insurance_dialog(act['id'], act['name'],
                                                                                         act['number'])).props(
                                            'flat round dense color="primary"')
                                        ui.button(icon='delete', on_click=lambda: delete_insurance(act['id'])).props(
                                            'flat round dense color="negative"')
                            else:
                                ui.label('Keine aktive Versicherung hinterlegt.').classes('text-slate-500 italic mb-4')

                            if state['insurance_history']:
                                with ui.expansion('Versicherungs-Historie anzeigen').classes(
                                        'w-full shadow-none border border-slate-200'):
                                    for old in state['insurance_history']:
                                        with ui.row().classes(
                                                'w-full items-center justify-between p-2 border-b border-slate-100 last:border-0'):
                                            with ui.column().classes('gap-0'):
                                                ui.label(old['name']).classes('text-sm text-gray-500 line-through')
                                                ui.label(f"Nr: {old['number']}").classes('text-xs text-gray-400')
                                            with ui.row().classes('gap-1'):
                                                ui.button(icon='edit',
                                                          on_click=lambda o=old: open_insurance_dialog(o['id'],
                                                                                                       o['name'], o[
                                                                                                           'number'])).props(
                                                    'flat round dense color="primary" size="sm"')
                                                ui.button(icon='delete',
                                                          on_click=lambda o=old: delete_insurance(o['id'])).props(
                                                    'flat round dense color="negative" size="sm"')

                    render_insurance_section()

                # Leere Platzhalter für die nächsten Tabs
                with ui.tab_panel(kontakt_tab):
                    ui.label('Hier kommen die dynamischen Adressen, E-Mails und Telefonnummern hin...').classes(
                        'text-lg')
                with ui.tab_panel(sitzungen_tab):
                    ui.label('Sitzungen kommen hier hin...').classes('text-lg')
                with ui.tab_panel(abrechnungen_tab):
                    ui.label('Abrechnungen kommen hier hin...').classes('text-lg')
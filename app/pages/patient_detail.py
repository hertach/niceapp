# app/pages/patient_detail.py
from datetime import datetime
from nicegui import ui, app as nicegui_app
from app.core.database import get_session
from app.models.patient import Patient, PatientInsurance, PatientAddress, PatientPhone, PatientEmail


def patient_detail_page(navigate) -> None:
    patient_id = nicegui_app.storage.user.get('current_patient_id')

    # ── 1. ZENTRALER STATE ──
    state = {
        'active_tab': 'Personalien',
        'first_name': '', 'last_name': '', 'birthdate': '', 'gender': '', 'notes': '',
        'ins_active': None, 'ins_history': [],
        'phones': [], 'emails': [], 'addresses': []
    }

    def load_data():
        if not patient_id: return
        with get_session() as session:
            p = session.query(Patient).filter_by(id=patient_id).first()
            if not p: return

            state['first_name'] = p.first_name or ''
            state['last_name'] = p.last_name or ''
            state['birthdate'] = p.birthdate.strftime('%Y-%m-%d') if p.birthdate else ''
            state['gender'] = p.gender or ''
            state['notes'] = p.notes or ''

            insurances = getattr(p, 'insurances', [])
            act = next((i for i in insurances if not getattr(i, 'is_deleted', False)), None)
            state['ins_active'] = {'id': act.id, 'name': act.name, 'number': act.insurance_number} if act else None
            state['ins_history'] = [{'id': i.id, 'name': i.name, 'number': i.insurance_number} for i in insurances if
                                    getattr(i, 'is_deleted', False)]

            state['phones'] = [{'id': ph.id, 'number': getattr(ph, 'number', ''), 'type': getattr(ph, 'type', 'Privat'),
                                'is_main': getattr(ph, 'is_main', False)} for ph in getattr(p, 'phones', []) if
                               not getattr(ph, 'is_deleted', False)]
            state['emails'] = [{'id': e.id, 'email': getattr(e, 'email', ''), 'type': getattr(e, 'type', 'Privat'),
                                'is_main': getattr(e, 'is_main', False)} for e in getattr(p, 'emails', []) if
                               not getattr(e, 'is_deleted', False)]
            state['addresses'] = [
                {'id': a.id, 'street': getattr(a, 'street', ''), 'zip_code': getattr(a, 'zip_code', ''),
                 'city': getattr(a, 'city', ''), 'is_main': getattr(a, 'is_main', False)} for a in
                getattr(p, 'addresses', []) if not getattr(a, 'is_deleted', False)]

    try:
        load_data()
    except Exception as e:
        ui.notify(f"Datenbankfehler: {e}", type='negative')

    # ── 2. GLOBALE DIALOGE ──

    # --- Versicherung ---
    ins_state = {'id': None}
    ins_dlg = ui.dialog()
    with ins_dlg, ui.card().classes('p-6 min-w-[400px]'):
        ui.label('Krankenkasse').classes('text-lg font-bold mb-4')
        ins_name_in = ui.input('Name').classes('w-full mb-2').props('outlined dense')
        ins_num_in = ui.input('Versichertennummer').classes('w-full mb-4').props('outlined dense')

        def save_ins():
            if not ins_name_in.value: return ui.notify('Name benötigt', type='warning')
            with get_session() as session:
                if ins_state['id']:
                    ins = session.query(PatientInsurance).filter_by(id=ins_state['id']).first()
                    if ins: ins.name, ins.insurance_number = ins_name_in.value, ins_num_in.value
                else:
                    p = session.query(Patient).filter_by(id=patient_id).first()
                    for ins in getattr(p, 'insurances', []): ins.is_deleted = True
                    session.add(PatientInsurance(patient_id=patient_id, name=ins_name_in.value,
                                                 insurance_number=ins_num_in.value, is_deleted=False))
                session.commit()
            ins_dlg.close();
            load_data();
            main_content.refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Abbrechen', on_click=ins_dlg.close).props('flat text-color="grey"')
            ui.button('Speichern', on_click=save_ins).props('unelevated color="primary"')

    def open_ins(item=None):
        ins_state['id'] = item['id'] if item else None
        ins_name_in.value = item['name'] if item else ''
        ins_num_in.value = item['number'] if item else ''
        ins_dlg.open()

    # --- Telefon ---
    phone_state = {'id': None}
    phone_dlg = ui.dialog()
    with phone_dlg, ui.card().classes('p-6 min-w-[400px]'):
        ui.label('Telefonnummer').classes('text-lg font-bold mb-4')
        phone_num_in = ui.input('Nummer').classes('w-full mb-2').props('outlined dense')
        phone_type_in = ui.select(['Privat', 'Geschäftlich', 'Mobil', 'Andere'], label='Typ').classes(
            'w-full mb-2').props('outlined dense')
        phone_main_in = ui.checkbox('Als Hauptnummer festlegen').classes('mb-4')

        def save_phone():
            if not phone_num_in.value: return ui.notify('Nummer benötigt', type='warning')
            with get_session() as session:
                p = session.query(Patient).filter_by(id=patient_id).first()
                if phone_main_in.value:
                    for ph in getattr(p, 'phones', []): ph.is_main = False
                if phone_state['id']:
                    ph = session.query(PatientPhone).filter_by(id=phone_state['id']).first()
                    ph.number, ph.type, ph.is_main = phone_num_in.value, phone_type_in.value, phone_main_in.value
                else:
                    session.add(PatientPhone(patient_id=patient_id, number=phone_num_in.value, type=phone_type_in.value,
                                             is_main=phone_main_in.value))
                session.commit()
            phone_dlg.close();
            load_data();
            main_content.refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Abbrechen', on_click=phone_dlg.close).props('flat text-color="grey"')
            ui.button('Speichern', on_click=save_phone).props('unelevated color="primary"')

    def open_phone(item=None):
        phone_state['id'] = item['id'] if item else None
        phone_num_in.value = item['number'] if item else ''
        phone_type_in.value = item['type'] if item else 'Privat'
        phone_main_in.value = item['is_main'] if item else False
        phone_dlg.open()

    # --- E-Mail ---
    email_state = {'id': None}
    email_dlg = ui.dialog()
    with email_dlg, ui.card().classes('p-6 min-w-[400px]'):
        ui.label('E-Mail Adresse').classes('text-lg font-bold mb-4')
        email_val_in = ui.input('E-Mail').classes('w-full mb-2').props('outlined dense type="email"')
        email_type_in = ui.select(['Privat', 'Geschäftlich', 'Andere'], label='Typ').classes('w-full mb-2').props(
            'outlined dense')
        email_main_in = ui.checkbox('Als Hauptadresse festlegen').classes('mb-4')

        def save_email():
            if not email_val_in.value: return ui.notify('E-Mail benötigt', type='warning')
            with get_session() as session:
                p = session.query(Patient).filter_by(id=patient_id).first()
                if email_main_in.value:
                    for em in getattr(p, 'emails', []): em.is_main = False
                if email_state['id']:
                    em = session.query(PatientEmail).filter_by(id=email_state['id']).first()
                    em.email, em.type, em.is_main = email_val_in.value, email_type_in.value, email_main_in.value
                else:
                    session.add(PatientEmail(patient_id=patient_id, email=email_val_in.value, type=email_type_in.value,
                                             is_main=email_main_in.value))
                session.commit()
            email_dlg.close();
            load_data();
            main_content.refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Abbrechen', on_click=email_dlg.close).props('flat text-color="grey"')
            ui.button('Speichern', on_click=save_email).props('unelevated color="primary"')

    def open_email(item=None):
        email_state['id'] = item['id'] if item else None
        email_val_in.value = item['email'] if item else ''
        email_type_in.value = item['type'] if item else 'Privat'
        email_main_in.value = item['is_main'] if item else False
        email_dlg.open()

    # --- Adresse ---
    addr_state = {'id': None}
    addr_dlg = ui.dialog()
    with addr_dlg, ui.card().classes('p-6 min-w-[500px]'):
        ui.label('Postadresse').classes('text-lg font-bold mb-4')
        addr_st_in = ui.input('Straße & Hausnummer').classes('w-full mb-2').props('outlined dense')
        with ui.row().classes('w-full gap-2 mb-2'):
            addr_zip_in = ui.input('PLZ').classes('w-[100px]').props('outlined dense')
            addr_city_in = ui.input('Ort').classes('flex-1').props('outlined dense')
        addr_main_in = ui.checkbox('Als Hauptwohnsitz festlegen').classes('mb-4')

        def save_address():
            with get_session() as session:
                p = session.query(Patient).filter_by(id=patient_id).first()
                if addr_main_in.value:
                    for a in getattr(p, 'addresses', []): a.is_main = False
                if addr_state['id']:
                    a = session.query(PatientAddress).filter_by(id=addr_state['id']).first()
                    a.street, a.zip_code, a.city, a.is_main = addr_st_in.value, addr_zip_in.value, addr_city_in.value, addr_main_in.value
                else:
                    session.add(
                        PatientAddress(patient_id=patient_id, street=addr_st_in.value, zip_code=addr_zip_in.value,
                                       city=addr_city_in.value, is_main=addr_main_in.value))
                session.commit()
            addr_dlg.close();
            load_data();
            main_content.refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Abbrechen', on_click=addr_dlg.close).props('flat text-color="grey"')
            ui.button('Speichern', on_click=save_address).props('unelevated color="primary"')

    def open_addr(item=None):
        addr_state['id'] = item['id'] if item else None
        addr_st_in.value = item['street'] if item else ''
        addr_zip_in.value = item['zip_code'] if item else ''
        addr_city_in.value = item['city'] if item else ''
        addr_main_in.value = item['is_main'] if item else False
        addr_dlg.open()

    # --- Lösch-Helfer ---
    def hard_delete(model_class, item_id):
        with get_session() as session:
            item = session.query(model_class).filter_by(id=item_id).first()
            if item: session.delete(item); session.commit()
        load_data();
        main_content.refresh()

    def soft_delete(model_class, item_id):
        with get_session() as session:
            item = session.query(model_class).filter_by(id=item_id).first()
            if item: item.is_deleted = True; session.commit()
        load_data();
        main_content.refresh()

    # ── 3. MAIN SAVE FUNKTION ──
    def save_basic():
        with get_session() as session:
            p = session.query(Patient).filter_by(id=patient_id).first() if patient_id else Patient()
            if not patient_id: session.add(p)

            p.first_name, p.last_name = state['first_name'], state['last_name']
            p.gender, p.notes = state['gender'], state['notes']

            if state['birthdate']:
                try:
                    p.birthdate = datetime.strptime(state['birthdate'], '%Y-%m-%d').date()
                except ValueError:
                    return ui.notify('Format YYYY-MM-DD nutzen.', type='negative')
            else:
                p.birthdate = None

            session.commit()
            if not patient_id:
                nicegui_app.storage.user['current_patient_id'] = p.id
                navigate('/patient_detail')
                return
            ui.notify('Stammdaten gespeichert', type='positive')

    # ── 4. KUGELSICHERES CUSTOM-LAYOUT ──
    with ui.row().classes('items-center w-full mb-6 gap-4'):
        ui.button(icon='arrow_back', on_click=lambda: navigate('/patients')).props('flat round').classes(
            'text-gray-600 hover:bg-gray-100')
        ui.label("Patientenakte" if patient_id else "Neuer Patient").classes('text-[24px] font-semibold text-[#1e3a5f]')
        ui.space()
        ui.button('Speichern', icon='save', on_click=save_basic).props('unelevated').classes('bg-[#0078d4] text-white')

    with ui.splitter(value=15).classes('w-full') as splitter:

        # LINKE SEITE: Custom Menü
        with splitter.before:
            def set_tab(t):
                state['active_tab'] = t
                menu_col.refresh()
                main_content.refresh()

            def get_btn_class(t):
                # Kein font-bold mehr, nur die Farben ändern sich
                base = 'w-full px-4 py-3 text-[14px] rounded-none transition-colors border-r-4 '
                return base + ('bg-blue-50 text-blue-700 border-blue-500' if state[
                                                                                 'active_tab'] == t else 'text-slate-600 hover:bg-slate-50 border-transparent')

            @ui.refreshable
            def menu_col():
                with ui.column().classes('w-full gap-0 mt-2'):
                    # props='flat align="left" no-caps' erzwingt die Linksbündigkeit und Groß-/Kleinschreibung direkt bei Quasar
                    btn_props = 'flat align="left" no-caps'

                    ui.button('Personalien', icon='badge', on_click=lambda: set_tab('Personalien')).classes(
                        get_btn_class('Personalien')).props(btn_props)
                    btn_k = ui.button('Kontaktangaben', icon='contact_mail',
                                      on_click=lambda: set_tab('Kontaktangaben')).classes(
                        get_btn_class('Kontaktangaben')).props(btn_props)
                    btn_s = ui.button('Sitzungen', icon='event', on_click=lambda: set_tab('Sitzungen')).classes(
                        get_btn_class('Sitzungen')).props(btn_props)
                    btn_a = ui.button('Abrechnungen', icon='receipt', on_click=lambda: set_tab('Abrechnungen')).classes(
                        get_btn_class('Abrechnungen')).props(btn_props)

                    if not patient_id:
                        btn_k.disable();
                        btn_s.disable();
                        btn_a.disable()

            menu_col()

        # RECHTE SEITE: Refreshable Content Area
        with splitter.after:
            @ui.refreshable
            def main_content():
                with ui.column().classes('w-full pl-6'):

                    if state['active_tab'] == 'Personalien':
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

                        if patient_id:
                            with ui.card().classes('w-full max-w-3xl p-6 shadow-sm border-l-4 border-[#0078d4]'):
                                with ui.row().classes('w-full items-center justify-between mb-4'):
                                    ui.label('Krankenversicherung').classes('text-[18px] font-medium text-[#1e3a5f]')
                                    ui.button('Neu', icon='add', on_click=lambda: open_ins()).props(
                                        'outline dense').classes('text-[#0078d4]')

                                act = state['ins_active']
                                if act:
                                    with ui.row().classes(
                                            'w-full items-center justify-between bg-blue-50 p-3 rounded mb-4'):
                                        with ui.column().classes('gap-0'):
                                            ui.label(act['name']).classes('font-semibold text-slate-800')
                                            ui.label(f"Versicherten-Nr: {act['number']}").classes(
                                                'text-sm text-slate-500')
                                        with ui.row().classes('gap-1'):
                                            ui.button(icon='edit', on_click=lambda: open_ins(act)).props(
                                                'flat round dense color="primary"')
                                            ui.button(icon='delete',
                                                      on_click=lambda: hard_delete(PatientInsurance, act['id'])).props(
                                                'flat round dense color="negative"')
                                else:
                                    ui.label('Keine aktive Versicherung hinterlegt.').classes(
                                        'text-slate-500 italic mb-4')

                                if state['ins_history']:
                                    with ui.expansion('Versicherungs-Historie anzeigen').classes(
                                            'w-full shadow-none border border-slate-200'):
                                        for old in state['ins_history']:
                                            with ui.row().classes(
                                                    'w-full items-center justify-between p-2 border-b border-slate-100 last:border-0'):
                                                with ui.column().classes('gap-0'):
                                                    ui.label(old['name']).classes('text-sm text-gray-500 line-through')
                                                    ui.label(f"Nr: {old['number']}").classes('text-xs text-gray-400')
                                                with ui.row().classes('gap-1'):
                                                    ui.button(icon='edit', on_click=lambda o=old: open_ins(o)).props(
                                                        'flat round dense color="primary" size="sm"')
                                                    ui.button(icon='delete',
                                                              on_click=lambda o=old: hard_delete(PatientInsurance,
                                                                                                 o['id'])).props(
                                                        'flat round dense color="negative" size="sm"')

                    elif state['active_tab'] == 'Kontaktangaben':
                        def draw_list(title, items, open_fn, model_cls, format_main, format_sub):
                            with ui.card().classes('w-full max-w-3xl p-6 shadow-sm mb-6'):
                                with ui.row().classes('w-full items-center justify-between mb-4'):
                                    ui.label(title).classes('text-[18px] font-medium text-[#1e3a5f]')
                                    ui.button('Neu', icon='add', on_click=lambda: open_fn()).props(
                                        'outline dense').classes('text-[#0078d4]')

                                if not items: ui.label('Noch keine Einträge vorhanden.').classes(
                                    'text-slate-400 italic')

                                for item in sorted(items, key=lambda x: not x['is_main']):
                                    with ui.row().classes(
                                            'w-full items-center justify-between p-2 border-b border-slate-100 last:border-0'):
                                        with ui.row().classes('items-center gap-3'):
                                            ui.icon('star',
                                                    color='amber' if item['is_main'] else 'transparent').classes(
                                                'text-lg')
                                            with ui.column().classes('gap-0'):
                                                ui.label(format_main(item)).classes('font-medium')
                                                ui.label(format_sub(item)).classes('text-xs text-slate-500')
                                        with ui.row().classes('gap-1'):
                                            ui.button(icon='edit', on_click=lambda i=item: open_fn(i)).props(
                                                'flat round dense color="primary" size="sm"')
                                            ui.button(icon='delete', on_click=lambda i=item, m=model_cls: soft_delete(m,
                                                                                                                      i[
                                                                                                                          'id'])).props(
                                                'flat round dense color="negative" size="sm"')

                        draw_list('Telefonnummern', state['phones'], open_phone, PatientPhone, lambda i: i['number'],
                                  lambda i: i['type'])
                        draw_list('E-Mail Adressen', state['emails'], open_email, PatientEmail, lambda i: i['email'],
                                  lambda i: i['type'])
                        draw_list('Postadressen', state['addresses'], open_addr, PatientAddress, lambda i: i['street'],
                                  lambda i: f"{i['zip_code']} {i['city']}")

                    elif state['active_tab'] == 'Sitzungen':
                        ui.label('Sitzungen kommen hier hin...').classes('text-lg text-slate-500')

                    elif state['active_tab'] == 'Abrechnungen':
                        ui.label('Abrechnungen kommen hier hin...').classes('text-lg text-slate-500')

            main_content()
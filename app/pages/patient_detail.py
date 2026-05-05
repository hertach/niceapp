# app/pages/patient_detail.py
import os
import base64
import tempfile
import asyncio
from datetime import datetime
from nicegui import ui, app as nicegui_app
from app.core.database import get_session
from app.models.patient import Patient, PatientInsurance, PatientAddress, PatientPhone, PatientEmail, PatientSession

# ── 100% OFFLINE KI-SPRACHERKENNUNG INITIALISIEREN ──
try:
    from faster_whisper import WhisperModel

    print("Lade Whisper-Modell...")
    whisper_model = WhisperModel("small", device="cpu", compute_type="default")
    print("Whisper-Modell erfolgreich geladen!")
except ImportError:
    whisper_model = None
    print("FEHLER: faster-whisper ist nicht installiert!")


def patient_detail_page(navigate) -> None:
    patient_id = nicegui_app.storage.user.get('current_patient_id')

    state = {
        'active_tab': 'Personalien',
        'first_name': '', 'last_name': '', 'birthdate': '', 'gender': '', 'notes': '',
        'ins_active': None, 'ins_history': [],
        'phones': [], 'emails': [], 'addresses': [],
        'sessions': [],
        'sess_id': None, 'sess_date': '', 'sess_time_from': '', 'sess_time_to': '',
        'sess_issue': '', 'sess_approach': '', 'sess_protocol': '',
        'sess_billing_type': 'Selbstzahler', 'sess_is_paid': False, 'sess_amount': 0.0,
        'recording_field': None,
        'recording_original_text': ''
    }

    mic_buttons = {}
    textareas = {}

    # NEU: Das Lock-System (Die Ampel für die KI)
    ai_lock = {'is_busy': False}

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

    # ── OFFLINE STREAMING TRANSKRIBIERUNG ──
    async def toggle_recording(state_key):
        if not whisper_model:
            return ui.notify('faster-whisper ist nicht verfügbar!', type='negative')

        btn = mic_buttons.get(state_key)
        area = textareas.get(state_key)

        js_setup = '''
        if (typeof window.startLiveRecord === 'undefined') {
            window.startLiveRecord = async function() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
                    window.liveRecorder = new MediaRecorder(stream);
                    window.liveChunks = [];
                    window.liveRecorder.ondataavailable = e => {
                        if (e.data.size > 0) window.liveChunks.push(e.data);
                    };
                    window.liveRecorder.start(1000); 
                    return "OK";
                } catch (err) {
                    return "ERR_NO_MIC";
                }
            };
            window.getLiveAudio = async function() {
                if (!window.liveChunks || window.liveChunks.length === 0) return null;
                const blob = new Blob(window.liveChunks, {type: window.liveRecorder.mimeType || 'audio/webm'});
                return new Promise(resolve => {
                    const reader = new FileReader();
                    reader.onloadend = () => resolve(reader.result);
                    reader.readAsDataURL(blob);
                });
            };
            window.stopLiveRecord = function() {
                if (window.liveRecorder && window.liveRecorder.state !== 'inactive') {
                    window.liveRecorder.stop();
                    window.liveRecorder.stream.getTracks().forEach(t => t.stop());
                }
            };
        }
        '''
        await ui.run_javascript(js_setup)

        # 1. AUFNAHME STARTEN
        if state['recording_field'] is None:
            try:
                res = await ui.run_javascript('return await window.startLiveRecord();', timeout=60.0)
                if res == "ERR_NO_MIC":
                    return ui.notify('Mikrofon blockiert!', type='negative')
            except TimeoutError:
                return ui.notify('Zeitüberschreitung beim Mikrofon.', type='warning')

            state['recording_field'] = state_key
            state['recording_original_text'] = state[state_key] or ''
            ai_lock['is_busy'] = False

            if btn:
                btn.props('color=negative icon=stop')
                btn.update()
            ui.notify('Live-Aufnahme läuft...', type='info', timeout=3.0)

            # --- Hintergrundprozess für das Live-Streaming ---
            async def live_transcription_loop():
                spacer = '\n\n' if state['recording_original_text'] else ''

                while state['recording_field'] == state_key:
                    await asyncio.sleep(2.0)
                    if state['recording_field'] != state_key:
                        break

                        # === DIE AMPEL: Überspringen, wenn die KI bei einem langen Text noch rechnet! ===
                    if ai_lock['is_busy']:
                        continue

                    try:
                        b64 = await ui.run_javascript('return await window.getLiveAudio();', timeout=5.0)
                    except Exception:
                        continue

                    if not b64 or not b64.startswith('data:audio'): continue

                    # Ampel auf ROT setzen (KI blockieren)
                    ai_lock['is_busy'] = True

                    try:
                        header, encoded = b64.split(",", 1)
                        audio_data = base64.b64decode(encoded)

                        sys_tmp = tempfile.gettempdir()
                        tmp_path = os.path.join(sys_tmp, f"live_audio_{datetime.now().timestamp()}.webm")

                        with open(tmp_path, "wb") as f:
                            f.write(audio_data)

                        segments, _ = await asyncio.to_thread(
                            whisper_model.transcribe, tmp_path, language="de"
                        )
                        text = " ".join([s.text for s in segments]).strip()

                        if text:
                            state[state_key] = f"{state['recording_original_text']}{spacer}{text}"
                            if area: area.update()

                    except Exception as e:
                        pass
                    finally:
                        if 'tmp_path' in locals() and os.path.exists(tmp_path):
                            os.remove(tmp_path)
                        # Ampel auf GRÜN setzen (KI wieder freigeben)
                        ai_lock['is_busy'] = False

            asyncio.create_task(live_transcription_loop())


        # 2. AUFNAHME BEENDEN & FINALISIEREN
        elif state['recording_field'] == state_key:
            state['recording_field'] = None

            if btn:
                btn.props('color=warning icon=hourglass_empty')
                btn.update()

            ui.notify('Finalisiere Text... (bitte kurz warten)', type='info', timeout=5.0)

            # === WICHTIG: Warten, bis der letzte Live-Loop fertig gerechnet hat, bevor wir finalisieren ===
            while ai_lock['is_busy']:
                await asyncio.sleep(0.5)

            try:
                await ui.run_javascript('window.stopLiveRecord();')
                b64 = await ui.run_javascript('return await window.getLiveAudio();', timeout=10.0)

                if b64 and b64.startswith('data:audio'):
                    header, encoded = b64.split(",", 1)
                    audio_data = base64.b64decode(encoded)

                    sys_tmp = tempfile.gettempdir()
                    tmp_path = os.path.join(sys_tmp, f"final_audio_{datetime.now().timestamp()}.webm")

                    try:
                        with open(tmp_path, "wb") as f:
                            f.write(audio_data)

                        segments, _ = await asyncio.to_thread(
                            whisper_model.transcribe, tmp_path, language="de"
                        )
                        text = " ".join([s.text for s in segments]).strip()
                        spacer = '\n\n' if state['recording_original_text'] else ''

                        if text:
                            state[state_key] = f"{state['recording_original_text']}{spacer}{text}"
                            if area: area.update()

                    except Exception as e:
                        print(f"Finaler Fehler: {e}")
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
            except Exception as e:
                print(f"JavaScript Fehler: {e}")
            finally:
                if btn:
                    btn.props('color=grey icon=mic')
                    btn.update()
                ui.notify('Erfassung abgeschlossen!', type='positive', timeout=3.0)

        else:
            ui.notify('Bitte beende zuerst die andere laufende Aufnahme!', type='warning')

    # ── 2. GLOBALE DIALOGE (Versicherung, Kontakte...) ──
    ins_state = {'id': None}
    ins_dlg = ui.dialog()
    with ins_dlg, ui.card().classes('p-6 min-w-[400px]'):
        ui.label('Krankenkasse').classes('text-lg font-bold mb-4')
        ins_name_in = ui.input('Name').classes('w-full mb-2').props('outlined dense')
        ins_num_in = ui.input('Versichertennummer').classes('w-full mb-4').props('outlined dense')

        def save_ins():
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

    phone_state = {'id': None}
    phone_dlg = ui.dialog()
    with phone_dlg, ui.card().classes('p-6 min-w-[400px]'):
        ui.label('Telefonnummer').classes('text-lg font-bold mb-4')
        phone_num_in = ui.input('Nummer').classes('w-full mb-2').props('outlined dense')
        phone_type_in = ui.select(['Privat', 'Geschäftlich', 'Mobil', 'Andere'], label='Typ').classes(
            'w-full mb-2').props('outlined dense')
        phone_main_in = ui.checkbox('Als Hauptnummer festlegen').classes('mb-4')

        def save_phone():
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

    email_state = {'id': None}
    email_dlg = ui.dialog()
    with email_dlg, ui.card().classes('p-6 min-w-[400px]'):
        ui.label('E-Mail Adresse').classes('text-lg font-bold mb-4')
        email_val_in = ui.input('E-Mail').classes('w-full mb-2').props('outlined dense type="email"')
        email_type_in = ui.select(['Privat', 'Geschäftlich', 'Andere'], label='Typ').classes('w-full mb-2').props(
            'outlined dense')
        email_main_in = ui.checkbox('Als Hauptadresse festlegen').classes('mb-4')

        def save_email():
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

    # ── SITZUNGS-DIALOG ──
    sess_dlg = ui.dialog()
    with sess_dlg, ui.card().classes('p-6 min-w-[700px] max-w-[800px]'):
        with ui.row().classes('w-full justify-between items-center mb-4'):
            ui.label('Sitzungsdetails').classes('text-lg font-bold')
            ui.button(icon='close', on_click=sess_dlg.close).props('flat round dense')

        with ui.row().classes('w-full gap-4 mb-4'):
            ui.input('Datum').bind_value(state, 'sess_date').classes('flex-1').props('outlined dense type="date"')
            ui.input('Von').bind_value(state, 'sess_time_from').classes('w-[100px]').props('outlined dense type="time"')
            ui.input('Bis').bind_value(state, 'sess_time_to').classes('w-[100px]').props('outlined dense type="time"')

        def voice_area(label, state_key):
            with ui.row().classes('w-full items-start gap-2 mb-4'):
                t_area = ui.textarea(label).bind_value(state, state_key).classes('flex-1').props('outlined rows="10"')
                textareas[state_key] = t_area

                btn = ui.button(icon='mic', on_click=lambda: toggle_recording(state_key)).props(
                    'flat round color="grey"').tooltip('Push-to-Talk')
                mic_buttons[state_key] = btn

        voice_area('Anliegen / Thema', 'sess_issue')
        voice_area('Lösungsansatz / Intervention', 'sess_approach')
        voice_area('Protokoll / Notizen', 'sess_protocol')

        ui.separator().classes('my-4')

        with ui.row().classes('w-full gap-4 mb-4 items-center'):
            ui.select(['Selbstzahler', 'Zusatzversicherung', 'Grundversicherung', 'IV'],
                      label='Abrechnungsart').bind_value(state, 'sess_billing_type').classes('flex-1').props(
                'outlined dense')
            ui.input('Betrag (CHF)').bind_value(state, 'sess_amount').classes('w-[150px]').props(
                'outlined dense type="number" step="0.05"')
            ui.checkbox('Bezahlt').bind_value(state, 'sess_is_paid')

        def save_session():
            if not state['sess_date']: return ui.notify('Datum ist Pflichtfeld', type='warning')
            with get_session() as session:
                if state['sess_id']:
                    s = session.query(PatientSession).filter_by(id=state['sess_id']).first()
                else:
                    s = PatientSession(patient_id=patient_id)
                    session.add(s)

                s.date = datetime.strptime(state['sess_date'], '%Y-%m-%d').date()
                s.time_from = state['sess_time_from']
                s.time_to = state['sess_time_to']
                s.issue = state['sess_issue']
                s.approach = state['sess_approach']
                s.protocol = state['sess_protocol']
                s.billing_type = state['sess_billing_type']
                s.is_paid = state['sess_is_paid']

                try:
                    s.amount = float(state['sess_amount'])
                except:
                    s.amount = 0.0

                session.commit()
            sess_dlg.close();
            load_data();
            main_content.refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Speichern', on_click=save_session).props('unelevated color="primary"')

    def open_session(s=None):
        state.update({
            'sess_id': getattr(s, 'id', None) if s else None,
            'sess_date': s.date.strftime('%Y-%m-%d') if s and getattr(s, 'date', None) else datetime.now().strftime(
                '%Y-%m-%d'),
            'sess_time_from': getattr(s, 'time_from', ''),
            'sess_time_to': getattr(s, 'time_to', ''),
            'sess_issue': getattr(s, 'issue', ''),
            'sess_approach': getattr(s, 'approach', ''),
            'sess_protocol': getattr(s, 'protocol', ''),
            'sess_billing_type': getattr(s, 'billing_type', 'Selbstzahler'),
            'sess_is_paid': getattr(s, 'is_paid', False),
            'sess_amount': getattr(s, 'amount', 0.0)
        })
        sess_dlg.open()

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

    with ui.row().classes('items-center w-full mb-6 gap-4'):
        ui.button(icon='arrow_back', on_click=lambda: navigate('/patients')).props('flat round').classes(
            'text-gray-600 hover:bg-gray-100')
        ui.label("Patientenakte" if patient_id else "Neuer Patient").classes('text-[24px] font-semibold text-[#1e3a5f]')
        ui.space()
        ui.button('Speichern', icon='save', on_click=save_basic).props('unelevated').classes('bg-[#0078d4] text-white')

    with ui.splitter(value=15).classes('w-full') as splitter:
        with splitter.before:
            def set_tab(t):
                state['active_tab'] = t
                menu_col.refresh()
                main_content.refresh()

            def get_btn_class(t):
                base = 'w-full px-4 py-3 text-[14px] rounded-none transition-colors border-l-4 '
                return base + ('bg-blue-50 text-blue-700 border-blue-500' if state[
                                                                                 'active_tab'] == t else 'text-slate-600 hover:bg-slate-50 border-transparent')

            @ui.refreshable
            def menu_col():
                with ui.column().classes('w-full gap-0 mt-2'):
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
                            ui.textarea('Bemerkungen').bind_value(state, 'notes').classes('w-full').props(
                                'outlined rows="4"')

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
                        with get_session() as session:
                            p = session.query(Patient).filter_by(id=patient_id).first()
                            sitzungen = [s for s in getattr(p, 'sessions', []) if
                                         not getattr(s, 'is_deleted', False)] if p else []
                            sitzungen.sort(key=lambda x: x.date, reverse=True)

                        with ui.row().classes('w-full max-w-4xl justify-between items-center mb-6'):
                            ui.label('Sitzungshistorie').classes('text-[20px] font-medium text-[#1e3a5f]')
                            ui.button('Neue Sitzung', icon='add', on_click=lambda: open_session()).props(
                                'unelevated').classes('bg-[#0078d4] text-white')

                        if not sitzungen:
                            ui.label('Noch keine Sitzungen erfasst.').classes('text-slate-400 italic')

                        for s in sitzungen:
                            date_str = s.date.strftime('%d.%m.%Y')
                            time_str = f" | {s.time_from} - {s.time_to} Uhr" if (s.time_from and s.time_to) else ""
                            paid_str = "Bezahlt" if s.is_paid else "Offen"

                            header_text = f"{date_str}{time_str} | CHF {s.amount:.2f} ({paid_str})"

                            with ui.expansion(header_text, icon='event').classes(
                                    'w-full max-w-4xl shadow-sm border border-slate-200 mb-2 bg-white rounded'):
                                with ui.column().classes('w-full p-4 gap-4'):
                                    if s.issue:
                                        with ui.column().classes('gap-1'):
                                            ui.label('Anliegen').classes('font-bold text-slate-700 text-sm')
                                            ui.label(s.issue).classes('text-slate-600 whitespace-pre-line')
                                    if s.approach:
                                        with ui.column().classes('gap-1'):
                                            ui.label('Lösungsansatz').classes('font-bold text-slate-700 text-sm')
                                            ui.label(s.approach).classes('text-slate-600 whitespace-pre-line')
                                    if s.protocol:
                                        with ui.column().classes('gap-1'):
                                            ui.label('Protokoll').classes('font-bold text-slate-700 text-sm')
                                            ui.label(s.protocol).classes('text-slate-600 whitespace-pre-line')

                                    ui.separator()
                                    with ui.row().classes('w-full justify-between items-center'):
                                        ui.label(f"Abrechnungsart: {s.billing_type}").classes('text-xs text-slate-400')
                                        with ui.row().classes('gap-2'):
                                            ui.button('Löschen',
                                                      on_click=lambda idx=s.id: soft_delete(PatientSession, idx)).props(
                                                'flat color="negative" size="sm"')
                                            ui.button('Bearbeiten', on_click=lambda item=s: open_session(item)).props(
                                                'outline color="primary" size="sm"')

                    elif state['active_tab'] == 'Abrechnungen':
                        ui.label('Abrechnungen kommen hier hin...').classes('text-lg text-slate-500')

            main_content()
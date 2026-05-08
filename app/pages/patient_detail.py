# app/pages/patient_detail.py
import asyncio
import base64
import json
import os
import tempfile
import urllib.request
import zipfile
from datetime import date, datetime
from nicegui import app as nicegui_app, ui
from app.core.logger import app_logger
from sqlalchemy.orm import joinedload
from app.components.document_dialog import open_document_dialog
from app.core.database import get_session
from app.core.speech import SpeechManager
from app.models.app_setting import AppSetting
from app.models.finance_setting import PaymentMethod, VATSetting
from app.models.patient import (
    Patient,
    PatientAddress,
    PatientEmail,
    PatientInsurance,
    PatientPhone,
    PatientSession,
)

# ── 1. KI INITIALISIERUNG (WHISPER) ──
try:
    from faster_whisper import WhisperModel

    app_logger.info("Lade Whisper-Modell...")
    whisper_model = WhisperModel("small", device="cpu", compute_type="default")
    app_logger.info("Whisper-Modell erfolgreich geladen!")
except ImportError:
    whisper_model = None
    app_logger.error("FEHLER: faster-whisper ist nicht installiert!")

# ── 2. KI INITIALISIERUNG (VOSK FÜR LIVE-STREAMING) ──
try:
    import vosk

    app_logger.info("Prüfe Vosk-Modell...")
    VOSK_DIR = "vosk-model-small-de-0.15"
    if not os.path.exists(VOSK_DIR):
        app_logger.info("Lade deutsches Vosk-Modell herunter (45 MB) - bitte kurz warten...")
        urllib.request.urlretrieve(
            "https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip",
            "vosk.zip",
        )
        with zipfile.ZipFile("vosk.zip", "r") as z:
            z.extractall(".")
        os.remove("vosk.zip")

    vosk.SetLogLevel(-1)
    vosk_model = vosk.Model(VOSK_DIR)
    app_logger.info("Vosk (Streaming) erfolgreich geladen!")
except Exception as e:
    vosk_model = None
    app_logger.error(f"Vosk Info: {e}. (Live-Streaming deaktiviert)")


def patient_detail_page(navigate) -> None:
    patient_id = nicegui_app.storage.user.get("current_patient_id")

    state = {
        "active_tab": "Personalien",
        "first_name": "",
        "last_name": "",
        "birthdate": "",
        "gender": "",
        "notes": "",
        "ins_active": None,
        "ins_history": [],
        "phones": [],
        "emails": [],
        "addresses": [],
        "sessions": [],
        "sess_id": None,
        "sess_date": "",
        "sess_time_from": "",
        "sess_time_to": "",
        "sess_issue": "",
        "sess_approach": "",
        "sess_protocol": "",
        "sess_payment_method_id": None,
        "sess_vat_id": None,
        "sess_is_paid": False,
        "sess_amount": 0.0,
        "billing_filter": "Alle",
        "recording_field": None,
        "recording_original_text": "",
    }

    mic_buttons = {}
    textareas = {}

    def load_data():
        if not patient_id:
            return
        with get_session() as session:
            p = session.query(Patient).filter_by(id=patient_id).first()
            if not p:
                return

            state["first_name"] = p.first_name or ""
            state["last_name"] = p.last_name or ""
            state["birthdate"] = p.birthdate.strftime("%Y-%m-%d") if p.birthdate else ""
            state["gender"] = p.gender or ""
            state["notes"] = p.notes or ""

            insurances = getattr(p, "insurances", [])
            act = next(
                (i for i in insurances if not getattr(i, "is_deleted", False)), None
            )
            state["ins_active"] = (
                {"id": act.id, "name": act.name, "number": act.insurance_number}
                if act
                else None
            )
            state["ins_history"] = [
                {"id": i.id, "name": i.name, "number": i.insurance_number}
                for i in insurances
                if getattr(i, "is_deleted", False)
            ]

            state["phones"] = [
                {
                    "id": ph.id,
                    "number": getattr(ph, "number", ""),
                    "type": getattr(ph, "type", "Privat"),
                    "is_main": getattr(ph, "is_main", False),
                }
                for ph in getattr(p, "phones", [])
                if not getattr(ph, "is_deleted", False)
            ]
            state["emails"] = [
                {
                    "id": e.id,
                    "email": getattr(e, "email", ""),
                    "type": getattr(e, "type", "Privat"),
                    "is_main": getattr(e, "is_main", False),
                }
                for e in getattr(p, "emails", [])
                if not getattr(e, "is_deleted", False)
            ]
            state["addresses"] = [
                {
                    "id": a.id,
                    "street": getattr(a, "street", ""),
                    "zip_code": getattr(a, "zip_code", ""),
                    "city": getattr(a, "city", ""),
                    "is_main": getattr(a, "is_main", False),
                }
                for a in getattr(p, "addresses", [])
                if not getattr(a, "is_deleted", False)
            ]

    try:
        load_data()
    except Exception as e:
        app_logger.error(f"Datenbankfehler: {e}", type="negative")
        ui.notify(f"Datenbankfehler: {e}", type="negative")

    # ── HYBRID-TRANSKRIBIERUNG (VOSK LIVE + WHISPER FINAL) ──
    async def toggle_recording(state_key):
        btn = mic_buttons.get(state_key)
        area = textareas.get(state_key)

        js_setup = """
        if (typeof window.startLiveRecord === 'undefined') {
            window.startLiveRecord = async function() {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({audio: true});

                    window.audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    await window.audioContext.resume(); 

                    const source = window.audioContext.createMediaStreamSource(stream);
                    window.processor = window.audioContext.createScriptProcessor(4096, 1, 1);
                    window.pcmChunks = [];

                    window.processor.onaudioprocess = function(e) {
                        const float32 = e.inputBuffer.getChannelData(0);
                        const int16 = new Int16Array(float32.length);
                        for (let i = 0; i < float32.length; i++) {
                            let s = Math.max(-1, Math.min(1, float32[i]));
                            int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                        }
                        window.pcmChunks.push(int16);
                    };

                    const gainNode = window.audioContext.createGain();
                    gainNode.gain.value = 0;
                    source.connect(window.processor);
                    window.processor.connect(gainNode);
                    gainNode.connect(window.audioContext.destination);

                    window.liveRecorder = new MediaRecorder(stream);
                    window.liveChunks = [];
                    window.liveRecorder.ondataavailable = e => {
                        if (e.data.size > 0) window.liveChunks.push(e.data);
                    };
                    window.liveRecorder.start();

                    window.audioStream = stream;

                    return "OK|" + window.audioContext.sampleRate;
                } catch (err) {
                    return "ERR_NO_MIC";
                }
            };

            window.getNewPcmData = async function() {
                if (!window.pcmChunks || window.pcmChunks.length === 0) return null;
                const chunks = window.pcmChunks;
                window.pcmChunks = []; 
                let total = chunks.reduce((acc, val) => acc + val.length, 0);
                let result = new Int16Array(total);
                let offset = 0;
                for (let chunk of chunks) {
                    result.set(chunk, offset);
                    offset += chunk.length;
                }

                const blob = new Blob([result.buffer], {type: 'application/octet-stream'});
                return new Promise(resolve => {
                    const reader = new FileReader();
                    reader.onloadend = () => {
                        resolve(reader.result.split(',')[1]); 
                    };
                    reader.readAsDataURL(blob);
                });
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
                if (window.processor) window.processor.disconnect();
                if (window.audioContext) window.audioContext.close();
                if (window.liveRecorder && window.liveRecorder.state !== 'inactive') window.liveRecorder.stop();
                if (window.audioStream) window.audioStream.getTracks().forEach(t => t.stop());
            };
        }
        """
        await ui.run_javascript(js_setup)

        if state["recording_field"] is None:
            if not vosk_model:
                app_logger.info("Live-Stream inaktiv, Whisper finalisiert am Ende.")
                ui.notify(
                    "Info: Live-Stream inaktiv, Whisper finalisiert am Ende.",
                    type="warning",
                )

            try:
                res = await ui.run_javascript(
                    "return await window.startLiveRecord();", timeout=60.0
                )
                if str(res).startswith("ERR_NO_MIC"):
                    return ui.notify("Mikrofon blockiert!", type="negative")
            except TimeoutError:
                return ui.notify("Zeitüberschreitung beim Mikrofon.", type="warning")

            mac_sample_rate = 16000
            if res and "|" in str(res):
                try:
                    mac_sample_rate = int(float(str(res).split("|")[1]))
                except:
                    pass

            state["recording_field"] = state_key
            state["recording_original_text"] = state[state_key] or ""

            if btn:
                btn.props("color=negative icon=stop")
                btn.update()

            ui.notify("Live-Aufnahme läuft...", type="info", timeout=3.0)

            async def live_transcription_loop():
                with get_session() as session:
                    settings = session.query(AppSetting).first()
                    interval = settings.streaming_interval if settings else 0.5

                whisper_model = SpeechManager.get_whisper()
                vosk_model = SpeechManager.get_vosk()

                spacer = "\n\n" if state["recording_original_text"] else ""
                live_draft = ""
                display_str = ""

                if vosk_model:
                    rec = vosk.KaldiRecognizer(vosk_model, mac_sample_rate)

                while state["recording_field"] == state_key:
                    await asyncio.sleep(0.25)
                    if state["recording_field"] != state_key:
                        break

                    if not vosk_model:
                        continue

                    with btn.client:
                        try:
                            b64_pcm = await ui.run_javascript(
                                "return await window.getNewPcmData();", timeout=5.0
                            )
                        except Exception as e:
                            app_logger.error(e)
                            continue

                        if b64_pcm:
                            try:
                                pcm_bytes = base64.b64decode(b64_pcm)

                                def run_vosk(b):
                                    if rec.AcceptWaveform(b):
                                        return True, json.loads(rec.Result()).get(
                                            "text", ""
                                        )
                                    else:
                                        return False, json.loads(
                                            rec.PartialResult()
                                        ).get("partial", "")

                                is_final, text_res = await asyncio.to_thread(
                                    run_vosk, pcm_bytes
                                )

                                if is_final and text_res:
                                    live_draft += (" " if live_draft else "") + text_res
                                    display_str = live_draft
                                elif not is_final:
                                    display_str = (
                                        live_draft
                                        + (" " if live_draft and text_res else "")
                                        + text_res
                                    )
                                else:
                                    display_str = live_draft

                            except Exception:
                                pass

                        dots = "." * (int(datetime.now().timestamp() * 2) % 4)
                        try:
                            new_text = f"{state['recording_original_text']}{spacer}≈ {display_str} {dots}".strip()
                            state[state_key] = new_text
                            if area:
                                area.value = new_text
                        except Exception:
                            break

            asyncio.create_task(live_transcription_loop())

        elif state["recording_field"] == state_key:
            state["recording_field"] = None

            if btn:
                btn.props("color=warning icon=hourglass_empty")
                btn.update()

            ui.notify(
                "Erstelle finale Whisper-Abschrift...", type="ongoing", timeout=5.0
            )

            try:
                await ui.run_javascript("window.stopLiveRecord();")
                await asyncio.sleep(0.5)

                b64 = await ui.run_javascript(
                    "return await window.getLiveAudio();", timeout=10.0
                )

                if b64 and b64.startswith("data:audio") and whisper_model:
                    header, encoded = b64.split(",", 1)
                    audio_data = base64.b64decode(encoded)

                    sys_tmp = tempfile.gettempdir()
                    tmp_path = os.path.join(
                        sys_tmp, f"final_audio_{datetime.now().timestamp()}.webm"
                    )

                    try:
                        with open(tmp_path, "wb") as f:
                            f.write(audio_data)

                        segments, _ = await asyncio.to_thread(
                            whisper_model.transcribe, tmp_path, language="de"
                        )
                        whisper_text = " ".join([s.text for s in segments]).strip()
                        spacer = "\n\n" if state["recording_original_text"] else ""

                        if whisper_text:
                            final_text = f"{state['recording_original_text']}{spacer}{whisper_text}".strip()
                            state[state_key] = final_text
                            if area:
                                area.value = final_text

                    except Exception as e:
                        app_logger.error(f"Whisper Fehler: {e}")
                        print(f"Whisper Fehler: {e}")
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
            except Exception as e:
                app_logger.error(f"Whisper Fehler: {e}")
                print(f"JavaScript Fehler: {e}")
            finally:
                if btn:
                    try:
                        btn.props("color=grey icon=mic")
                        btn.update()
                    except Exception:
                        pass
                ui.notify(
                    "Aufnahme erfolgreich gespeichert!", type="positive", timeout=3.0
                )

        else:
            ui.notify(
                "Bitte beende zuerst die andere laufende Aufnahme!", type="warning"
            )

    # ── 2. GLOBALE DIALOGE (Versicherung, Kontakte...) ──
    ins_state = {"id": None}
    ins_dlg = ui.dialog()
    with ins_dlg, ui.card().classes("p-6 min-w-[400px]"):
        ui.label("Krankenkasse").classes("text-lg font-bold mb-4")
        ins_name_in = ui.input("Name").classes("w-full mb-2").props("outlined dense")
        ins_num_in = (
            ui.input("Versichertennummer")
            .classes("w-full mb-4")
            .props("outlined dense")
        )

        def save_ins():
            with get_session() as session:
                if ins_state["id"]:
                    ins = (
                        session.query(PatientInsurance)
                        .filter_by(id=ins_state["id"])
                        .first()
                    )
                    if ins:
                        ins.name, ins.insurance_number = (
                            ins_name_in.value,
                            ins_num_in.value,
                        )
                else:
                    p = session.query(Patient).filter_by(id=patient_id).first()
                    for ins in getattr(p, "insurances", []):
                        ins.is_deleted = True
                    session.add(
                        PatientInsurance(
                            patient_id=patient_id,
                            name=ins_name_in.value,
                            insurance_number=ins_num_in.value,
                            is_deleted=False,
                        )
                    )
                session.commit()
            ins_dlg.close()
            load_data()
            main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=ins_dlg.close).props(
                'flat text-color="grey"'
            )
            ui.button("Speichern", on_click=save_ins).props(
                'unelevated color="primary"'
            )

    def open_ins(item=None):
        ins_state["id"] = item["id"] if item else None
        ins_name_in.value = item["name"] if item else ""
        ins_num_in.value = item["number"] if item else ""
        ins_dlg.open()

    phone_state = {"id": None}
    phone_dlg = ui.dialog()
    with phone_dlg, ui.card().classes("p-6 min-w-[400px]"):
        ui.label("Telefonnummer").classes("text-lg font-bold mb-4")
        phone_num_in = ui.input("Nummer").classes("w-full mb-2").props("outlined dense")
        phone_type_in = (
            ui.select(["Privat", "Geschäftlich", "Mobil", "Andere"], label="Typ")
            .classes("w-full mb-2")
            .props("outlined dense")
        )
        phone_main_in = ui.checkbox("Als Hauptnummer festlegen").classes("mb-4")

        def save_phone():
            with get_session() as session:
                p = session.query(Patient).filter_by(id=patient_id).first()
                if phone_main_in.value:
                    for ph in getattr(p, "phones", []):
                        ph.is_main = False
                if phone_state["id"]:
                    ph = (
                        session.query(PatientPhone)
                        .filter_by(id=phone_state["id"])
                        .first()
                    )
                    ph.number, ph.type, ph.is_main = (
                        phone_num_in.value,
                        phone_type_in.value,
                        phone_main_in.value,
                    )
                else:
                    session.add(
                        PatientPhone(
                            patient_id=patient_id,
                            number=phone_num_in.value,
                            type=phone_type_in.value,
                            is_main=phone_main_in.value,
                        )
                    )
                session.commit()
            phone_dlg.close()
            load_data()
            main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=phone_dlg.close).props(
                'flat text-color="grey"'
            )
            ui.button("Speichern", on_click=save_phone).props(
                'unelevated color="primary"'
            )

    def open_phone(item=None):
        phone_state["id"] = item["id"] if item else None
        phone_num_in.value = item["number"] if item else ""
        phone_type_in.value = item["type"] if item else "Privat"
        phone_main_in.value = item["is_main"] if item else False
        phone_dlg.open()

    email_state = {"id": None}
    email_dlg = ui.dialog()
    with email_dlg, ui.card().classes("p-6 min-w-[400px]"):
        ui.label("E-Mail Adresse").classes("text-lg font-bold mb-4")
        email_val_in = (
            ui.input("E-Mail")
            .classes("w-full mb-2")
            .props('outlined dense type="email"')
        )
        email_type_in = (
            ui.select(["Privat", "Geschäftlich", "Andere"], label="Typ")
            .classes("w-full mb-2")
            .props("outlined dense")
        )
        email_main_in = ui.checkbox("Als Hauptadresse festlegen").classes("mb-4")

        def save_email():
            with get_session() as session:
                p = session.query(Patient).filter_by(id=patient_id).first()
                if email_main_in.value:
                    for em in getattr(p, "emails", []):
                        em.is_main = False
                if email_state["id"]:
                    em = (
                        session.query(PatientEmail)
                        .filter_by(id=email_state["id"])
                        .first()
                    )
                    em.email, em.type, em.is_main = (
                        email_val_in.value,
                        email_type_in.value,
                        email_main_in.value,
                    )
                else:
                    session.add(
                        PatientEmail(
                            patient_id=patient_id,
                            email=email_val_in.value,
                            type=email_type_in.value,
                            is_main=email_main_in.value,
                        )
                    )
                session.commit()
            email_dlg.close()
            load_data()
            main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=email_dlg.close).props(
                'flat text-color="grey"'
            )
            ui.button("Speichern", on_click=save_email).props(
                'unelevated color="primary"'
            )

    def open_email(item=None):
        email_state["id"] = item["id"] if item else None
        email_val_in.value = item["email"] if item else ""
        email_type_in.value = item["type"] if item else "Privat"
        email_main_in.value = item["is_main"] if item else False
        email_dlg.open()

    addr_state = {"id": None}
    addr_dlg = ui.dialog()
    with addr_dlg, ui.card().classes("p-6 min-w-[500px]"):
        ui.label("Postadresse").classes("text-lg font-bold mb-4")
        addr_st_in = (
            ui.input("Straße & Hausnummer")
            .classes("w-full mb-2")
            .props("outlined dense")
        )
        with ui.row().classes("w-full gap-2 mb-2"):
            addr_zip_in = ui.input("PLZ").classes("w-[100px]").props("outlined dense")
            addr_city_in = ui.input("Ort").classes("flex-1").props("outlined dense")
        addr_main_in = ui.checkbox("Als Hauptwohnsitz festlegen").classes("mb-4")

        def save_address():
            with get_session() as session:
                p = session.query(Patient).filter_by(id=patient_id).first()
                if addr_main_in.value:
                    for a in getattr(p, "addresses", []):
                        a.is_main = False
                if addr_state["id"]:
                    a = (
                        session.query(PatientAddress)
                        .filter_by(id=addr_state["id"])
                        .first()
                    )
                    a.street, a.zip_code, a.city, a.is_main = (
                        addr_st_in.value,
                        addr_zip_in.value,
                        addr_city_in.value,
                        addr_main_in.value,
                    )
                else:
                    session.add(
                        PatientAddress(
                            patient_id=patient_id,
                            street=addr_st_in.value,
                            zip_code=addr_zip_in.value,
                            city=addr_city_in.value,
                            is_main=addr_main_in.value,
                        )
                    )
                session.commit()
            addr_dlg.close()
            load_data()
            main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=addr_dlg.close).props(
                'flat text-color="grey"'
            )
            ui.button("Speichern", on_click=save_address).props(
                'unelevated color="primary"'
            )

    def open_addr(item=None):
        addr_state["id"] = item["id"] if item else None
        addr_st_in.value = item["street"] if item else ""
        addr_zip_in.value = item["zip_code"] if item else ""
        addr_city_in.value = item["city"] if item else ""
        addr_main_in.value = item["is_main"] if item else False
        addr_dlg.open()

    sess_dlg = ui.dialog()
    with sess_dlg, ui.card().classes("p-6 min-w-[1100px] max-w-[1300px]"):
        with ui.row().classes("w-full justify-between items-center mb-4"):
            ui.label("Sitzungsdetails").classes("text-lg font-bold")
            ui.button(icon="close", on_click=sess_dlg.close).props("flat round dense")

        with ui.row().classes("w-full gap-4 mb-4"):
            ui.input("Datum").bind_value(state, "sess_date").classes("flex-1").props(
                'outlined dense type="date"'
            )
            ui.input("Von").bind_value(state, "sess_time_from").classes(
                "w-[100px]"
            ).props('outlined dense type="time"')
            ui.input("Bis").bind_value(state, "sess_time_to").classes(
                "w-[100px]"
            ).props('outlined dense type="time"')

        def voice_area(label, state_key):
            with ui.row().classes("w-full items-start gap-2 mb-4"):
                t_area = (
                    ui.textarea(label)
                    .bind_value(state, state_key)
                    .classes("flex-1")
                    .props('outlined rows="10"')
                )
                textareas[state_key] = t_area

                btn = (
                    ui.button(icon="mic", on_click=lambda: toggle_recording(state_key))
                    .props('flat round color="grey"')
                    .tooltip("Push-to-Talk")
                )
                mic_buttons[state_key] = btn

        voice_area("Anliegen / Thema", "sess_issue")
        voice_area("Lösungsansatz / Intervention", "sess_approach")
        voice_area("Protokoll / Notizen", "sess_protocol")

        ui.separator().classes("my-4")

        with ui.row().classes("w-full gap-4 mb-4 items-center"):
            pm_select = (
                ui.select({}, label="Bezahlmethode")
                .bind_value(state, "sess_payment_method_id")
                .classes("flex-1")
                .props("outlined dense")
            )
            vat_select = (
                ui.select({}, label="MwSt-Satz")
                .bind_value(state, "sess_vat_id")
                .classes("w-[180px]")
                .props("outlined dense")
            )

            ui.input("Betrag (Netto in CHF)").bind_value(state, "sess_amount").classes(
                "w-[180px]"
            ).props('outlined dense type="number" step="0.05"')
            ui.checkbox("Bezahlt").bind_value(state, "sess_is_paid")

        def save_session():
            if not state["sess_date"]:
                return ui.notify("Datum ist Pflichtfeld", type="warning")
            with get_session() as session:
                if state["sess_id"]:
                    s = (
                        session.query(PatientSession)
                        .filter_by(id=state["sess_id"])
                        .first()
                    )
                else:
                    s = PatientSession(patient_id=patient_id)
                    s.user_id = nicegui_app.storage.user.get("user_id")
                    session.add(s)

                s.date = datetime.strptime(state["sess_date"], "%Y-%m-%d").date()
                s.time_from = state["sess_time_from"]
                s.time_to = state["sess_time_to"]
                s.issue = state["sess_issue"]
                s.approach = state["sess_approach"]
                s.protocol = state["sess_protocol"]

                s.payment_method_id = state["sess_payment_method_id"]
                s.vat_id = state["sess_vat_id"]
                s.is_paid = state["sess_is_paid"]

                try:
                    s.amount = float(state["sess_amount"])
                except:
                    s.amount = 0.0

                session.commit()
            sess_dlg.close()
            load_data()
            main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Speichern", on_click=save_session).props(
                'unelevated color="primary"'
            )

    def open_session(s=None):
        with get_session() as db:
            active_pms = db.query(PaymentMethod).filter_by(is_active=True).all()
            pm_options = {pm.id: pm.title for pm in active_pms}

            today = date.today()
            active_vats = db.query(VATSetting).filter_by(is_active=True).all()
            vat_options = {}
            for v in active_vats:
                if not v.end_date or v.end_date >= today:
                    vat_options[v.id] = f"{v.description} ({v.rate}%)"

            if s:
                if s.payment_method_id and s.payment_method_id not in pm_options:
                    pm_options[s.payment_method_id] = (
                        f"Archiviert (ID {s.payment_method_id})"
                    )
                if s.vat_id and s.vat_id not in vat_options:
                    vat_options[s.vat_id] = f"Archiviert (ID {s.vat_id})"

            pm_select.options = pm_options
            vat_select.options = vat_options
            pm_select.update()
            vat_select.update()

        state.update(
            {
                "sess_id": getattr(s, "id", None) if s else None,
                "sess_date": (
                    s.date.strftime("%Y-%m-%d")
                    if s and getattr(s, "date", None)
                    else datetime.now().strftime("%Y-%m-%d")
                ),
                "sess_time_from": getattr(s, "time_from", ""),
                "sess_time_to": getattr(s, "time_to", ""),
                "sess_issue": getattr(s, "issue", ""),
                "sess_approach": getattr(s, "approach", ""),
                "sess_protocol": getattr(s, "protocol", ""),
                "sess_payment_method_id": getattr(s, "payment_method_id", None),
                "sess_vat_id": getattr(s, "vat_id", None),
                "sess_is_paid": getattr(s, "is_paid", False),
                "sess_amount": getattr(s, "amount", 0.0),
            }
        )
        sess_dlg.open()

    def hard_delete(model_class, item_id):
        with get_session() as session:
            item = session.query(model_class).filter_by(id=item_id).first()
            if item:
                session.delete(item)
                session.commit()
        load_data()
        main_content.refresh()

    def soft_delete(model_class, item_id):
        with get_session() as session:
            item = session.query(model_class).filter_by(id=item_id).first()
            if item:
                item.is_deleted = True
                session.commit()
        load_data()
        main_content.refresh()

    def save_basic():
        with get_session() as session:
            p = (
                session.query(Patient).filter_by(id=patient_id).first()
                if patient_id
                else Patient()
            )
            if not patient_id:
                session.add(p)

            p.first_name, p.last_name = state["first_name"], state["last_name"]
            p.gender, p.notes = state["gender"], state["notes"]

            if state["birthdate"]:
                try:
                    p.birthdate = datetime.strptime(
                        state["birthdate"], "%Y-%m-%d"
                    ).date()
                except ValueError:
                    return ui.notify("Format YYYY-MM-DD nutzen.", type="negative")
            else:
                p.birthdate = None

            session.commit()
            if not patient_id:
                nicegui_app.storage.user["current_patient_id"] = p.id
                navigate("/patient_detail")
                return
            ui.notify("Stammdaten gespeichert", type="positive")

    with ui.row().classes("items-center w-full mb-6 gap-4"):
        ui.button(icon="arrow_back", on_click=lambda: navigate("/patients")).props(
            "flat round"
        ).classes("text-gray-600 hover:bg-gray-100")
        ui.label("Patientenakte" if patient_id else "Neuer Patient").classes(
            "text-[24px] font-semibold text-[#1e3a5f]"
        )
        ui.space()
        ui.button("Speichern", icon="save", on_click=save_basic).props(
            "unelevated"
        ).classes("bg-[#0078d4] text-white")

    with ui.splitter(value=15).classes("w-full") as splitter:
        with splitter.before:

            def set_tab(t):
                state["active_tab"] = t
                menu_col.refresh()
                main_content.refresh()

            def get_btn_class(t):
                base = "w-full px-4 py-3 text-[14px] rounded-none transition-colors border-r-4 "
                return base + (
                    "bg-blue-50 text-blue-700 border-blue-500"
                    if state["active_tab"] == t
                    else "text-slate-600 hover:bg-slate-50 border-transparent"
                )

            @ui.refreshable
            def menu_col():
                with ui.column().classes("w-full gap-0 mt-2"):
                    btn_props = 'flat align="left" no-caps'
                    ui.button(
                        "Personalien",
                        icon="badge",
                        on_click=lambda: set_tab("Personalien"),
                    ).classes(get_btn_class("Personalien")).props(btn_props)
                    btn_contacts = (
                        ui.button(
                            "Kontaktangaben",
                            icon="contact_mail",
                            on_click=lambda: set_tab("Kontaktangaben"),
                        )
                        .classes(get_btn_class("Kontaktangaben"))
                        .props(btn_props)
                    )
                    btn_sessions = (
                        ui.button(
                            "Sitzungen",
                            icon="event",
                            on_click=lambda: set_tab("Sitzungen"),
                        )
                        .classes(get_btn_class("Sitzungen"))
                        .props(btn_props)
                    )
                    btn_payments = (
                        ui.button(
                            "Abrechnungen",
                            icon="receipt",
                            on_click=lambda: set_tab("Abrechnungen"),
                        )
                        .classes(get_btn_class("Abrechnungen"))
                        .props(btn_props)
                    )
                    btn_files = (
                        ui.button(
                            "Dateien",
                            icon="attach_file",
                            on_click=lambda: set_tab("Dateien"),
                        )
                        .classes(get_btn_class("Dateien"))
                        .props(btn_props)
                    )
                    if not patient_id:
                        btn_contacts.disable()
                        btn_sessions.disable()
                        btn_payments.disable()
                        btn_files.disable()

            menu_col()

        with splitter.after:

            @ui.refreshable
            def main_content():
                with ui.column().classes("w-full pl-6"):

                    if state["active_tab"] == "Personalien":
                        with ui.card().classes("w-full max-w-3xl p-6 shadow-sm mb-6"):
                            ui.label("Stammdaten").classes(
                                "text-[18px] font-medium mb-4 text-[#1e3a5f]"
                            )
                            with ui.row().classes("w-full gap-4 mb-4"):
                                ui.input("Vorname").bind_value(
                                    state, "first_name"
                                ).classes("flex-1").props("outlined dense")
                                ui.input("Nachname").bind_value(
                                    state, "last_name"
                                ).classes("flex-1").props("outlined dense")
                            with ui.row().classes("w-full gap-4 mb-4"):
                                ui.input("Geburtsdatum (YYYY-MM-DD)").bind_value(
                                    state, "birthdate"
                                ).classes("flex-1").props('outlined dense type="date"')
                                ui.select(
                                    ["Männlich", "Weiblich", "Divers", "Keine Angabe"],
                                    label="Geschlecht",
                                ).bind_value(state, "gender").classes("flex-1").props(
                                    "outlined dense"
                                )
                            ui.textarea("Bemerkungen").bind_value(
                                state, "notes"
                            ).classes("w-full").props('outlined rows="4"')

                        if patient_id:
                            with ui.card().classes(
                                "w-full max-w-3xl p-6 shadow-sm border-l-4 border-[#0078d4]"
                            ):
                                with ui.row().classes(
                                    "w-full items-center justify-between mb-4"
                                ):
                                    ui.label("Krankenversicherung").classes(
                                        "text-[18px] font-medium text-[#1e3a5f]"
                                    )
                                    ui.button(
                                        "Neu", icon="add", on_click=lambda: open_ins()
                                    ).props("outline dense").classes("text-[#0078d4]")

                                act = state["ins_active"]
                                if act:
                                    with ui.row().classes(
                                        "w-full items-center justify-between bg-blue-50 p-3 rounded mb-4"
                                    ):
                                        with ui.column().classes("gap-0"):
                                            ui.label(act["name"]).classes(
                                                "font-semibold text-slate-800"
                                            )
                                            ui.label(
                                                f"Versicherten-Nr: {act['number']}"
                                            ).classes("text-sm text-slate-500")
                                        with ui.row().classes("gap-1"):
                                            ui.button(
                                                icon="edit",
                                                on_click=lambda: open_ins(act),
                                            ).props('flat round dense color="primary"')
                                            ui.button(
                                                icon="delete",
                                                on_click=lambda: hard_delete(
                                                    PatientInsurance, act["id"]
                                                ),
                                            ).props('flat round dense color="negative"')
                                else:
                                    ui.label(
                                        "Keine aktive Versicherung hinterlegt."
                                    ).classes("text-slate-500 italic mb-4")

                                if state["ins_history"]:
                                    with ui.expansion(
                                        "Versicherungs-Historie anzeigen"
                                    ).classes(
                                        "w-full shadow-none border border-slate-200"
                                    ):
                                        for old in state["ins_history"]:
                                            with ui.row().classes(
                                                "w-full items-center justify-between p-2 border-b border-slate-100 last:border-0"
                                            ):
                                                with ui.column().classes("gap-0"):
                                                    ui.label(old["name"]).classes(
                                                        "text-sm text-gray-500 line-through"
                                                    )
                                                    ui.label(
                                                        f"Nr: {old['number']}"
                                                    ).classes("text-xs text-gray-400")
                                                with ui.row().classes("gap-1"):
                                                    ui.button(
                                                        icon="edit",
                                                        on_click=lambda o=old: open_ins(
                                                            o
                                                        ),
                                                    ).props(
                                                        'flat round dense color="primary" size="sm"'
                                                    )
                                                    ui.button(
                                                        icon="delete",
                                                        on_click=lambda o=old: hard_delete(
                                                            PatientInsurance, o["id"]
                                                        ),
                                                    ).props(
                                                        'flat round dense color="negative" size="sm"'
                                                    )

                    elif state["active_tab"] == "Kontaktangaben":

                        def draw_list(
                            title, items, open_fn, model_cls, format_main, format_sub
                        ):
                            with ui.card().classes(
                                "w-full max-w-3xl p-6 shadow-sm mb-6"
                            ):
                                with ui.row().classes(
                                    "w-full items-center justify-between mb-4"
                                ):
                                    ui.label(title).classes(
                                        "text-[18px] font-medium text-[#1e3a5f]"
                                    )
                                    ui.button(
                                        "Neu", icon="add", on_click=lambda: open_fn()
                                    ).props("outline dense").classes("text-[#0078d4]")

                                if not items:
                                    ui.label("Noch keine Einträge vorhanden.").classes(
                                        "text-slate-400 italic"
                                    )

                                for item in sorted(
                                    items, key=lambda x: not x["is_main"]
                                ):
                                    with ui.row().classes(
                                        "w-full items-center justify-between p-2 border-b border-slate-100 last:border-0"
                                    ):
                                        with ui.row().classes("items-center gap-3"):
                                            ui.icon(
                                                "star",
                                                color=(
                                                    "amber"
                                                    if item["is_main"]
                                                    else "transparent"
                                                ),
                                            ).classes("text-lg")
                                            with ui.column().classes("gap-0"):
                                                ui.label(format_main(item)).classes(
                                                    "font-medium"
                                                )
                                                ui.label(format_sub(item)).classes(
                                                    "text-xs text-slate-500"
                                                )
                                        with ui.row().classes("gap-1"):
                                            ui.button(
                                                icon="edit",
                                                on_click=lambda i=item: open_fn(i),
                                            ).props(
                                                'flat round dense color="primary" size="sm"'
                                            )
                                            ui.button(
                                                icon="delete",
                                                on_click=lambda i=item, m=model_cls: soft_delete(
                                                    m, i["id"]
                                                ),
                                            ).props(
                                                'flat round dense color="negative" size="sm"'
                                            )

                        draw_list(
                            "Telefonnummern",
                            state["phones"],
                            open_phone,
                            PatientPhone,
                            lambda i: i["number"],
                            lambda i: i["type"],
                        )
                        draw_list(
                            "E-Mail Adressen",
                            state["emails"],
                            open_email,
                            PatientEmail,
                            lambda i: i["email"],
                            lambda i: i["type"],
                        )
                        draw_list(
                            "Postadressen",
                            state["addresses"],
                            open_addr,
                            PatientAddress,
                            lambda i: i["street"],
                            lambda i: f"{i['zip_code']} {i['city']}",
                        )

                    elif state["active_tab"] == "Sitzungen":
                        with get_session() as session:
                            sitzungen = (
                                session.query(PatientSession)
                                .options(
                                    joinedload(PatientSession.payment_method),
                                    joinedload(PatientSession.vat_setting),
                                )
                                .filter_by(patient_id=patient_id, is_deleted=False)
                                .all()
                            )

                            sitzungen.sort(key=lambda x: x.date, reverse=True)

                        with ui.row().classes(
                            "w-full max-w-4xl justify-between items-center mb-6"
                        ):
                            ui.label("Sitzungshistorie").classes(
                                "text-[20px] font-medium text-[#1e3a5f]"
                            )
                            ui.button(
                                "Neue Sitzung",
                                icon="add",
                                on_click=lambda: open_session(),
                            ).props("unelevated").classes("bg-[#0078d4] text-white")

                        if not sitzungen:
                            ui.label("Noch keine Sitzungen erfasst.").classes(
                                "text-slate-400 italic"
                            )

                        for s in sitzungen:
                            date_str = s.date.strftime("%d.%m.%Y")
                            time_str = (
                                f" | {s.time_from} - {s.time_to} Uhr"
                                if (s.time_from and s.time_to)
                                else ""
                            )
                            paid_str = "Bezahlt" if s.is_paid else "Offen"

                            vat_rate = s.vat_setting.rate if s.vat_setting else 0.0
                            gross_amount = s.amount * (1 + vat_rate / 100)

                            header_text = f"{date_str}{time_str} | CHF {gross_amount:.2f} ({paid_str})"

                            with ui.expansion(header_text, icon="event").classes(
                                "w-full max-w-4xl shadow-sm border border-slate-200 mb-0 mt-0 bg-white rounded"
                            ):
                                with ui.column().classes("w-full p-4 gap-4"):
                                    if s.issue:
                                        with ui.column().classes("gap-1"):
                                            ui.label("Anliegen").classes(
                                                "font-bold text-slate-700 text-sm"
                                            )
                                            ui.label(s.issue).classes(
                                                "text-slate-600 whitespace-pre-line"
                                            )
                                    if s.approach:
                                        with ui.column().classes("gap-1"):
                                            ui.label("Lösungsansatz").classes(
                                                "font-bold text-slate-700 text-sm"
                                            )
                                            ui.label(s.approach).classes(
                                                "text-slate-600 whitespace-pre-line"
                                            )
                                    if s.protocol:
                                        with ui.column().classes("gap-1"):
                                            ui.label("Protokoll").classes(
                                                "font-bold text-slate-700 text-sm"
                                            )
                                            ui.label(s.protocol).classes(
                                                "text-slate-600 whitespace-pre-line"
                                            )

                                    ui.separator()
                                    with ui.row().classes(
                                        "w-full justify-between items-center"
                                    ):
                                        pm_title = (
                                            s.payment_method.title
                                            if s.payment_method
                                            else "Nicht definiert"
                                        )
                                        vat_desc = (
                                            f"{s.vat_setting.rate}% MwSt"
                                            if s.vat_setting
                                            else "Keine MwSt"
                                        )
                                        ui.label(
                                            f"Abrechnung: {pm_title} | {vat_desc}"
                                        ).classes("text-xs text-slate-500 font-medium")

                                        with ui.row().classes("gap-2"):
                                            ui.button(
                                                "Löschen",
                                                on_click=lambda idx=s.id: soft_delete(
                                                    PatientSession, idx
                                                ),
                                            ).props('flat color="negative" size="sm"')
                                            ui.button(
                                                "Bearbeiten",
                                                on_click=lambda item=s: open_session(
                                                    item
                                                ),
                                            ).props('outline color="primary" size="sm"')

                    elif state["active_tab"] == "Abrechnungen":

                        # ── DATENABRUF FÜR ABRECHNUNGEN ──

                        with get_session() as session:

                            sitzungen = (
                                session.query(PatientSession)
                                .options(
                                    joinedload(PatientSession.payment_method),
                                    joinedload(PatientSession.vat_setting),
                                )
                                .filter_by(patient_id=patient_id, is_deleted=False)
                                .order_by(PatientSession.date.desc())
                                .all()
                            )

                            billing_rows = []

                            for s in sitzungen:

                                if state["billing_filter"] == "Offen" and s.is_paid:
                                    continue

                                if (
                                    state["billing_filter"] == "Bezahlt"
                                    and not s.is_paid
                                ):
                                    continue

                                pm_title = (
                                    s.payment_method.title
                                    if s.payment_method
                                    else "Nicht definiert"
                                )

                                vat_rate = s.vat_setting.rate if s.vat_setting else 0.0

                                vat_desc = f"{vat_rate}%"

                                amount_incl_vat = s.amount * (1 + (vat_rate / 100))

                                billing_rows.append(
                                    {
                                        "id": s.id,
                                        "date": s.date.strftime("%d.%m.%Y"),
                                        "amount_net": s.amount,
                                        "amount_gross": amount_incl_vat,
                                        "amount_str": f"CHF {amount_incl_vat:.2f}",
                                        "vat": vat_desc,
                                        "status": "Bezahlt" if s.is_paid else "Offen",
                                        "is_paid": s.is_paid,
                                        "payment_method": (
                                            pm_title if s.is_paid else "-"
                                        ),
                                    }
                                )

                        with ui.column().classes("w-full max-w-4xl gap-6"):

                            with ui.row().classes(
                                "w-full justify-between items-center mb-2 gap-4"
                            ):

                                ui.label("Abrechnungen & Belege").classes(
                                    "text-[20px] font-medium text-[#1e3a5f] flex-1"
                                )

                                # ── Filter-Buttons ──

                                with ui.row().classes("gap-2 items-center"):

                                    def set_filter(f):
                                        state["billing_filter"] = f

                                        main_content.refresh()

                                    ui.button(
                                        "Alle", on_click=lambda: set_filter("Alle")
                                    ).props(
                                        'unelevated color="primary"'
                                        if state["billing_filter"] == "Alle"
                                        else 'outline color="grey"'
                                    )

                                    ui.button(
                                        "Offen", on_click=lambda: set_filter("Offen")
                                    ).props(
                                        'unelevated color="negative"'
                                        if state["billing_filter"] == "Offen"
                                        else 'outline color="grey"'
                                    )

                                    ui.button(
                                        "Bezahlt",
                                        on_click=lambda: set_filter("Bezahlt"),
                                    ).props(
                                        'unelevated color="positive"'
                                        if state["billing_filter"] == "Bezahlt"
                                        else 'outline color="grey"'
                                    )

                                def print_summary():

                                    ui.notify("Zusammenzug Logik folgt...", type="info")

                                def handle_invoice_success():
                                    """Wird ausgeführt, wenn die Rechnung erfolgreich gedruckt wurde."""
                                    billing_table.selected.clear()
                                    billing_table.update()

                                def print_invoice():
                                    # Sicherheitscheck: Gibt es überhaupt Daten/eine Tabelle?
                                    if not billing_rows:
                                        ui.notify(
                                            "Es gibt keine Sitzungen, die abgerechnet werden können.",
                                            type="warning",
                                        )
                                        return

                                    selected_rows = billing_table.selected
                                    unpaid_selected = [
                                        r for r in selected_rows if not r["is_paid"]
                                    ]

                                    if not unpaid_selected:
                                        ui.notify(
                                            "Bitte markieren Sie mindestens eine offene Sitzung in der Tabelle.",
                                            type="warning",
                                        )
                                        return

                                    session_ids = [r["id"] for r in unpaid_selected]

                                    # Aufruf des neuen, zentralen Dialogs
                                    open_document_dialog(
                                        doc_type="Rechnung",
                                        patient_id=patient_id,
                                        session_ids=session_ids,
                                        on_success=handle_invoice_success,
                                    )

                                    ui.button(
                                        "Zusammenzug",
                                        icon="summarize",
                                        on_click=print_summary,
                                    ).props("outline").classes("text-[#0078d4]")

                                ui.button(
                                    "Rechnung erstellen",
                                    icon="receipt_long",
                                    on_click=print_invoice,
                                ).props("unelevated").classes("bg-[#0078d4] text-white")

                            if not billing_rows:

                                ui.label(
                                    "Es wurden keine Sitzungen für den gewählten Filter gefunden."
                                ).classes("text-slate-400 italic")

                            else:

                                billing_columns = [
                                    {
                                        "name": "date",
                                        "label": "Datum",
                                        "field": "date",
                                        "align": "left",
                                        "sortable": True,
                                    },
                                    {
                                        "name": "amount_str",
                                        "label": "Betrag (inkl. MwSt)",
                                        "field": "amount_str",
                                        "align": "right",
                                    },
                                    {
                                        "name": "vat",
                                        "label": "MwSt",
                                        "field": "vat",
                                        "align": "right",
                                    },
                                    {
                                        "name": "status",
                                        "label": "Status",
                                        "field": "status",
                                        "align": "center",
                                    },
                                    {
                                        "name": "payment_method",
                                        "label": "Bezahlmethode",
                                        "field": "payment_method",
                                        "align": "left",
                                    },
                                    {
                                        "name": "actions",
                                        "label": "Aktionen",
                                        "field": "id",
                                        "align": "right",
                                    },
                                ]

                                billing_table = ui.table(
                                    columns=billing_columns,
                                    rows=billing_rows,
                                    row_key="id",
                                    selection="multiple",
                                ).classes(
                                    "w-full shadow-sm border border-slate-200 bg-white"
                                )

                                billing_table.add_slot(
                                    "body-cell-actions",
                                    r"""
                                                        <q-td :props="props">
                                                            <div class="row items-center justify-end no-wrap gap-1">
                                                                <q-btn v-if="props.row.is_paid" flat round dense icon="print" color="primary" @click="$parent.$emit('print_receipt', props.row)">
                                                                    <q-tooltip>Quittung drucken</q-tooltip>
                                                                </q-btn>
                                                                <q-btn v-if="!props.row.is_paid" flat round dense icon="check_circle" color="positive" @click="$parent.$emit('mark_paid', props.row.id)">
                                                                    <q-tooltip>Als bezahlt markieren</q-tooltip>
                                                                </q-btn>
                                                            </div>
                                                        </q-td>
                                                    """,
                                )

                                billing_table.add_slot(
                                    "body-selection",
                                    r"""
                                                        <q-td :auto-width="true">
                                                            <q-checkbox :class="{ 'invisible': props.row.is_paid }" v-model="props.selected" color="primary" />
                                                        </q-td>
                                                    """,
                                )

                                def print_receipt(msg):
                                    row = msg.args

                                    # Aufruf des neuen, zentralen Dialogs
                                    open_document_dialog(
                                        doc_type="Quittung",
                                        patient_id=patient_id,
                                        session_ids=[row["id"]],
                                    )

                                def mark_as_paid(msg):

                                    sess_id = msg.args

                                    with get_session() as session:
                                        s = (
                                            session.query(PatientSession)
                                            .filter_by(id=sess_id)
                                            .first()
                                        )

                                        if s:
                                            s.is_paid = True

                                            session.commit()

                                    ui.notify(
                                        "Sitzung als bezahlt markiert.", type="positive"
                                    )

                                    main_content.refresh()

                                billing_table.on("print_receipt", print_receipt)
                                billing_table.on("mark_paid", mark_as_paid)
                                billing_table.add_slot(
                                    "body-row",
                                    r"""
                                                        <q-tr :props="props" :class="props.row.is_paid ? 'bg-slate-50 text-slate-500' : ''">
                                                            <q-td v-for="col in props.cols" :key="col.name" :props="props">
                                                                {{ col.value }}
                                                            </q-td>
                                                        </q-tr>
                                                    """,
                                )

                    elif state["active_tab"] == "Dateien":
                        ui.label("Dateien kommen hier hin...").classes(
                            "text-lg text-slate-500"
                        )

            main_content()
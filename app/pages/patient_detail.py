# app/pages/patient_detail.py
import asyncio
import base64
import json
import os
import tempfile
import urllib.request
import zipfile
from datetime import date, datetime

from nicegui import app as nicegui_app
from nicegui import ui
from sqlalchemy.orm import joinedload

from app.components.document_dialog import open_document_dialog
from app.core.accounting_logic import book_patient_session, generate_invoice_number
from app.core.database import get_session
from app.core.logger import app_logger
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

# ── KI INITIALISIERUNG (WHISPER) ────────────────────────────────────────────
try:
    from faster_whisper import WhisperModel

    app_logger.info("Lade Whisper-Modell...")
    whisper_model = WhisperModel("small", device="cpu", compute_type="default")
    app_logger.info("Whisper-Modell erfolgreich geladen!")
except ImportError:
    whisper_model = None
    app_logger.error("FEHLER: faster-whisper ist nicht installiert!")

# ── KI INITIALISIERUNG (VOSK FÜR LIVE-STREAMING) ───────────────────────────
try:
    import vosk

    app_logger.info("Prüfe Vosk-Modell...")
    VOSK_DIR = "vosk-model-small-de-0.15"
    if not os.path.exists(VOSK_DIR):
        app_logger.info("Lade deutsches Vosk-Modell herunter (45 MB)...")
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


# ── STATUS-HILFSFUNKTION ─────────────────────────────────────────────────────
# Priorität:  Bezahlt  >  Verrechnet  >  Abgeschlossen  >  Offen
def _session_status(s) -> str:
    if s.is_invoiced and s.is_paid:
        return "Bezahlt"
    if s.is_invoiced:
        return "Verrechnet"
    if getattr(s, "is_closed", False):
        return "Abgeschlossen"
    return "Offen"


def patient_detail_page(navigate) -> None:
    patient_id = nicegui_app.storage.user.get("current_patient_id")

    state = {
        "active_tab":            "Personalien",
        "first_name":            "",
        "last_name":             "",
        "birthdate":             "",
        "gender":                "",
        "notes":                 "",
        "ins_active":            None,
        "ins_history":           [],
        "phones":                [],
        "emails":                [],
        "addresses":             [],
        "sessions":              [],
        # Sitzungsdialog
        "sess_id":               None,
        "sess_date":             "",
        "sess_time_from":        "",
        "sess_time_to":          "",
        "sess_issue":            "",
        "sess_approach":         "",
        "sess_protocol":         "",
        "sess_booking_text":     "",
        "sess_is_closed":        False,
        "sess_is_invoiced":      False,
        "sess_payment_method_id": None,
        "sess_vat_id":           None,
        "sess_is_paid":          False,
        "sess_amount":           0.0,
        # Tabellenfilter (kombinierter Tab)
        "sess_filter":           "Alle",
        # Aufnahme
        "recording_field":       None,
        "recording_original_text": "",
    }

    mic_buttons: dict = {}
    textareas:   dict = {}

    # ── DATENLADEN ──────────────────────────────────────────────────────────
    def load_data():
        if not patient_id:
            return
        with get_session() as session:
            p = session.query(Patient).filter_by(id=patient_id).first()
            if not p:
                return
            state["first_name"] = p.first_name or ""
            state["last_name"]  = p.last_name  or ""
            state["birthdate"]  = p.birthdate.strftime("%Y-%m-%d") if p.birthdate else ""
            state["gender"]     = p.gender or ""
            state["notes"]      = p.notes  or ""

            ins = getattr(p, "insurances", [])
            act = next((i for i in ins if not getattr(i, "is_deleted", False)), None)
            state["ins_active"]  = (
                {"id": act.id, "name": act.name, "number": act.insurance_number}
                if act else None
            )
            state["ins_history"] = [
                {"id": i.id, "name": i.name, "number": i.insurance_number}
                for i in ins if getattr(i, "is_deleted", False)
            ]
            state["phones"] = [
                {"id": ph.id, "number": getattr(ph, "number", ""),
                 "type": getattr(ph, "type", "Privat"), "is_main": getattr(ph, "is_main", False)}
                for ph in getattr(p, "phones", []) if not getattr(ph, "is_deleted", False)
            ]
            state["emails"] = [
                {"id": e.id, "email": getattr(e, "email", ""),
                 "type": getattr(e, "type", "Privat"), "is_main": getattr(e, "is_main", False)}
                for e in getattr(p, "emails", []) if not getattr(e, "is_deleted", False)
            ]
            state["addresses"] = [
                {"id": a.id, "street": getattr(a, "street", ""),
                 "zip_code": getattr(a, "zip_code", ""),
                 "city": getattr(a, "city", ""), "is_main": getattr(a, "is_main", False)}
                for a in getattr(p, "addresses", []) if not getattr(a, "is_deleted", False)
            ]

    try:
        load_data()
    except Exception as e:
        app_logger.error(f"Datenbankfehler: {e}")
        ui.notify(f"Datenbankfehler: {e}", type="negative")

    # ── SPRACHAUFNAHME ───────────────────────────────────────────────────────
    async def toggle_recording(state_key):
        btn  = mic_buttons.get(state_key)
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
                        const f32 = e.inputBuffer.getChannelData(0);
                        const i16 = new Int16Array(f32.length);
                        for (let i = 0; i < f32.length; i++) {
                            let s = Math.max(-1, Math.min(1, f32[i]));
                            i16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                        }
                        window.pcmChunks.push(i16);
                    };
                    const gain = window.audioContext.createGain(); gain.gain.value = 0;
                    source.connect(window.processor);
                    window.processor.connect(gain);
                    gain.connect(window.audioContext.destination);
                    window.liveRecorder = new MediaRecorder(stream);
                    window.liveChunks = [];
                    window.liveRecorder.ondataavailable = e => { if (e.data.size > 0) window.liveChunks.push(e.data); };
                    window.liveRecorder.start();
                    window.audioStream = stream;
                    return "OK|" + window.audioContext.sampleRate;
                } catch(err) { return "ERR_NO_MIC"; }
            };
            window.getNewPcmData = async function() {
                if (!window.pcmChunks || window.pcmChunks.length === 0) return null;
                const chunks = window.pcmChunks; window.pcmChunks = [];
                let total = chunks.reduce((a, v) => a + v.length, 0);
                let result = new Int16Array(total); let offset = 0;
                for (let c of chunks) { result.set(c, offset); offset += c.length; }
                const blob = new Blob([result.buffer], {type: 'application/octet-stream'});
                return new Promise(res => { const r = new FileReader(); r.onloadend = () => res(r.result.split(',')[1]); r.readAsDataURL(blob); });
            };
            window.getLiveAudio = async function() {
                if (!window.liveChunks || window.liveChunks.length === 0) return null;
                const blob = new Blob(window.liveChunks, {type: window.liveRecorder.mimeType || 'audio/webm'});
                return new Promise(res => { const r = new FileReader(); r.onloadend = () => res(r.result); r.readAsDataURL(blob); });
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
                ui.notify("Info: Live-Stream inaktiv, Whisper finalisiert am Ende.", type="warning")
            try:
                res = await ui.run_javascript("return await window.startLiveRecord();", timeout=60.0)
                if str(res).startswith("ERR_NO_MIC"):
                    return ui.notify("Mikrofon blockiert!", type="negative")
            except TimeoutError:
                return ui.notify("Zeitüberschreitung beim Mikrofon.", type="warning")

            sample_rate = 16000
            if res and "|" in str(res):
                try:
                    sample_rate = int(float(str(res).split("|")[1]))
                except Exception:
                    pass

            state["recording_field"]        = state_key
            state["recording_original_text"] = state[state_key] or ""
            if btn:
                btn.props("color=negative icon=stop")
                btn.update()
            ui.notify("Live-Aufnahme läuft...", type="info", timeout=3.0)

            async def live_transcription_loop():
                wm = SpeechManager.get_whisper()
                vm = SpeechManager.get_vosk()
                spacer     = "\n\n" if state["recording_original_text"] else ""
                live_draft = ""
                display_str = ""
                if vm:
                    rec = vosk.KaldiRecognizer(vm, sample_rate)

                while state["recording_field"] == state_key:
                    await asyncio.sleep(0.25)
                    if state["recording_field"] != state_key:
                        break
                    if not vm:
                        continue
                    with btn.client:
                        try:
                            b64 = await ui.run_javascript("return await window.getNewPcmData();", timeout=5.0)
                        except Exception as ex:
                            app_logger.error(ex)
                            continue
                        if b64:
                            try:
                                pcm = base64.b64decode(b64)
                                def run_vosk(b):
                                    if rec.AcceptWaveform(b):
                                        return True, json.loads(rec.Result()).get("text", "")
                                    return False, json.loads(rec.PartialResult()).get("partial", "")
                                is_final, text_res = await asyncio.to_thread(run_vosk, pcm)
                                if is_final and text_res:
                                    live_draft  += (" " if live_draft else "") + text_res
                                    display_str  = live_draft
                                elif not is_final:
                                    display_str = live_draft + (" " if live_draft and text_res else "") + text_res
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
            ui.notify("Erstelle finale Whisper-Abschrift...", type="ongoing", timeout=5.0)
            try:
                await ui.run_javascript("window.stopLiveRecord();")
                await asyncio.sleep(0.5)
                b64 = await ui.run_javascript("return await window.getLiveAudio();", timeout=10.0)
                if b64 and b64.startswith("data:audio") and whisper_model:
                    _, encoded  = b64.split(",", 1)
                    audio_data  = base64.b64decode(encoded)
                    sys_tmp     = tempfile.gettempdir()
                    tmp_path    = os.path.join(sys_tmp, f"final_audio_{datetime.now().timestamp()}.webm")
                    try:
                        with open(tmp_path, "wb") as f:
                            f.write(audio_data)
                        segs, _ = await asyncio.to_thread(whisper_model.transcribe, tmp_path, language="de")
                        wt      = " ".join([s.text for s in segs]).strip()
                        spacer  = "\n\n" if state["recording_original_text"] else ""
                        if wt:
                            final_text = f"{state['recording_original_text']}{spacer}{wt}".strip()
                            state[state_key] = final_text
                            if area:
                                area.value = final_text
                    except Exception as ex:
                        app_logger.error(f"Whisper Fehler: {ex}")
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)
            except Exception as ex:
                app_logger.error(f"Whisper Fehler: {ex}")
            finally:
                if btn:
                    try:
                        btn.props("color=grey icon=mic")
                        btn.update()
                    except Exception:
                        pass
                ui.notify("Aufnahme erfolgreich gespeichert!", type="positive", timeout=3.0)
        else:
            ui.notify("Bitte beende zuerst die andere laufende Aufnahme!", type="warning")

    # ── DIALOGE (Versicherung / Kontakte) ────────────────────────────────────

    ins_state = {"id": None}
    ins_dlg   = ui.dialog()
    with ins_dlg, ui.card().classes("p-6 min-w-[400px]"):
        ui.label("Krankenkasse").classes("text-lg font-bold mb-4")
        ins_name_in = ui.input("Name").classes("w-full mb-2").props("outlined dense")
        ins_num_in  = ui.input("Versichertennummer").classes("w-full mb-4").props("outlined dense")

        def save_ins():
            with get_session() as db:
                if ins_state["id"]:
                    obj = db.query(PatientInsurance).filter_by(id=ins_state["id"]).first()
                    if obj:
                        obj.name, obj.insurance_number = ins_name_in.value, ins_num_in.value
                else:
                    p = db.query(Patient).filter_by(id=patient_id).first()
                    for i in getattr(p, "insurances", []):
                        i.is_deleted = True
                    db.add(PatientInsurance(patient_id=patient_id, name=ins_name_in.value,
                                            insurance_number=ins_num_in.value, is_deleted=False))
                db.commit()
            ins_dlg.close(); load_data(); main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=ins_dlg.close).props('flat text-color="grey"')
            ui.button("Speichern", on_click=save_ins).props('unelevated color="primary"')

    def open_ins(item=None):
        ins_state["id"] = item["id"] if item else None
        ins_name_in.value = item["name"] if item else ""
        ins_num_in.value  = item["number"] if item else ""
        ins_dlg.open()

    phone_state = {"id": None}
    phone_dlg   = ui.dialog()
    with phone_dlg, ui.card().classes("p-6 min-w-[400px]"):
        ui.label("Telefonnummer").classes("text-lg font-bold mb-4")
        phone_num_in  = ui.input("Nummer").classes("w-full mb-2").props("outlined dense")
        phone_type_in = ui.select(["Privat", "Geschäftlich", "Mobil", "Andere"], label="Typ").classes("w-full mb-2").props("outlined dense")
        phone_main_in = ui.checkbox("Als Hauptnummer festlegen").classes("mb-4")

        def save_phone():
            with get_session() as db:
                p = db.query(Patient).filter_by(id=patient_id).first()
                if phone_main_in.value:
                    for ph in getattr(p, "phones", []):
                        ph.is_main = False
                if phone_state["id"]:
                    ph = db.query(PatientPhone).filter_by(id=phone_state["id"]).first()
                    ph.number, ph.type, ph.is_main = phone_num_in.value, phone_type_in.value, phone_main_in.value
                else:
                    db.add(PatientPhone(patient_id=patient_id, number=phone_num_in.value,
                                        type=phone_type_in.value, is_main=phone_main_in.value))
                db.commit()
            phone_dlg.close(); load_data(); main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=phone_dlg.close).props('flat text-color="grey"')
            ui.button("Speichern", on_click=save_phone).props('unelevated color="primary"')

    def open_phone(item=None):
        phone_state["id"]  = item["id"]      if item else None
        phone_num_in.value = item["number"]   if item else ""
        phone_type_in.value= item["type"]     if item else "Privat"
        phone_main_in.value= item["is_main"]  if item else False
        phone_dlg.open()

    email_state = {"id": None}
    email_dlg   = ui.dialog()
    with email_dlg, ui.card().classes("p-6 min-w-[400px]"):
        ui.label("E-Mail Adresse").classes("text-lg font-bold mb-4")
        email_val_in  = ui.input("E-Mail").classes("w-full mb-2").props('outlined dense type="email"')
        email_type_in = ui.select(["Privat", "Geschäftlich", "Andere"], label="Typ").classes("w-full mb-2").props("outlined dense")
        email_main_in = ui.checkbox("Als Hauptadresse festlegen").classes("mb-4")

        def save_email():
            with get_session() as db:
                p = db.query(Patient).filter_by(id=patient_id).first()
                if email_main_in.value:
                    for em in getattr(p, "emails", []):
                        em.is_main = False
                if email_state["id"]:
                    em = db.query(PatientEmail).filter_by(id=email_state["id"]).first()
                    em.email, em.type, em.is_main = email_val_in.value, email_type_in.value, email_main_in.value
                else:
                    db.add(PatientEmail(patient_id=patient_id, email=email_val_in.value,
                                        type=email_type_in.value, is_main=email_main_in.value))
                db.commit()
            email_dlg.close(); load_data(); main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=email_dlg.close).props('flat text-color="grey"')
            ui.button("Speichern", on_click=save_email).props('unelevated color="primary"')

    def open_email(item=None):
        email_state["id"]  = item["id"]     if item else None
        email_val_in.value = item["email"]   if item else ""
        email_type_in.value= item["type"]    if item else "Privat"
        email_main_in.value= item["is_main"] if item else False
        email_dlg.open()

    addr_state = {"id": None}
    addr_dlg   = ui.dialog()
    with addr_dlg, ui.card().classes("p-6 min-w-[500px]"):
        ui.label("Postadresse").classes("text-lg font-bold mb-4")
        addr_st_in   = ui.input("Straße & Hausnummer").classes("w-full mb-2").props("outlined dense")
        with ui.row().classes("w-full gap-2 mb-2"):
            addr_zip_in  = ui.input("PLZ").classes("w-[100px]").props("outlined dense")
            addr_city_in = ui.input("Ort").classes("flex-1").props("outlined dense")
        addr_main_in = ui.checkbox("Als Hauptwohnsitz festlegen").classes("mb-4")

        def save_address():
            with get_session() as db:
                p = db.query(Patient).filter_by(id=patient_id).first()
                if addr_main_in.value:
                    for a in getattr(p, "addresses", []):
                        a.is_main = False
                if addr_state["id"]:
                    a = db.query(PatientAddress).filter_by(id=addr_state["id"]).first()
                    a.street, a.zip_code, a.city, a.is_main = (
                        addr_st_in.value, addr_zip_in.value, addr_city_in.value, addr_main_in.value)
                else:
                    db.add(PatientAddress(patient_id=patient_id, street=addr_st_in.value,
                                          zip_code=addr_zip_in.value, city=addr_city_in.value,
                                          is_main=addr_main_in.value))
                db.commit()
            addr_dlg.close(); load_data(); main_content.refresh()

        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Abbrechen", on_click=addr_dlg.close).props('flat text-color="grey"')
            ui.button("Speichern", on_click=save_address).props('unelevated color="primary"')

    def open_addr(item=None):
        addr_state["id"]   = item["id"]      if item else None
        addr_st_in.value   = item["street"]   if item else ""
        addr_zip_in.value  = item["zip_code"] if item else ""
        addr_city_in.value = item["city"]     if item else ""
        addr_main_in.value = item["is_main"]  if item else False
        addr_dlg.open()

    # ── SITZUNGSDIALOG ──────────────────────────────────────────────────────
    sess_dlg = ui.dialog()
    with sess_dlg, ui.card().classes("p-6 min-w-[1100px] max-w-[1300px]"):
        with ui.row().classes("w-full justify-between items-center mb-4"):
            ui.label("Sitzungsdetails").classes("text-lg font-bold")
            ui.button(icon="close", on_click=sess_dlg.close).props("flat round dense")

        @ui.refreshable
        def sess_lock_banner():
            if state["sess_is_invoiced"]:
                with ui.row().classes(
                    "w-full items-center gap-3 bg-amber-50 border border-amber-300 "
                    "rounded px-4 py-3 mb-4"
                ):
                    ui.icon("lock", color="warning").classes("text-xl")
                    with ui.column().classes("gap-0 flex-1"):
                        ui.label("Sitzung ist verrechnet – Felder schreibgeschützt").classes(
                            "font-semibold text-amber-800 text-sm"
                        )
                        ui.label(
                            "Zum Bearbeiten über «Wiederöffnen» in der Tabelle entsperren."
                        ).classes("text-xs text-amber-700")

        sess_lock_banner()

        with ui.row().classes("w-full gap-4 mb-4"):
            ui.input("Datum").bind_value(state, "sess_date").classes("flex-1").props(
                'outlined dense type="date"'
            ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
            ui.input("Von").bind_value(state, "sess_time_from").classes("w-[100px]").props(
                'outlined dense type="time"'
            ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
            ui.input("Bis").bind_value(state, "sess_time_to").classes("w-[100px]").props(
                'outlined dense type="time"'
            ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)

        def voice_area(label, state_key):
            with ui.row().classes("w-full items-start gap-2 mb-4"):
                t = (
                    ui.textarea(label).bind_value(state, state_key)
                    .classes("flex-1").props('outlined rows="10"')
                ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
                textareas[state_key] = t
                b = (
                    ui.button(icon="mic", on_click=lambda sk=state_key: toggle_recording(sk))
                    .props('flat round color="grey"').tooltip("Push-to-Talk")
                ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
                mic_buttons[state_key] = b

        voice_area("Anliegen / Thema", "sess_issue")
        voice_area("Lösungsansatz / Intervention", "sess_approach")
        voice_area("Protokoll / Notizen", "sess_protocol")

        ui.separator().classes("my-4")

        ui.input("Buchungstext").bind_value(state, "sess_booking_text").classes(
            "w-full mb-2"
        ).props("outlined dense").bind_enabled_from(
            state, "sess_is_invoiced", backward=lambda v: not v
        )

        with ui.row().classes("w-full gap-4 mb-4 items-center"):
            pm_select = (
                ui.select({}, label="Bezahlmethode").bind_value(state, "sess_payment_method_id")
                .classes("flex-1").props("outlined dense")
            ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
            vat_select = (
                ui.select({}, label="MwSt-Satz").bind_value(state, "sess_vat_id")
                .classes("w-[180px]").props("outlined dense")
            ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
            ui.input("Betrag (Netto CHF)").bind_value(state, "sess_amount").classes(
                "w-[180px]"
            ).props('outlined dense type="number" step="0.05"').bind_enabled_from(
                state, "sess_is_invoiced", backward=lambda v: not v
            )
            ui.checkbox("Bezahlt").bind_value(state, "sess_is_paid")

        def _do_save(is_closed: bool = False):
            if state.get("sess_is_invoiced"):
                ui.notify(
                    "Sitzung ist verrechnet – bitte zuerst über «Wiederöffnen» entsperren.",
                    type="warning",
                )
                return None
            if not state["sess_date"]:
                ui.notify("Datum ist Pflichtfeld", type="warning")
                return None
            with get_session() as db:
                if state["sess_id"]:
                    s = db.query(PatientSession).filter_by(id=state["sess_id"]).first()
                else:
                    s = PatientSession(patient_id=patient_id)
                    s.user_id = nicegui_app.storage.user.get("user_id")
                    db.add(s)
                s.date         = datetime.strptime(state["sess_date"], "%Y-%m-%d").date()
                s.time_from    = state["sess_time_from"]
                s.time_to      = state["sess_time_to"]
                s.issue        = state["sess_issue"]
                s.approach     = state["sess_approach"]
                s.protocol     = state["sess_protocol"]
                s.booking_text = state["sess_booking_text"] or None
                if is_closed:
                    try:
                        s.is_closed = True
                    except Exception:
                        pass
                s.payment_method_id = state["sess_payment_method_id"]
                s.vat_id            = state["sess_vat_id"]
                s.is_paid           = state["sess_is_paid"]
                try:
                    s.amount = float(state["sess_amount"])
                except Exception:
                    s.amount = 0.0
                db.flush()
                saved_id = s.id
                db.commit()
                try:
                    book_patient_session(db, s.id)
                    db.commit()
                except Exception as ex:
                    app_logger.error(f"Buchungsfehler im Dialog: {ex}")
            return saved_id

        def save_session():
            if _do_save(is_closed=False) is not None:
                sess_dlg.close(); load_data(); main_content.refresh()

        def close_session():
            if _do_save(is_closed=True) is not None:
                sess_dlg.close(); load_data(); main_content.refresh()

        def create_invoice_from_session():
            saved_id = _do_save(is_closed=True)
            if saved_id is not None:
                sess_dlg.close(); load_data(); main_content.refresh()
                open_invoice_selection(preselect_id=saved_id)

        with ui.row().classes("w-full justify-between items-center gap-2 mt-2"):
            ui.button("Abbrechen", on_click=sess_dlg.close).props('flat color="grey"')
            with ui.row().classes("gap-2"):
                ui.button("Speichern", on_click=save_session).props(
                    'outline color="primary"'
                ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
                ui.button("Abschliessen", icon="task_alt", on_click=close_session).props(
                    'outline color="positive"'
                ).bind_enabled_from(state, "sess_is_invoiced", backward=lambda v: not v)
                ui.button(
                    "Rechnung erstellen", icon="receipt_long",
                    on_click=create_invoice_from_session,
                ).props('unelevated color="primary"').bind_enabled_from(
                    state, "sess_is_invoiced", backward=lambda v: not v
                )

    def open_session(s=None):
        with get_session() as db:
            active_pms  = db.query(PaymentMethod).filter_by(is_active=True).all()
            pm_options  = {pm.id: pm.title for pm in active_pms}
            today       = date.today()
            active_vats = db.query(VATSetting).filter_by(is_active=True).all()
            vat_options = {}
            for v in active_vats:
                if not v.end_date or v.end_date >= today:
                    vat_options[v.id] = f"{v.description} ({v.rate}%)"
            if s:
                if s.payment_method_id and s.payment_method_id not in pm_options:
                    pm_options[s.payment_method_id] = f"Archiviert (ID {s.payment_method_id})"
                if s.vat_id and s.vat_id not in vat_options:
                    vat_options[s.vat_id] = f"Archiviert (ID {s.vat_id})"
            pm_select.options  = pm_options
            vat_select.options = vat_options
            pm_select.update()
            vat_select.update()

        state.update({
            "sess_id":               getattr(s, "id", None) if s else None,
            "sess_date": (
                s.date.strftime("%Y-%m-%d") if s and getattr(s, "date", None)
                else datetime.now().strftime("%Y-%m-%d")
            ),
            "sess_time_from":        getattr(s, "time_from", ""),
            "sess_time_to":          getattr(s, "time_to", ""),
            "sess_issue":            getattr(s, "issue", ""),
            "sess_approach":         getattr(s, "approach", ""),
            "sess_protocol":         getattr(s, "protocol", ""),
            "sess_booking_text": (
                getattr(s, "booking_text", None)
                or f"Sitzung {state['first_name']} {state['last_name']}".strip()
            ),
            "sess_is_closed":        getattr(s, "is_closed",   False) if s else False,
            "sess_is_invoiced":      getattr(s, "is_invoiced",  False) if s else False,
            "sess_payment_method_id": getattr(s, "payment_method_id", None),
            "sess_vat_id":           getattr(s, "vat_id", None),
            "sess_is_paid":          getattr(s, "is_paid",  False),
            "sess_amount":           getattr(s, "amount",   0.0),
        })
        sess_lock_banner.refresh()
        sess_dlg.open()

    # ── RECHNUNGSAUSWAHL-DIALOG (aus Sitzungsdialog) ─────────────────────────
    invoice_selection_dlg = ui.dialog()

    def open_invoice_selection(preselect_id: int = None):
        with get_session() as db:
            open_sess = (
                db.query(PatientSession)
                .filter_by(patient_id=patient_id, is_deleted=False, is_paid=False)
                .order_by(PatientSession.date.desc()).all()
            )
            rows = [
                {
                    "id":           s.id,
                    "date":         s.date.strftime("%d.%m.%Y") if s.date else "",
                    "text":         s.booking_text or f"Sitzung {state['first_name']} {state['last_name']}",
                    "amount":       f"CHF {s.amount:.2f}",
                    "status":       "Abgeschlossen" if getattr(s, "is_closed", False) else "Offen",
                    "preselected":  s.id == preselect_id,
                }
                for s in open_sess
            ]

        invoice_selection_dlg.clear()
        with invoice_selection_dlg, ui.card().classes("p-6 min-w-[720px] max-w-[960px]"):
            ui.label("Sitzungen für Rechnung auswählen").classes("text-lg font-bold mb-1")
            ui.label("Wählen Sie alle Sitzungen, die auf diese Rechnung sollen:").classes(
                "text-sm text-slate-500 mb-4"
            )
            if not rows:
                ui.label("Keine offenen Sitzungen vorhanden.").classes("text-slate-400 italic py-4")
                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button("Schliessen", on_click=invoice_selection_dlg.close).props('flat color="grey"')
            else:
                checks: dict[int, object] = {}
                with ui.row().classes(
                    "w-full gap-3 py-2 border-b border-slate-300 "
                    "text-xs font-semibold text-slate-500 uppercase"
                ):
                    ui.label("").classes("w-6")
                    ui.label("Datum").classes("w-24")
                    ui.label("Buchungstext").classes("flex-1")
                    ui.label("Betrag").classes("w-24 text-right")
                    ui.label("Status").classes("w-28 text-center")

                for row in rows:
                    with ui.row().classes(
                        "w-full items-center gap-3 py-2 border-b border-slate-100 hover:bg-slate-50"
                    ):
                        cb = ui.checkbox(value=row["preselected"]).classes("w-6")
                        checks[row["id"]] = cb
                        ui.label(row["date"]).classes("w-24 text-sm font-medium")
                        ui.label(row["text"]).classes("flex-1 text-sm text-slate-700 truncate")
                        ui.label(row["amount"]).classes("w-24 text-sm font-medium text-right")
                        sc = "bg-blue-100 text-blue-800" if row["status"] == "Abgeschlossen" \
                             else "bg-amber-100 text-amber-800"
                        ui.label(row["status"]).classes(
                            f"text-xs font-medium px-2 py-0.5 rounded-full w-28 text-center {sc}"
                        )

                def do_create_invoice():
                    sel = [sid for sid, cb in checks.items() if cb.value]
                    if not sel:
                        ui.notify("Bitte mindestens eine Sitzung auswählen.", type="warning")
                        return
                    invoice_selection_dlg.close()
                    open_document_dialog(
                        doc_type="Rechnung", patient_id=patient_id,
                        session_ids=sel, on_success=lambda: main_content.refresh(),
                    )

                with ui.row().classes("w-full justify-end gap-2 mt-6"):
                    ui.button("Abbrechen", on_click=invoice_selection_dlg.close).props('flat color="grey"')
                    ui.button("Rechnung erstellen", icon="receipt_long",
                               on_click=do_create_invoice).props('unelevated color="primary"')

        invoice_selection_dlg.open()

    # ── HILFSFUNKTIONEN ──────────────────────────────────────────────────────
    def hard_delete(model_class, item_id):
        with get_session() as db:
            item = db.query(model_class).filter_by(id=item_id).first()
            if item:
                db.delete(item); db.commit()
        load_data(); main_content.refresh()

    def soft_delete(model_class, item_id):
        with get_session() as db:
            item = db.query(model_class).filter_by(id=item_id).first()
            if item:
                item.is_deleted = True; db.commit()
        load_data(); main_content.refresh()

    def save_basic():
        with get_session() as db:
            p = db.query(Patient).filter_by(id=patient_id).first() if patient_id else Patient()
            if not patient_id:
                db.add(p)
            p.first_name, p.last_name = state["first_name"], state["last_name"]
            p.gender, p.notes = state["gender"], state["notes"]
            if state["birthdate"]:
                try:
                    p.birthdate = datetime.strptime(state["birthdate"], "%Y-%m-%d").date()
                except ValueError:
                    return ui.notify("Format YYYY-MM-DD nutzen.", type="negative")
            else:
                p.birthdate = None
            db.commit()
            if not patient_id:
                nicegui_app.storage.user["current_patient_id"] = p.id
                navigate("/patient_detail"); return
            ui.notify("Stammdaten gespeichert", type="positive")

    # ── SEITENHEADER ─────────────────────────────────────────────────────────
    with ui.row().classes("items-center w-full mb-6 gap-4"):
        ui.button(icon='arrow_back', on_click=lambda: navigate('/patients')).props('flat round dense')
        ui.label("Patientenakte" if patient_id else "Neuer Patient").classes(
            "text-[24px] font-semibold text-[#1e3a5f]"
        )
        ui.space()
        ui.button("Speichern", icon="save", on_click=save_basic).props("unelevated").classes(
            "bg-[#0078d4] text-white"
        )

    # ── SPLITTER-LAYOUT ──────────────────────────────────────────────────────
    with ui.splitter(value=15).classes("w-full") as splitter:
        with splitter.before:

            def set_tab(t):
                state["active_tab"] = t
                menu_col.refresh(); main_content.refresh()

            def btn_cls(t):
                base = "w-full px-4 py-3 text-[14px] rounded-none transition-colors border-r-4 "
                return base + (
                    "bg-blue-50 text-blue-700 border-blue-500"
                    if state["active_tab"] == t
                    else "text-slate-600 hover:bg-slate-50 border-transparent"
                )

            @ui.refreshable
            def menu_col():
                with ui.column().classes("w-full gap-0 mt-2"):
                    bp = 'flat align="left" no-caps'
                    ui.button("Personalien",   icon="badge",        on_click=lambda: set_tab("Personalien")  ).classes(btn_cls("Personalien")  ).props(bp)
                    b2 = ui.button("Kontaktangaben", icon="contact_mail", on_click=lambda: set_tab("Kontaktangaben")).classes(btn_cls("Kontaktangaben")).props(bp)
                    # ── Ehemals "Sitzungen" + "Abrechnungen" → jetzt ein Tab ──
                    b3 = ui.button("Sitzungen",      icon="event_note",   on_click=lambda: set_tab("Sitzungen")     ).classes(btn_cls("Sitzungen")     ).props(bp)
                    b4 = ui.button("Dateien",        icon="attach_file",  on_click=lambda: set_tab("Dateien")       ).classes(btn_cls("Dateien")       ).props(bp)
                    if not patient_id:
                        b2.disable(); b3.disable(); b4.disable()

            menu_col()

        with splitter.after:

            @ui.refreshable
            def main_content():
                with ui.column().classes("w-full pl-6"):

                    # ════════════════════════════════════════════════════════
                    # PERSONALIEN
                    # ════════════════════════════════════════════════════════
                    if state["active_tab"] == "Personalien":
                        with ui.card().classes("w-full max-w-3xl p-6 shadow-sm mb-6"):
                            ui.label("Stammdaten").classes("text-[18px] font-medium mb-4 text-[#1e3a5f]")
                            with ui.row().classes("w-full gap-4 mb-4"):
                                ui.input("Vorname").bind_value(state, "first_name").classes("flex-1").props("outlined dense")
                                ui.input("Nachname").bind_value(state, "last_name").classes("flex-1").props("outlined dense")
                            with ui.row().classes("w-full gap-4 mb-4"):
                                ui.input("Geburtsdatum").bind_value(state, "birthdate").classes("flex-1").props('outlined dense type="date"')
                                ui.select(["Männlich", "Weiblich", "Divers", "Keine Angabe"], label="Geschlecht").bind_value(state, "gender").classes("flex-1").props("outlined dense")
                            ui.textarea("Bemerkungen").bind_value(state, "notes").classes("w-full").props('outlined rows="4"')

                        if patient_id:
                            with ui.card().classes("w-full max-w-3xl p-6 shadow-sm border-l-4 border-[#0078d4]"):
                                with ui.row().classes("w-full items-center justify-between mb-4"):
                                    ui.label("Krankenversicherung").classes("text-[18px] font-medium text-[#1e3a5f]")
                                    ui.button("Neu", icon="add", on_click=lambda: open_ins()).props("outline dense").classes("text-[#0078d4]")
                                act = state["ins_active"]
                                if act:
                                    with ui.row().classes("w-full items-center justify-between bg-blue-50 p-3 rounded mb-4"):
                                        with ui.column().classes("gap-0"):
                                            ui.label(act["name"]).classes("font-semibold text-slate-800")
                                            ui.label(f"Versicherten-Nr: {act['number']}").classes("text-sm text-slate-500")
                                        with ui.row().classes("gap-1"):
                                            ui.button(icon="edit",   on_click=lambda: open_ins(act)).props('flat round dense color="primary"')
                                            ui.button(icon="delete", on_click=lambda: hard_delete(PatientInsurance, act["id"])).props('flat round dense color="negative"')
                                else:
                                    ui.label("Keine aktive Versicherung hinterlegt.").classes("text-slate-500 italic mb-4")
                                if state["ins_history"]:
                                    with ui.expansion("Versicherungs-Historie anzeigen").classes("w-full shadow-none border border-slate-200"):
                                        for old in state["ins_history"]:
                                            with ui.row().classes("w-full items-center justify-between p-2 border-b border-slate-100 last:border-0"):
                                                with ui.column().classes("gap-0"):
                                                    ui.label(old["name"]).classes("text-sm text-gray-500 line-through")
                                                    ui.label(f"Nr: {old['number']}").classes("text-xs text-gray-400")
                                                with ui.row().classes("gap-1"):
                                                    ui.button(icon="edit",   on_click=lambda o=old: open_ins(o)).props('flat round dense color="primary" size="sm"')
                                                    ui.button(icon="delete", on_click=lambda o=old: hard_delete(PatientInsurance, o["id"])).props('flat round dense color="negative" size="sm"')

                    # ════════════════════════════════════════════════════════
                    # KONTAKTANGABEN
                    # ════════════════════════════════════════════════════════
                    elif state["active_tab"] == "Kontaktangaben":
                        def draw_list(title, items, open_fn, model_cls, fmt_main, fmt_sub):
                            with ui.card().classes("w-full max-w-3xl p-6 shadow-sm mb-6"):
                                with ui.row().classes("w-full items-center justify-between mb-4"):
                                    ui.label(title).classes("text-[18px] font-medium text-[#1e3a5f]")
                                    ui.button("Neu", icon="add", on_click=lambda: open_fn()).props("outline dense").classes("text-[#0078d4]")
                                if not items:
                                    ui.label("Noch keine Einträge vorhanden.").classes("text-slate-400 italic")
                                for item in sorted(items, key=lambda x: not x["is_main"]):
                                    with ui.row().classes("w-full items-center justify-between p-2 border-b border-slate-100 last:border-0"):
                                        with ui.row().classes("items-center gap-3"):
                                            ui.icon("star", color="amber" if item["is_main"] else "transparent").classes("text-lg")
                                            with ui.column().classes("gap-0"):
                                                ui.label(fmt_main(item)).classes("font-medium")
                                                ui.label(fmt_sub(item)).classes("text-xs text-slate-500")
                                        with ui.row().classes("gap-1"):
                                            ui.button(icon="edit",   on_click=lambda i=item: open_fn(i)).props('flat round dense color="primary" size="sm"')
                                            ui.button(icon="delete", on_click=lambda i=item, m=model_cls: soft_delete(m, i["id"])).props('flat round dense color="negative" size="sm"')

                        draw_list("Telefonnummern", state["phones"],    open_phone, PatientPhone,    lambda i: i["number"],  lambda i: i["type"])
                        draw_list("E-Mail Adressen", state["emails"],   open_email, PatientEmail,   lambda i: i["email"],   lambda i: i["type"])
                        draw_list("Postadressen",    state["addresses"], open_addr,  PatientAddress, lambda i: i["street"],  lambda i: f"{i['zip_code']} {i['city']}")

                    # ════════════════════════════════════════════════════════
                    # SITZUNGEN & ABRECHNUNG  (ehemals 2 separate Tabs)
                    # ════════════════════════════════════════════════════════
                    elif state["active_tab"] == "Sitzungen":

                        # ── Datenbankabfrage ──────────────────────────────
                        with get_session() as db:
                            sitzungen = (
                                db.query(PatientSession)
                                .options(
                                    joinedload(PatientSession.payment_method),
                                    joinedload(PatientSession.vat_setting),
                                )
                                .filter_by(patient_id=patient_id, is_deleted=False)
                                .order_by(PatientSession.date.desc())
                                .all()
                            )
                            all_rows = []
                            for s in sitzungen:
                                vat_rate     = s.vat_setting.rate if s.vat_setting else 0.0
                                amount_gross = s.amount * (1 + vat_rate / 100)
                                inv_num      = s.invoice_number or ""
                                inv_ver      = s.invoice_version or 0
                                # Rechnungsnummer-Anzeige: RE-2026-001  oder  RE-2026-001.2 (bei Wiederöffnung)
                                inv_display  = f"{inv_num}.{inv_ver}" if inv_ver > 0 else inv_num
                                status       = _session_status(s)
                                all_rows.append({
                                    "id":             s.id,
                                    "date":           s.date.strftime("%d.%m.%Y") if s.date else "",
                                    "booking_text":   s.booking_text or f"Sitzung {state['first_name']} {state['last_name']}",
                                    "amount_str":     f"CHF {amount_gross:.2f}",
                                    "vat":            f"{vat_rate}%",
                                    "invoice_number": inv_display,
                                    "status":         status,
                                    "payment_method": s.payment_method.title if s.payment_method else "—",
                                    "is_paid":        s.is_paid,
                                    "is_invoiced":    s.is_invoiced,
                                })

                        # ── Filter anwenden ───────────────────────────────
                        f = state["sess_filter"]
                        rows = (
                            [r for r in all_rows if r["status"] == f]
                            if f != "Alle" else all_rows
                        )

                        # ── Statistik-Chips ───────────────────────────────
                        cnt = {s: sum(1 for r in all_rows if r["status"] == s)
                               for s in ("Offen", "Abgeschlossen", "Verrechnet", "Bezahlt")}

                        # ── Kopf ──────────────────────────────────────────
                        with ui.row().classes("w-full justify-between items-start mb-4 gap-4 flex-wrap"):
                            with ui.column().classes("gap-2"):
                                ui.label("Sitzungen").classes("text-[20px] font-medium text-[#1e3a5f]")
                                # Statistik-Chips
                                with ui.row().classes("gap-2 flex-wrap"):
                                    for label, chip_cls in [
                                        ("Offen",         "bg-amber-100  text-amber-800"),
                                        ("Abgeschlossen", "bg-blue-100   text-blue-800"),
                                        ("Verrechnet",    "bg-violet-100 text-violet-800"),
                                        ("Bezahlt",       "bg-emerald-100 text-emerald-800"),
                                    ]:
                                        ui.label(f"{label}: {cnt[label]}").classes(
                                            f"text-xs font-semibold px-2 py-0.5 rounded-full {chip_cls}"
                                        )
                            with ui.row().classes("gap-2 items-center"):
                                ui.button("Neue Sitzung", icon="add", on_click=open_session).props(
                                    "unelevated"
                                ).classes("bg-[#0078d4] text-white")

                        # ── Filter-Leiste ─────────────────────────────────
                        # Jeder Button hat eine semantisch passende Farbe
                        with ui.row().classes("gap-2 mb-4 flex-wrap items-center"):
                            ui.label("Filter:").classes("text-xs text-slate-400 self-center mr-1")
                            filter_defs = [
                                # (key,           aktiv-Klassen,                          inaktiv-Klassen)
                                ("Alle",          "bg-slate-700  text-white",              "bg-white text-slate-600  border border-slate-300"),
                                ("Offen",         "bg-amber-500  text-white",              "bg-white text-amber-700  border border-amber-300"),
                                ("Abgeschlossen", "bg-blue-600   text-white",              "bg-white text-blue-700   border border-blue-300"),
                                ("Verrechnet",    "bg-violet-600 text-white",              "bg-white text-violet-700 border border-violet-300"),
                                ("Bezahlt",       "bg-emerald-600 text-white",             "bg-white text-emerald-700 border border-emerald-300"),
                            ]
                            for key, active_cls, inactive_cls in filter_defs:
                                is_active = (state["sess_filter"] == key)
                                ui.button(
                                    key,
                                    on_click=lambda k=key: [
                                        state.update({"sess_filter": k}),
                                        main_content.refresh(),
                                    ],
                                ).classes(
                                    f"text-xs px-3 py-1 rounded-full font-medium "
                                    f"{'border-0 ' + active_cls if is_active else inactive_cls}"
                                ).props("flat no-caps dense")

                        if not rows:
                            ui.label("Keine Sitzungen für diesen Filter.").classes(
                                "text-slate-400 italic py-4"
                            )
                        else:
                            columns = [
                                {"name": "date",           "label": "Datum",        "field": "date",           "align": "left",  "sortable": True},
                                {"name": "booking_text",   "label": "Buchungstext", "field": "booking_text",   "align": "left"},
                                {"name": "amount_str",     "label": "Betrag",       "field": "amount_str",     "align": "right"},
                                {"name": "vat",            "label": "MwSt",         "field": "vat",            "align": "right"},
                                {"name": "invoice_number", "label": "Rechnungs-Nr.", "field": "invoice_number", "align": "left"},
                                {"name": "status",         "label": "Status",        "field": "status",         "align": "center"},
                                {"name": "payment_method", "label": "Zahlungsart",   "field": "payment_method", "align": "left"},
                                {"name": "actions",        "label": "",              "field": "id",             "align": "right"},
                            ]

                            tbl = ui.table(
                                columns=columns, rows=rows,
                                row_key="id", selection="multiple",
                            ).classes("w-full shadow-sm border border-slate-200 bg-white")

                            # ── Zeilen-Hintergrundfarbe (Tailwind) ────────
                            tbl.add_slot("body-row", r"""
                                <q-tr :props="props"
                                      :class="props.row.status === 'Bezahlt'       ? 'bg-emerald-50' :
                                              props.row.status === 'Verrechnet'    ? 'bg-violet-50'  :
                                              props.row.status === 'Abgeschlossen' ? 'bg-blue-50'    : ''">
                                    <q-td v-for="col in props.cols" :key="col.name" :props="props">
                                        {{ col.value }}
                                    </q-td>
                                </q-tr>
                            """)

                            # ── Checkbox: nur bei noch nicht verrechneten ─
                            tbl.add_slot("body-selection", r"""
                                <q-td :auto-width="true">
                                    <q-checkbox :class="{ invisible: props.row.is_invoiced }"
                                                v-model="props.selected" color="primary" />
                                </q-td>
                            """)

                            # ── Status-Badge (Tailwind) ───────────────────
                            # Farbsemantik:
                            #   Offen         → Amber   (ausstehend, Aufmerksamkeit nötig)
                            #   Abgeschlossen → Blau    (erledigt, aber noch nicht verrechnet)
                            #   Verrechnet    → Violett (in Buchhaltung übergeben, Zahlung ausstehend)
                            #   Bezahlt       → Grün    (vollständig abgewickelt)
                            tbl.add_slot("body-cell-status", r"""
                                <q-td :props="props">
                                    <span :class="{
                                        'bg-amber-100   text-amber-800':   props.row.status === 'Offen',
                                        'bg-blue-100    text-blue-800':    props.row.status === 'Abgeschlossen',
                                        'bg-violet-100  text-violet-800':  props.row.status === 'Verrechnet',
                                        'bg-emerald-100 text-emerald-800': props.row.status === 'Bezahlt'
                                    }" class="text-xs font-semibold px-2 py-0.5 rounded-full whitespace-nowrap">
                                        {{ props.row.status }}
                                    </span>
                                </q-td>
                            """)

                            # ── Rechnungsnummer: Monospace-Font, leer = "—" ──
                            tbl.add_slot("body-cell-invoice_number", r"""
                                <q-td :props="props">
                                    {{ props.row.invoice_number || '-' }}
                                </q-td>
                            """)

                            # ── Aktionsbuttons pro Zeile ──────────────────
                            tbl.add_slot("body-cell-actions", r"""
                                <q-td :props="props">
                                    <div class="row items-center justify-end no-wrap gap-1">
                                        <!-- Bearbeiten (immer) -->
                                        <q-btn flat round dense icon="edit"
                                               color="primary" size="sm"
                                               @click="$parent.$emit('t_edit', props.row.id)">
                                            <q-tooltip>Bearbeiten</q-tooltip>
                                        </q-btn>
                                        <!-- Wiederöffnen: nur wenn verrechnet -->
                                        <q-btn v-if="props.row.is_invoiced"
                                               flat round dense icon="lock_open" size="sm"
                                               class="text-amber-600"
                                               @click="$parent.$emit('t_reopen', props.row.id)">
                                            <q-tooltip>Wiederöffnen (neue Rechnungsnr.)</q-tooltip>
                                        </q-btn>
                                        <!-- Bezahlt: nur wenn noch nicht bezahlt -->
                                        <q-btn v-if="!props.row.is_paid"
                                               flat round dense icon="price_check" size="sm"
                                               class="text-emerald-600"
                                               @click="$parent.$emit('t_paid', props.row.id)">
                                            <q-tooltip>Als bezahlt markieren</q-tooltip>
                                        </q-btn>
                                        <!-- Quittung: nur wenn bezahlt -->
                                        <q-btn v-if="props.row.is_paid"
                                               flat round dense icon="print"
                                               color="primary" size="sm"
                                               @click="$parent.$emit('t_receipt', props.row)">
                                            <q-tooltip>Quittung drucken</q-tooltip>
                                        </q-btn>
                                        <!-- Löschen: nur wenn nicht verrechnet -->
                                        <q-btn v-if="!props.row.is_invoiced"
                                               flat round dense icon="delete"
                                               color="negative" size="sm"
                                               @click="$parent.$emit('t_delete', props.row.id)">
                                            <q-tooltip>Löschen</q-tooltip>
                                        </q-btn>
                                    </div>
                                </q-td>
                            """)

                            # ── Sammel-Toolbar (unterhalb der Tabelle) ────
                            with ui.row().classes("w-full justify-end gap-2 mt-3"):

                                def handle_batch_invoice_success():
                                    selected_ids = [r["id"] for r in tbl.selected]
                                    if selected_ids:
                                        with get_session() as db:
                                            for sid in selected_ids:
                                                s = db.query(PatientSession).filter_by(id=sid).first()
                                                if s and not s.is_invoiced:
                                                    s.invoice_number = generate_invoice_number(db, s.date.year)
                                                    print(s.invoice_number)
                                                    s.invoice_version = 0
                                                    s.is_invoiced = True
                                                    db.flush()   # ← BUGFIX: Nummer für nächste Iteration sichtbar
                                            db.commit()
                                    tbl.selected.clear()
                                    main_content.refresh()

                                def print_batch_invoice():
                                    uninvoiced = [r for r in tbl.selected if not r["is_invoiced"]]
                                    if not uninvoiced:
                                        ui.notify(
                                            "Bitte mind. eine noch nicht verrechnete Sitzung auswählen.",
                                            type="warning",
                                        )
                                        return
                                    open_document_dialog(
                                        doc_type="Rechnung",
                                        patient_id=patient_id,
                                        session_ids=[r["id"] for r in uninvoiced],
                                        on_success=handle_batch_invoice_success,
                                    )

                                ui.button(
                                    "Rechnung für Auswahl",
                                    icon="receipt_long",
                                    on_click=print_batch_invoice,
                                ).props("unelevated").classes("bg-[#0078d4] text-white")

                                ui.button(
                                    "Zusammenzug", icon="summarize",
                                    on_click=lambda: ui.notify("Zusammenzug folgt…", type="info"),
                                ).props("outline").classes("text-[#0078d4]")

                            # ── Event-Handler ─────────────────────────────

                            def on_edit(msg):
                                sid = msg.args
                                with get_session() as db:
                                    s = db.query(PatientSession).filter_by(id=sid).first()
                                    if s:
                                        db.expunge(s)
                                if s:
                                    open_session(s)

                            def on_reopen(msg):
                                """
                                Sitzung entsperren.
                                invoice_number bekommt Versions-Suffix  RE-2026-001 → RE-2026-001.1
                                """
                                sid = msg.args
                                with get_session() as db:
                                    s = db.query(PatientSession).filter_by(id=sid).first()
                                    if s and s.is_invoiced:
                                        new_ver = (s.invoice_version or 0) + 1
                                        base    = (s.invoice_number or "").split(".")[0]
                                        s.invoice_number  = f"{base}.{new_ver}"
                                        s.invoice_version = new_ver
                                        s.is_invoiced     = False
                                        db.commit()
                                ui.notify("Sitzung wiedergeöffnet – neue Rechnungsnr. vergeben.", type="warning")
                                main_content.refresh()

                            def on_invoice(msg):
                                row = msg.args
                                session_id = row["id"]

                                # 1. Datenbank-Update durchführen
                                try:
                                    with get_session() as db:
                                        # Diese Funktion muss die Nummer vergeben und den Status setzen
                                        book_patient_session(db, session_id)
                                        db.commit()
                                    ui.notify("Rechnung verbucht und Nummer generiert", type="positive")
                                except Exception as e:
                                    app_logger.error(f"Fehler beim Verrechnen: {e}")
                                    ui.notify(f"Fehler: {e}", type="negative")
                                    return

                                # 2. UI aktualisieren, damit die neue Nummer und der Status sichtbar werden
                                main_content.refresh()

                                # 3. Erst jetzt den Dialog zum Drucken/Vorschau öffnen
                                open_document_dialog(
                                    doc_type="Rechnung", patient_id=patient_id,
                                    session_ids=[session_id],
                                )

                            def on_paid(msg):
                                sid = msg.args
                                with get_session() as db:
                                    s = db.query(PatientSession).filter_by(id=sid).first()
                                    if s:
                                        s.is_paid = True
                                        db.commit()
                                        try:
                                            book_patient_session(db, s.id)
                                            db.commit()
                                        except Exception as ex:
                                            app_logger.error(f"Buchungsfehler: {ex}")
                                ui.notify("Als bezahlt markiert.", type="positive")
                                main_content.refresh()

                            def on_receipt(msg):
                                row = msg.args
                                open_document_dialog(
                                    doc_type="Quittung", patient_id=patient_id,
                                    session_ids=[row["id"]],
                                )

                            def on_delete(msg):
                                soft_delete(PatientSession, msg.args)

                            tbl.on("t_edit",    on_edit)
                            tbl.on("t_reopen",  on_reopen)
                            tbl.on("t_invoice", on_invoice)
                            tbl.on("t_paid",    on_paid)
                            tbl.on("t_receipt", on_receipt)
                            tbl.on("t_delete",  on_delete)

                    # ════════════════════════════════════════════════════════
                    # DATEIEN
                    # ════════════════════════════════════════════════════════
                    elif state["active_tab"] == "Dateien":
                        ui.label("Dateien kommen hier hin…").classes("text-lg text-slate-500")

            main_content()

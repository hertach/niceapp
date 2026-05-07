# app/pages/admin/company_settings.py
import asyncio
import os

from nicegui import ui

from app.core.database import get_session
from app.models.app_setting import AppSetting
from app.models.company_setting import CompanyProfile, DocumentTemplate


def company_settings_page() -> None:
    ui.label("Firmenangaben").classes(
        "text-[24px] font-semibold text-[#1e3a5f] mb-4"
    )

    state = {
        "profile_id": None,
        "name": "",
        "street": "",
        "zip_code": "",
        "city": "",
        "phone": "",
        "email": "",
        "website": "",
        "vat_number": "",
        "payment_terms_days": 30,
        "payment_terms_mode": "Netto",
        "iban": "",
        "bank_name": "",
        "account_number": "",
        "bic_swift": "",
        "logo_path": None,
    }

    # Lade dynamische Pfade aus der DB
    with get_session() as session:
        app_settings = session.query(AppSetting).first()

        # Sicherer Fallback: Prüft ob app_settings existiert UND ob die Spalte nicht NULL/None ist
        LOGO_DIR = (
            app_settings.upload_path_logos
            if app_settings and app_settings.upload_path_logos
            else "./data/uploads/logos"
        )

    # Ordner sicherstellen
    os.makedirs(LOGO_DIR, exist_ok=True)

    def load_company_data():
        with get_session() as session:
            profile = session.query(CompanyProfile).first()
            if profile:
                state.update({
                    "profile_id": profile.id,
                    "name": profile.name or "",
                    "street": profile.street or "",
                    "zip_code": profile.zip_code or "",
                    "city": profile.city or "",
                    "phone": profile.phone or "",
                    "email": profile.email or "",
                    "website": profile.website or "",
                    "vat_number": profile.vat_number or "",
                    "payment_terms_days": profile.payment_terms_days or 30,
                    "payment_terms_mode": profile.payment_terms_mode or "Netto",
                    "iban": profile.iban or "",
                    "bank_name": profile.bank_name or "",
                    "account_number": profile.account_number or "",
                    "bic_swift": profile.bic_swift or "",
                    "logo_path": profile.logo_path,
                })
            else:
                new_profile = CompanyProfile()
                session.add(new_profile)
                session.commit()
                state["profile_id"] = new_profile.id

    load_company_data()

    def save_company_data():
        with get_session() as session:
            if state["profile_id"]:
                profile = session.get(CompanyProfile, state["profile_id"])
            else:
                profile = CompanyProfile()
                session.add(profile)

            profile.name = state["name"]
            profile.street = state["street"]
            profile.zip_code = state["zip_code"]
            profile.city = state["city"]
            profile.phone = state["phone"]
            profile.email = state["email"]
            profile.website = state["website"]
            profile.vat_number = state["vat_number"]
            profile.payment_terms_days = int(state["payment_terms_days"])
            profile.payment_terms_mode = state["payment_terms_mode"]
            profile.iban = state["iban"]
            profile.bank_name = state["bank_name"]
            profile.account_number = state["account_number"]
            profile.bic_swift = state["bic_swift"]

            session.commit()
            state["profile_id"] = profile.id
        ui.notify("Stammdaten erfolgreich gespeichert!", type="positive")

    def get_upload_filename(e) -> str:
        """Liest den Dateinamen sicher aus dem Upload-Event (inkl. NiceGUI 2.x)."""
        # 1. Falls es direkt auf dem Event liegt (NiceGUI 1.x)
        if hasattr(e, "name") and e.name:
            return e.name
        if hasattr(e, "filename") and e.filename:
            return e.filename

        # 2. Falls es im neuen 'file' Objekt liegt (NiceGUI 2.x)
        if hasattr(e, "file"):
            if hasattr(e.file, "filename") and e.file.filename:
                return e.file.filename
            if hasattr(e.file, "name") and e.file.name:
                return e.file.name

        # 3. Fallback in den args
        if hasattr(e, "args") and isinstance(e.args, dict):
            return e.args.get("name", "upload_file")

        return "upload_file"

    async def get_upload_content(e) -> bytes:
        """Sicheres Auslesen des Dateiinhalts (unterstützt synchrone und asynchrone reads)."""
        data = None

        # Verschiedene Orte prüfen, wo NiceGUI die Datei versteckt haben könnte
        if hasattr(e, "content") and hasattr(e.content, "read"):
            data = e.content.read()
        elif hasattr(e, "content") and isinstance(e.content, bytes):
            return e.content
        elif hasattr(e, "file") and hasattr(e.file, "read"):
            data = e.file.read()
        elif hasattr(e, "read"):
            data = e.read()

        # Wenn wir eine Lese-Operation gefunden haben, prüfen ob sie 'await' braucht
        if data is not None:
            if asyncio.iscoroutine(data):
                return await data  # <-- HIER WIRD AUF DIE BYTES GEWARTET
            return data

        return b""

    # WICHTIG: Die Funktion muss jetzt 'async def' sein!
    async def handle_logo_upload(e):
        filename = get_upload_filename(e)
        # Trennt den Namen von der Endung (z.B. ('bild', '.jpg'))
        _, file_extension = os.path.splitext(filename)

        # Setzt 'logo' vor die extrahierte Endung
        safe_filename = "logo" + file_extension
        filepath = os.path.join(LOGO_DIR, safe_filename)

        # WICHTIG: Wir müssen 'await' benutzen
        file_bytes = await get_upload_content(e)
        if not file_bytes:
            return ui.notify(
                "Fehler: Dateiinhalt konnte nicht gelesen werden.", type="negative"
            )

        with open(filepath, "wb") as f:
            f.write(file_bytes)

        with get_session() as session:
            profile = (
                session.query(CompanyProfile).filter_by(id=state["profile_id"]).first()
            )
            profile.logo_path = filepath
            session.commit()
            state["logo_path"] = filepath

        ui.notify("Logo erfolgreich hochgeladen", type="positive")
        logo_preview.refresh()

    # --- UI LAYOUT ---
    with ui.row().classes("w-full gap-8"):
        # Linke Spalte
        with ui.column().classes("flex-1 max-w-md gap-4"):
            with ui.card().classes("w-full p-6 shadow-sm border border-slate-200"):
                ui.label("Kontaktangaben").classes(
                    "text-lg font-bold text-[#1e3a5f] border-b border-gray-100 pb-2 mb-2"
                )
                ui.input("Firmenname").bind_value(state, "name").classes(
                    "w-full"
                ).props("outlined dense")
                ui.input("Strasse & Nr.").bind_value(state, "street").classes(
                    "w-full"
                ).props("outlined dense")
                with ui.row().classes("w-full gap-2"):
                    ui.input("PLZ").bind_value(state, "zip_code").classes(
                        "w-1/3"
                    ).props("outlined dense")
                    ui.input("Ort").bind_value(state, "city").classes("flex-1").props(
                        "outlined dense"
                    )

                ui.input("Telefon").bind_value(state, "phone").classes("w-full").props(
                    "outlined dense"
                )
                ui.input("E-Mail").bind_value(state, "email").classes("w-full").props(
                    'outlined dense type="email"'
                )
                ui.input("Webseite").bind_value(state, "website").classes(
                    "w-full"
                ).props("outlined dense")
                ui.input("MWSt-Nummer").bind_value(state, "vat_number").classes("w-full").props("outlined dense")

            with ui.card().classes("w-full p-6 shadow-sm border border-slate-200"):
                ui.label("Firmenlogo").classes(
                    "text-lg font-bold text-[#1e3a5f] border-b border-gray-100 pb-2 mb-2"
                )

                @ui.refreshable
                def logo_preview():
                    if state["logo_path"] and os.path.exists(state["logo_path"]):
                        ui.image(state["logo_path"]).classes(
                            "w-48 h-auto border rounded p-2 bg-slate-50 object-contain"
                        )
                    else:
                        ui.label("Kein Logo hinterlegt").classes(
                            "text-gray-400 italic mb-2"
                        )

                logo_preview()
                ui.upload(
                    on_upload=handle_logo_upload,
                    auto_upload=True,
                    max_files=1,
                    label="Neues Logo hochladen",
                ).props('accept="image/*" flat bordered')

        # Rechte Spalte
        with ui.column().classes("flex-1 max-w-2xl gap-4"):
            with ui.card().classes("w-full p-6 shadow-sm border border-slate-200"):
                ui.label("Kontoinformationen").classes(
                    "text-lg font-bold text-[#1e3a5f] border-b border-gray-100 pb-2 mb-2"
                )
                ui.input("Bankname").bind_value(state, "bank_name").classes(
                    "w-full"
                ).props("outlined dense")
                ui.input("IBAN").bind_value(state, "iban").classes("w-full").props(
                    "outlined dense"
                )
                ui.input("Konto-Nummer").bind_value(state, "account_number").classes("w-full").props(
                    "outlined dense")  # NEU
                ui.input("BIC / SWIFT").bind_value(state, "bic_swift").classes("w-full").props("outlined dense")

                with ui.card().classes("w-full p-6 shadow-sm border border-slate-200"):
                    ui.label("Zahlungskonditionen").classes(
                        "text-lg font-bold text-[#1e3a5f] border-b border-gray-100 pb-2 mb-2")
                    with ui.row().classes("w-full items-center gap-4"):
                        ui.number("Zahlungsziel (Tage)", format="%.0f").bind_value(state,
                                                                                     "payment_terms_days").classes(
                            "w-40").props("outlined dense")
                        ui.select(["Netto", "Brutto"], label="Modus").bind_value(state, "payment_terms_mode").classes(
                            "w-32").props("outlined dense")

                with ui.row().classes("w-full justify-end mt-4"):
                    ui.button(
                        "Stammdaten speichern", icon="save", on_click=save_company_data
                    ).props("unelevated").classes("bg-[#0078d4] text-white")

    load_company_data()
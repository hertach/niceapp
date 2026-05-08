# app/core/document_data.py
from nicegui import app as nicegui_app
from sqlalchemy.orm import Session

from app.models.company_setting import CompanyProfile
from app.models.patient import Patient, PatientSession
from app.models.user import User

# ── 1. ZENTRALE PLATZHALTER DOKUMENTATION FÜR DAS UI ──
PLACEHOLDERS = {
    "Allgemein (Firma)": [
        "{{firma_name}}",
        "{{firma_strasse}}",
        "{{firma_plz_ort}}",
        "{{firma_plz}}",
        "{{firma_ort}}",
        "{{firma_telefon}}",
        "{{firma_mail}}",
        "{{firma_www}}",
        "{{firma_logo}}",
        "{{mwst_nummer}}",
        "{{bank_name}}",
        "{{bank_iban}}",
        "{{bank_konto_nummer}}",
        "{{bank_bic_swift}}",
        "{{brutto_netto}}",
        "{{zahlungsziel}}",
    ],
    "Patient": [
        "{{p_anrede}}",
        "{{p_vorname}}",
        "{{p_nachname}}",
        "{{p_strasse}}",
        "{{p_plz}}",
        "{{p_ort}}",
        "{{p_geburtsdatum}}",
    ],
    "Summen (Für Sammelrechnung)": ["{{total_netto}}", "{{total_brutto}}"],
    "Sitzungs-Details (Für Tabellen-Schleife)": [
        "{{s.s_datum}}",
        "{{s.u_vorname}}",
        "{{s.u_nachname}}",
        "{{s.s_betrag_netto}}",
        "{{s.s_mwst_satz}}",
        "{{s.s_betrag_brutto}}",
        "{{s.s_anliegen}}",
    ],
    "Druck-Info (Benutzer, der das Dokument druckt)": [
        "{{print_u_vorname}}",
        "{{print_u_nachname}}",
        "{{print_u_name}}",
    ],
    "System & Datum": ["{{heute}}"],
}


# ── 2. FUNKTIONEN ZUM BEFÜLLEN DER PLATZHALTER ──
def get_company_context(session: Session) -> dict:
    """Sammelt alle Firmenangaben."""
    company = session.query(CompanyProfile).first()
    if not company:
        return {}

    return {
        "firma_name": company.name or "",
        "firma_strasse": company.street or "",
        "firma_plz_ort": f"{company.zip_code or ''} {company.city or ''}".strip(),
        "firma_plz": company.zip_code or "",
        "firma_ort": company.city or "",
        "firma_telefon": company.phone or "",
        "firma_mail": company.email or "",
        "firma_www": company.website or "",
        "firma_logo": company.logo_path or "",
        "mwst_nummer": company.vat_number or "",
        "bank_name": company.bank_name or "",
        "bank_iban": company.iban or "",
        "bank_konto_nummer": company.account_number or "",
        "bank_bic_swift": company.bic_swift or "",
        "zahlungsziel": company.payment_terms_days or "",
        "brutto_netto": company.payment_terms_mode or "",
    }


def get_salutation(salutation):
    match salutation:
        case "Männlich":
            return "Herr"
        case "Weiblich":
            return "Frau"
        case _:
            return ""


def get_patient_context(patient: Patient) -> dict:
    """Sammelt alle Patientendaten."""
    if not patient:
        return {}

    main_address = next((a for a in patient.addresses if a.is_main), None)
    if not main_address and patient.addresses:
        main_address = patient.addresses[0]

    return {
        "p_anrede": get_salutation(patient.gender),
        "p_vorname": patient.first_name or "",
        "p_nachname": patient.last_name or "",
        "p_geburtsdatum": (
            patient.birthdate.strftime("%d.%m.%Y") if patient.birthdate else ""
        ),
        "p_strasse": main_address.street if main_address else "",
        "p_plz": main_address.zip_code if main_address else "",
        "p_ort": main_address.city if main_address else "",
    }


def get_sessions_context(
    db_sessions: list[PatientSession], db_session: Session
) -> dict:
    """
    Sammelt Daten aus einer Liste von Sitzungen inkl. Summen.
    Zusätzlich werden Behandler (aus der Session) und der aktuell druckende Benutzer geladen.
    """
    if not db_sessions:
        return {"sessions": [], "total_netto": "0.00", "total_brutto": "0.00"}

    # 1. Den aktuell druckenden Benutzer ermitteln
    printing_user_id = nicegui_app.storage.user.get("user_id")
    print_u = (
        db_session.query(User).filter_by(id=printing_user_id).first()
        if printing_user_id
        else None
    )

    sessions_data = []
    total_net = 0.0
    total_gross = 0.0

    for p_session in db_sessions:
        # Der Benutzer, der die Sitzung durchgeführt hat (Behandler)
        u = p_session.user

        vat_rate = p_session.vat_setting.rate if p_session.vat_setting else 0.0
        brutto = p_session.amount * (1 + (vat_rate / 100))

        total_net += p_session.amount
        total_gross += brutto

        sessions_data.append(
            {
                "s_datum": (
                    p_session.date.strftime("%d.%m.%Y") if p_session.date else ""
                ),
                "u_vorname": u.first_name if u else "",
                "u_nachname": u.last_name if u else "",
                "s_betrag_netto": f"{p_session.amount:.2f}",
                "s_mwst_satz": f"{vat_rate}%",
                "s_betrag_brutto": f"{brutto:.2f}",
                "s_anliegen": p_session.issue or "",
            }
        )

    # Rückgabe des Context-Dicts
    return {
        "sessions": sessions_data,
        "total_netto": f"{total_net:.2f}",
        "total_brutto": f"{total_gross:.2f}",
        "print_u_vorname": print_u.first_name if print_u else "",
        "print_u_nachname": print_u.last_name if print_u else "",
        "print_u_name": (
            f"{print_u.first_name or ''} {print_u.last_name or ''}".strip()
            if print_u
            else ""
        ),
    }

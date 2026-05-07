# app/core/document_engine.py
import os
import platform
import subprocess
import time
from datetime import datetime

from docxtpl import DocxTemplate
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models.app_setting import AppSetting
from app.models.company_setting import CompanyProfile, DocumentTemplate
from app.models.patient import Patient, PatientSession


class DocumentEngine:
    def __init__(self):
        with get_session() as session:
            app_settings = session.query(AppSetting).first()
            self.template_dir = (
                app_settings.upload_path_templates
                if app_settings and app_settings.upload_path_templates
                else "./data/uploads/templates"
            )

            # Speicherort für generierte Dateien (später können wir diese verschlüsseln)
            self.output_dir = "./data/generated_docs"
            os.makedirs(self.output_dir, exist_ok=True)

    def _get_company_data(self, session: Session) -> dict:
        """Sammelt alle Firmenangaben für die Platzhalter."""
        company = session.query(CompanyProfile).first()
        if not company:
            return {}

        return {
            "firma_name": company.name or "",
            "firma_strasse": company.street or "",
            "firma_ort": f"{company.zip_code or ''} {company.city or ''}".strip(),
            "firma_iban": company.iban or "",
            "firma_bank": company.bank_name or "",
        }

    def _get_patient_data(self, patient: Patient) -> dict:
        """Sammelt alle Patientendaten für die Platzhalter."""
        if not patient:
            return {}

        # Hauptadresse suchen
        main_address = next((a for a in patient.addresses if a.is_main), None)
        if not main_address and patient.addresses:
            main_address = patient.addresses[0]

        return {
            "p_vorname": patient.first_name or "",
            "p_nachname": patient.last_name or "",
            "p_geburtsdatum": (
                patient.birthdate.strftime("%d.%m.%Y") if patient.birthdate else ""
            ),
            "p_strasse": main_address.street if main_address else "",
            "p_plz": main_address.zip_code if main_address else "",
            "p_ort": main_address.city if main_address else "",
        }

    def generate_document(
        self,
        doc_type: str,
        patient_id: int,
        session_ids: list[int] = None,
        convert_to_pdf: bool = True,
        specific_template_id: int = None,
    ) -> str:
        with get_session() as db_session:
            # 1. Vorlage finden (JETZT MIT SPECIFIC_TEMPLATE_ID LOGIK)
            if specific_template_id:
                tpl_record = (
                    db_session.query(DocumentTemplate)
                    .filter_by(id=specific_template_id)
                    .first()
                )
            else:
                tpl_record = (
                    db_session.query(DocumentTemplate)
                    .filter_by(doc_type=doc_type, is_default=True)
                    .first()
                )
                if not tpl_record:
                    tpl_record = (
                        db_session.query(DocumentTemplate)
                        .filter_by(doc_type=doc_type)
                        .first()
                    )

            if not tpl_record or not os.path.exists(tpl_record.file_path):
                raise FileNotFoundError(f"Keine Vorlage für '{doc_type}' gefunden.")

            # 2. Daten sammeln
            patient = db_session.query(Patient).filter_by(id=patient_id).first()
            context = self._get_company_data(db_session)
            context.update(self._get_patient_data(patient))

            # Sitzungs-Logik (Sammelrechnung)
            if session_ids:
                sessions_data = []
                total_net = 0.0
                total_gross = 0.0

                db_sessions = (
                    db_session.query(PatientSession)
                    .filter(PatientSession.id.in_(session_ids))
                    .order_by(PatientSession.date)
                    .all()
                )

                for p_session in db_sessions:
                    vat_rate = (
                        p_session.vat_setting.rate if p_session.vat_setting else 0.0
                    )
                    brutto = p_session.amount * (1 + (vat_rate / 100))

                    total_net += p_session.amount
                    total_gross += brutto

                    sessions_data.append(
                        {
                            "s_datum": (
                                p_session.date.strftime("%d.%m.%Y")
                                if p_session.date
                                else ""
                            ),
                            "s_betrag_netto": f"{p_session.amount:.2f}",
                            "s_mwst_satz": f"{vat_rate}%",
                            "s_betrag_brutto": f"{brutto:.2f}",
                            "s_anliegen": p_session.issue or "",
                        }
                    )

                context.update(
                    {
                        "sessions": sessions_data,
                        "total_netto": f"{total_net:.2f}",
                        "total_brutto": f"{total_gross:.2f}",
                    }
                )

            # 3. Word-Datei generieren
            doc = DocxTemplate(tpl_record.file_path)
            doc.render(context)

            timestamp = int(time.time())
            docx_name = f"{patient.last_name}_{doc_type}_{timestamp}.docx"
            docx_path = os.path.join(self.output_dir, docx_name)
            doc.save(docx_path)

            # 4. In PDF umwandeln
            if convert_to_pdf:
                try:
                    return self._convert_to_pdf(docx_path)
                except Exception as e:
                    print(f"PDF Konvertierung fehlgeschlagen: {e}")
                    return docx_path  # Fallback auf Word

            return docx_path

    def _convert_to_pdf(self, docx_path: str) -> str:
        """Nutzt LibreOffice Headless um die Datei zu konvertieren."""
        # Befehl finden (unter Mac oft 'soffice' oder voller Pfad)
        command = "libreoffice"
        if platform.system() == "Darwin":  # Mac
            command = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

        # Befehl: libreoffice --headless --convert-to pdf --outdir [ziel] [datei]
        subprocess.run(
            [
                command,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                self.output_dir,
                docx_path,
            ],
            check=True,
        )

        # Pfad der neuen PDF Datei zurückgeben
        pdf_path = docx_path.replace(".docx", ".pdf").replace(".odt", ".pdf")
        return pdf_path

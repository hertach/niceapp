# app/core/document_engine.py
import os
import platform
import subprocess
import time
from datetime import datetime

from docxtpl import DocxTemplate
from sqlalchemy.orm import Session

from app.core.database import get_session

# Unser neuer Import!
from app.core.document_data import (
    get_company_context,
    get_patient_context,
    get_sessions_context,
)
from app.models.app_setting import AppSetting
from app.models.company_setting import DocumentTemplate
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

            self.output_dir = "./data/generated_docs"
            os.makedirs(self.output_dir, exist_ok=True)

    def generate_document(
        self,
        doc_type: str,
        patient_id: int,
        session_ids: list[int] = None,
        convert_to_pdf: bool = True,
        specific_template_id: int = None,
    ) -> str:
        with get_session() as db_session:
            # 1. Vorlage finden
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
                        .filter_by(doc_type=doc_type, is_active=True)
                        .first()
                    )

            if not tpl_record or not os.path.exists(tpl_record.file_path):
                raise FileNotFoundError(
                    f"Keine aktive Vorlage für '{doc_type}' gefunden."
                )

            # 2. Daten sammeln über unsere NEUE zentrale Logik
            context = {"heute": datetime.now().strftime("%d.%m.%Y")}
            context.update(get_company_context(db_session))

            patient = db_session.query(Patient).filter_by(id=patient_id).first()
            context.update(get_patient_context(patient))

            if session_ids:
                db_sessions = (
                    db_session.query(PatientSession)
                    .filter(PatientSession.id.in_(session_ids))
                    .order_by(PatientSession.date)
                    .all()
                )
                context.update(get_sessions_context(db_sessions))

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
                    return docx_path

            return docx_path

    def _convert_to_pdf(self, docx_path: str) -> str:
        command = "libreoffice"
        if platform.system() == "Darwin":
            command = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

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

        return docx_path.replace(".docx", ".pdf").replace(".odt", ".pdf")

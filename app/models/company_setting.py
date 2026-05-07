# app/models/company_setting.py
from sqlalchemy import Boolean, Column, Integer, String

from app.core.database import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    street = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    city = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)
    # --- VAT ---
    vat_number = Column(String, nullable=True)  # MWSt-Nummer
    # --- PAYMENT TERMS ---
    payment_terms_days = Column(Integer, default=30)
    payment_terms_mode = Column(String, default="Netto")
    # --- BANK DETAILS ---
    bank_name = Column(String, nullable=True)
    iban = Column(String, nullable=True)
    account_number = Column(String, nullable=True)
    bic_swift = Column(String, nullable=True)
    # --- LOGO PATH ---
    logo_path = Column(String, nullable=True)


class DocumentTemplate(Base):
    __tablename__ = "document_templates"

    id = Column(Integer, primary_key=True, index=True)
    doc_type = Column(String, nullable=False)  # z.B. 'Rechnung', 'Quittung', 'Mahnung'
    name = Column(String, nullable=False)  # Originaler Dateiname
    file_path = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

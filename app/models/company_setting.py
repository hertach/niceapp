# app/models/company_setting.py
from sqlalchemy import Column, Integer, String, Boolean
from app.core.database import Base


class CompanyProfile(Base):
    __tablename__ = 'company_profiles'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    street = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    city = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)

    iban = Column(String, nullable=True)
    bank_name = Column(String, nullable=True)

    logo_path = Column(String, nullable=True)


class DocumentTemplate(Base):
    __tablename__ = 'document_templates'

    id = Column(Integer, primary_key=True, index=True)
    doc_type = Column(String, nullable=False)  # z.B. 'Rechnung', 'Quittung', 'Mahnung'
    name = Column(String, nullable=False)  # Originaler Dateiname
    file_path = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
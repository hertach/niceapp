from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class VATSetting(Base):
    __tablename__ = "vat_settings"
    id = Column(Integer, primary_key=True)
    rate = Column(Float, nullable=False)  # z.B. 19.0
    description = Column(String, nullable=False)  # z.B. "Regelsatz"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # Wenn leer, dann aktuell gültig
    is_active = Column(Boolean, default=True)  # Soft-Delete Flag

    sessions = relationship("PatientSession", back_populates="vat_setting")


class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)  # z.B. "Bar", "Karte", "Rechnung"
    account_id = Column(Integer, ForeignKey("accounting_accounts.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    account = relationship("Account", back_populates="payment_method")
    sessions = relationship("PatientSession", back_populates="payment_method")

class InvoiceFormatSetting(Base):
    __tablename__ = "invoice_format_settings"
    id = Column(Integer, primary_key=True)
    prefix = Column(String, default="RE-", nullable=False) # z.B. "RE-" oder "INV-"
    include_year = Column(Boolean, default=True)           # Soll das Jahr rein? (z.B. 2026)
    padding = Column(Integer, default=3)

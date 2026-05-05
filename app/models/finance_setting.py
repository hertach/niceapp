from sqlalchemy import Column, Integer, String, Float, Date, Boolean, ForeignKey
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
    is_active = Column(Boolean, default=True)

    sessions = relationship("PatientSession", back_populates="payment_method")
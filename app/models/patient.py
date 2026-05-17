# app/models/patient.py
import enum
from sqlalchemy import Boolean, Column, Date, Float, ForeignKey, Integer, String, Text, Enum
from sqlalchemy.orm import relationship

from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    birthdate = Column(Date, nullable=True)
    gender = Column(String(20), nullable=True)  # <-- NEU: Geschlecht
    notes = Column(Text, nullable=True)

    # ── 1:n Beziehungen ──
    addresses = relationship(
        "PatientAddress", back_populates="patient", cascade="all, delete-orphan"
    )
    emails = relationship(
        "PatientEmail", back_populates="patient", cascade="all, delete-orphan"
    )
    phones = relationship(
        "PatientPhone", back_populates="patient", cascade="all, delete-orphan"
    )
    insurances = relationship(
        "PatientInsurance", back_populates="patient", cascade="all, delete-orphan"
    )  # <-- NEU
    sessions = relationship(
        "PatientSession", back_populates="patient", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Patient {self.full_name}>"


class PatientAddress(Base):
    __tablename__ = "patient_addresses"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    street = Column(String(200))
    zip_code = Column(String(20))
    city = Column(String(100))
    is_main = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)  # Soft-Delete

    patient = relationship("Patient", back_populates="addresses")


class PatientEmail(Base):
    __tablename__ = "patient_emails"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    email = Column(String(255))
    type = Column(String(50))
    is_main = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)  # Soft-Delete

    patient = relationship("Patient", back_populates="emails")


class PatientPhone(Base):
    __tablename__ = "patient_phones"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    number = Column(String(50))
    type = Column(String(50))  # z.B. "Mobil", "Privat", "Geschäftlich"
    is_main = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)  # Soft-Delete

    patient = relationship("Patient", back_populates="phones")


class PatientInsurance(Base):
    __tablename__ = "patient_insurances"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    name = Column(String(200), nullable=False)  # Name der Krankenkasse
    insurance_number = Column(String(100))  # Versichertennummer
    is_deleted = Column(Boolean, default=False)  # True = Alte Versicherung (Historie)

    patient = relationship("Patient", back_populates="insurances")

# 1. Definieren des Status-Enums
class SessionStatus(str, enum.Enum):
    OPEN = "Offen"
    COMPLETED = "Abgeschlossen"
    INVOICED = "Verrechnet"
    PAID = "Bezahlt"
    CANCELLED = "Storniert"

class PatientSession(Base):
    __tablename__ = "patient_sessions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    date = Column(Date, nullable=False)
    time_from = Column(String(5))  # Format: "HH:MM"
    time_to = Column(String(5))  # Format: "HH:MM"

    issue = Column(Text)  # Anliegen
    approach = Column(Text)  # Lösungsansatz
    protocol = Column(Text)  # Protokoll

    booking_text = Column(String(255), nullable=True)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    vat_id = Column(Integer, ForeignKey("vat_settings.id"), nullable=True)
    amount = Column(Float, default=0.0)

    invoice_number = Column(String(50), nullable=True)
    invoice_version = Column(Integer, default=0)
    cancellation_reason = Column(String(255), nullable=True)
    is_deleted = Column(Boolean, default=False)  # Für Soft-Delete

    status = Column(Enum(SessionStatus), default=SessionStatus.OPEN, server_default="Offen", nullable=False)
    parent_id = Column(Integer, ForeignKey("patient_sessions.id"), nullable=True)
    original_session = relationship("PatientSession", remote_side=[id], backref="clones")

    patient = relationship("Patient", back_populates="sessions")
    payment_method = relationship("PaymentMethod", back_populates="sessions")
    vat_setting = relationship("VATSetting", back_populates="sessions")
    user = relationship("User")

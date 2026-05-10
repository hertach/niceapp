# app/models/accounting.py
from datetime import date, datetime
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class FiscalYear(Base):
    """Verwaltet die Geschäftsjahre."""
    __tablename__ = "accounting_fiscal_years"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)  # z.B. "2026"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_closed = Column(Boolean, default=False)  # True = Jahr ist abgeschlossen, keine Buchungen mehr möglich

    entries = relationship("JournalEntry", back_populates="fiscal_year")

    def __repr__(self) -> str:
        return f"<FiscalYear {self.name}>"


class Account(Base):
    """Das eigentliche Konto im Kontenplan (nach Schweizer KMU)."""
    __tablename__ = "accounting_accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(Integer, nullable=False, unique=True)  # z.B. 1000, 1100, 3000
    name = Column(String(100), nullable=False)  # z.B. "Kasse", "Honorarertrag"

    # Kategorisierung für die Bilanz / ER
    account_class = Column(Integer, nullable=False)  # 1=Aktiven, 2=Passiven, 3=Betriebsertrag, etc.
    account_group = Column(Integer, nullable=False)  # z.B. 10=Flüssige Mittel

    is_active = Column(Boolean, default=True)

    lines = relationship("JournalEntryLine", back_populates="account")
    payment_method = relationship("PaymentMethod", back_populates="account")
    def __repr__(self) -> str:
        return f"<Account {self.account_number} - {self.name}>"


class JournalEntry(Base):
    """Der Buchungssatz (Kopfzeile)."""
    __tablename__ = "accounting_journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    fiscal_year_id = Column(Integer, ForeignKey("accounting_fiscal_years.id"), nullable=False)

    patient_session_id = Column(Integer, ForeignKey("patient_sessions.id"), nullable=True)
    date = Column(Date, nullable=False, default=date.today)
    description = Column(String(255), nullable=False)  # Buchungstext, z.B. "Rechnung Meier"
    reference = Column(String(100), nullable=True)  # Belegnummer, z.B. "RE-2026-001"

    created_at = Column(DateTime, default=datetime.utcnow)

    fiscal_year = relationship("FiscalYear", back_populates="entries")
    lines = relationship("JournalEntryLine", back_populates="journal_entry", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<JournalEntry {self.date} - {self.description}>"


class JournalEntryLine(Base):
    """Die Buchungszeilen (Soll und Haben)."""
    __tablename__ = "accounting_journal_lines"

    id = Column(Integer, primary_key=True, index=True)
    journal_entry_id = Column(Integer, ForeignKey("accounting_journal_entries.id"), nullable=False)
    account_id = Column(Integer, ForeignKey("accounting_accounts.id"), nullable=False)

    # Beträge (Entweder steht im Soll ein Wert oder im Haben)
    debit = Column(Float, default=0.0)  # Soll
    credit = Column(Float, default=0.0)  # Haben

    journal_entry = relationship("JournalEntry", back_populates="lines")
    account = relationship("Account", back_populates="lines")

    def __repr__(self) -> str:
        return f"<JournalEntryLine Acc:{self.account_id} S:{self.debit} H:{self.credit}>"
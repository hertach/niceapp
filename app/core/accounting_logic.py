# app/core/accounting_logic.py
from sqlalchemy.orm import Session
from datetime import date
from app.models.accounting import FiscalYear, Account, JournalEntry, JournalEntryLine
from app.models.patient import PatientSession


def book_patient_session(db: Session, session_id: int):
    """Bucht oder aktualisiert eine Sitzung in der Buchhaltung."""
    p_session = db.query(PatientSession).get(session_id)
    if not p_session or p_session.amount <= 0:
        return

    # 1. Prüfen, ob bereits ein Buchungssatz für DIESE Sitzung existiert
    entry = db.query(JournalEntry).filter_by(patient_session_id=session_id).first()

    # 2. Konten und Jahr ermitteln
    year_name = str(p_session.date.year)
    fiscal_year = db.query(FiscalYear).filter_by(name=year_name).first()
    if not fiscal_year: raise ValueError(f"Jahr {year_name} fehlt.")

    account_ertrag = db.query(Account).filter_by(account_number=3000).first()
    soll_konto_nr = 1020 if p_session.is_paid else 1100
    account_soll = db.query(Account).filter_by(account_number=soll_konto_nr).first()

    buchungstext = p_session.booking_text or f"Sitzung {p_session.patient.full_name}"

    if entry:
        # UPDATE: Bestehenden Kopf aktualisieren
        entry.description = buchungstext[:255]
        entry.date = p_session.date
        entry.fiscal_year_id = fiscal_year.id
        # Bestehende Zeilen löschen, um sie neu aufzubauen (sauberster Weg)
        for line in entry.lines:
            db.delete(line)
    else:
        # CREATE: Neuen Kopf erstellen
        entry = JournalEntry(
            patient_session_id=session_id,
            fiscal_year_id=fiscal_year.id,
            date=p_session.date,
            description=buchungstext[:255],
            reference=f"SITZUNG-{session_id}"
        )
        db.add(entry)

    db.flush()  # ID sichern

    # 3. Neue Buchungszeilen hinzufügen
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=account_soll.id, debit=p_session.amount))
    db.add(JournalEntryLine(journal_entry_id=entry.id, account_id=account_ertrag.id, credit=p_session.amount))
    db.commit()
    print(f"BUCHHALTUNG: Erfolgreich gebucht - {buchungstext} ({p_session.amount} CHF)")
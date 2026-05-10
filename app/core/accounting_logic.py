# app/core/accounting_logic.py
from sqlalchemy.orm import Session

from app.core.logger import app_logger
from app.models.accounting import Account, FiscalYear, JournalEntry, JournalEntryLine
from app.models.patient import PatientSession


def book_patient_session(db: Session, session_id: int):
    """Bucht eine Sitzung in die Buchhaltung (Rechnung und ggf. Zahlung)."""
    p_session = db.query(PatientSession).filter_by(id=session_id).first()
    if not p_session or p_session.amount <= 0:
        return

    # 1. Geschäftsjahr prüfen
    year_name = str(p_session.date.year)
    fiscal_year = db.query(FiscalYear).filter_by(name=year_name).first()
    if not fiscal_year or fiscal_year.is_closed:
        raise ValueError(f"Geschäftsjahr {year_name} fehlt oder ist abgeschlossen.")

    # 2. Konten laden (Ertrag, Debitoren und das Zahlungskonto)
    account_ertrag = db.query(Account).filter_by(account_number=3000).first()
    account_debitoren = db.query(Account).filter_by(account_number=1100).first()

    # HINWEIS: Für den Moment buchen wir alles Bezahle auf 1020 (Bank).
    # Sobald wir die Zahlarten (Twint, Sumup, Bar) verwalten, können wir hier
    # pro Zahlart ein eigenes Konto (z.B. 1000 für Kasse) ansteuern!
    if p_session.payment_method and p_session.payment_method.account_id:
        account_zahlung = p_session.payment_method.account
    else:
        # Fallback: Wenn kein Konto bei der Zahlart hinterlegt ist, buchen wir auf 1020 Bank
        account_zahlung = db.query(Account).filter_by(account_number=1020).first()
        app_logger.warning(
            f"Kein Konto für Zahlart {p_session.payment_method.title} definiert. Nutze Fallback 1020."
        )

    if not all([account_ertrag, account_debitoren, account_zahlung]):
        raise ValueError(
            "Es fehlen Standardkonten (3000, 1100 oder 1020) im Kontenplan."
        )

    buchungstext = p_session.booking_text or f"Sitzung {p_session.patient.full_name}"

    # --- SCHRITT A: IMMER DIE RECHNUNG BUCHEN (1100 an 3000) ---
    # Wir hängen ein "-RE" (für Rechnung) an die Reference, um sie von der Zahlung zu unterscheiden
    entry_rechnung = (
        db.query(JournalEntry)
        .filter_by(patient_session_id=session_id, reference=f"SITZUNG-{session_id}-RE")
        .first()
    )

    if entry_rechnung:
        entry_rechnung.description = buchungstext[:255]
        entry_rechnung.date = p_session.date
        for line in entry_rechnung.lines:
            db.delete(line)
    else:
        entry_rechnung = JournalEntry(
            patient_session_id=session_id,
            fiscal_year_id=fiscal_year.id,
            date=p_session.date,
            description=buchungstext[:255],
            reference=f"SITZUNG-{session_id}-RE",
        )
        db.add(entry_rechnung)

    db.flush()  # ID für die Zeilen generieren

    db.add(
        JournalEntryLine(
            journal_entry_id=entry_rechnung.id,
            account_id=account_debitoren.id,
            debit=p_session.amount,
        )
    )
    db.add(
        JournalEntryLine(
            journal_entry_id=entry_rechnung.id,
            account_id=account_ertrag.id,
            credit=p_session.amount,
        )
    )

    # --- SCHRITT B: DIE ZAHLUNG BUCHEN (1020 an 1100) - NUR WENN BEZAHLT ---
    # Wir hängen ein "-ZA" (für Zahlung) an
    entry_zahlung = (
        db.query(JournalEntry)
        .filter_by(patient_session_id=session_id, reference=f"SITZUNG-{session_id}-ZA")
        .first()
    )

    if p_session.is_paid:
        zahlungs_text = f"Zahlung: {buchungstext}"
        if entry_zahlung:
            entry_zahlung.description = zahlungs_text[:255]
            entry_zahlung.date = (
                p_session.date
            )  # Zahlung erfolgt vorerst am gleichen Tag wie Sitzung
            for line in entry_zahlung.lines:
                db.delete(line)
        else:
            entry_zahlung = JournalEntry(
                patient_session_id=session_id,
                fiscal_year_id=fiscal_year.id,
                date=p_session.date,
                description=zahlungs_text[:255],
                reference=f"SITZUNG-{session_id}-ZA",
            )
            db.add(entry_zahlung)

        db.flush()

        # Die Zahlung gleicht den Debitoren (1100) im Haben aus
        db.add(
            JournalEntryLine(
                journal_entry_id=entry_zahlung.id,
                account_id=account_zahlung.id,
                debit=p_session.amount,
            )
        )
        db.add(
            JournalEntryLine(
                journal_entry_id=entry_zahlung.id,
                account_id=account_debitoren.id,
                credit=p_session.amount,
            )
        )
    else:
        # Falls du den "Bereits bezahlt"-Haken bei einer Bearbeitung entfernst,
        # löschen wir die zugehörige Zahlungsbuchung automatisch!
        if entry_zahlung:
            db.delete(entry_zahlung)

    db.commit()

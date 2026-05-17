# app/core/accounting_logic.py
from datetime import date

from sqlalchemy.orm import Session

from app.core.logger import app_logger
from app.models.accounting import Account, FiscalYear, JournalEntry, JournalEntryLine
from app.models.finance_setting import InvoiceFormatSetting
from app.models.patient import PatientSession, SessionStatus


# ══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

def generate_invoice_number(db: Session, year: int) -> str:
    """
    Generiert die nächste Rechnungsnummer basierend auf den Format-Einstellungen.
    Format-Standard: RE-{YEAR}-{NNN}  → z.B. RE-2026-001
    Versionierte Wiederöffnungen (.1, .2 …) werden vom Aufrufer gesetzt.
    BUGFIX: db.flush() nach der Zuweisung im Aufrufer sicherstellt, dass
    bei Batch-Operationen jede Nummer eindeutig bleibt.
    """
    fmt          = db.query(InvoiceFormatSetting).first()
    prefix_base  = (fmt.prefix       if fmt else "RE-")
    include_year = (fmt.include_year if fmt else True)
    padding      = (fmt.padding      if fmt and fmt.padding else 3)

    prefix = f"{prefix_base}{year}-" if include_year else prefix_base

    existing = (
        db.query(PatientSession.invoice_number)
        .filter(PatientSession.invoice_number.like(f"{prefix}%"))
        .all()
    )

    max_num = 0
    for (inv_num,) in existing:
        if inv_num:
            base = inv_num.split(".")[0]   # ".x"-Versionssuffix ignorieren
            try:
                max_num = max(max_num, int(base.replace(prefix, "")))
            except ValueError:
                pass

    return f"{prefix}{max_num + 1:0{padding}d}"


def _load_standard_accounts(db: Session, payment_method=None):
    """Lädt die benötigten Standardkonten aus der Datenbank."""
    account_ertrag    = db.query(Account).filter_by(account_number=3000).first()
    account_debitoren = db.query(Account).filter_by(account_number=1100).first()

    if payment_method and payment_method.account_id:
        account_zahlung = payment_method.account
    else:
        account_zahlung = db.query(Account).filter_by(account_number=1020).first()
        if payment_method:
            app_logger.warning(
                f"Kein Konto für Zahlart «{payment_method.title}» definiert. Fallback 1020."
            )

    if not all([account_ertrag, account_debitoren, account_zahlung]):
        raise ValueError("Standardkonten (3000, 1100 oder 1020) fehlen im Kontenplan.")

    return account_ertrag, account_debitoren, account_zahlung


# ══════════════════════════════════════════════════════════════════════════════
# HAUPTFUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

def book_patient_session(db: Session, session_id: int) -> None:
    """
    Erstellt / aktualisiert Buchungssätze für eine Sitzung.

    Logik nach Status:
      OPEN / COMPLETED   → keine Buchung (Sitzung noch nicht abgerechnet)
      INVOICED           → Buchung: 1100 Debitoren AN 3000 Honorarertrag
      PAID               → obige Buchung  PLUS  Bank/Kassa AN 1100 Debitoren
      CANCELLED          → wird von cancel_patient_session() behandelt
    """
    p = db.query(PatientSession).filter_by(id=session_id).first()
    if not p or p.amount <= 0:
        return

    if p.status not in (SessionStatus.INVOICED, SessionStatus.PAID):
        return   # Keine Buchung nötig für offene / abgeschlossene Sitzungen

    # Geschäftsjahr prüfen
    year_name   = str(p.date.year)
    fiscal_year = db.query(FiscalYear).filter_by(name=year_name).first()
    if not fiscal_year or fiscal_year.is_closed:
        raise ValueError(f"Geschäftsjahr {year_name} fehlt oder ist abgeschlossen.")

    account_ertrag, account_debitoren, account_zahlung = _load_standard_accounts(
        db, p.payment_method
    )

    buchungstext = p.booking_text or f"Sitzung {p.patient.full_name}"

    # ── SCHRITT A: RECHNUNG  (1100 Debitoren AN 3000 Ertrag) ──────────────
    ref_re = f"SITZUNG-{session_id}-RE"
    entry_re = db.query(JournalEntry).filter_by(
        patient_session_id=session_id, reference=ref_re
    ).first()

    if entry_re:
        entry_re.description = buchungstext[:255]
        entry_re.date        = p.date
        for line in entry_re.lines:
            db.delete(line)
    else:
        entry_re = JournalEntry(
            patient_session_id=session_id,
            fiscal_year_id=fiscal_year.id,
            date=p.date,
            description=buchungstext[:255],
            reference=ref_re,
        )
        db.add(entry_re)

    db.flush()
    db.add(JournalEntryLine(journal_entry_id=entry_re.id, account_id=account_debitoren.id, debit=p.amount))
    db.add(JournalEntryLine(journal_entry_id=entry_re.id, account_id=account_ertrag.id,    credit=p.amount))

    # ── SCHRITT B: ZAHLUNG  (Bank/Kassa AN 1100 Debitoren) — nur wenn PAID ──
    ref_za   = f"SITZUNG-{session_id}-ZA"
    entry_za = db.query(JournalEntry).filter_by(
        patient_session_id=session_id, reference=ref_za
    ).first()

    if p.status == SessionStatus.PAID:
        zahlungs_text = f"Zahlung: {buchungstext}"
        if entry_za:
            entry_za.description = zahlungs_text[:255]
            entry_za.date        = p.date
            for line in entry_za.lines:
                db.delete(line)
        else:
            entry_za = JournalEntry(
                patient_session_id=session_id,
                fiscal_year_id=fiscal_year.id,
                date=p.date,
                description=zahlungs_text[:255],
                reference=ref_za,
            )
            db.add(entry_za)

        db.flush()
        db.add(JournalEntryLine(journal_entry_id=entry_za.id, account_id=account_zahlung.id,  debit=p.amount))
        db.add(JournalEntryLine(journal_entry_id=entry_za.id, account_id=account_debitoren.id, credit=p.amount))
    else:
        # Status wechselte zurück zu INVOICED → Zahlungsbuchung entfernen
        if entry_za:
            db.delete(entry_za)

    db.commit()


def cancel_patient_session(db: Session, session_id: int, reason: str) -> PatientSession:
    """
    Vollständige Stornierung einer Sitzung in drei Schritten:

    1. Gegenbuchungen (Stornorechnung): Alle JournalEntries der Original-Sitzung
       werden mit vertauschten Soll/Haben-Werten neu eingebucht.
    2. Original: Status → CANCELLED, Stornierungsgrund wird gespeichert.
    3. Klon: Eine neue Sitzung mit allen medizinischen Daten des Originals
       wird mit Status COMPLETED angelegt (parent_id verweist auf Original).
       So bleiben die klinischen Informationen für eine Korrektur sofort verfügbar.

    Returns:
        Die neu erstellte Klon-Sitzung (für direktes Weiterarbeiten).
    """
    original = db.query(PatientSession).filter_by(id=session_id).with_for_update().first()
    if not original:
        raise ValueError(f"Sitzung {session_id} nicht gefunden.")
    if original.status == SessionStatus.CANCELLED:
        raise ValueError(f"Sitzung {session_id} ist bereits storniert.")

    try:
        # ── 1. GEGENBUCHUNGEN (Stornorechnung) ──────────────────────────────
        existing_entries = db.query(JournalEntry).filter_by(
            patient_session_id=original.id
        ).all()

        storno_ref_prefix = f"STORNO-{original.invoice_number or session_id}"

        for entry in existing_entries:
            storno_ref = f"STORNO-{entry.reference}"

            # Dubletten-Schutz: existiert diese Storno-Buchung schon?
            if db.query(JournalEntry).filter_by(reference=storno_ref).first():
                continue

            storno_entry = JournalEntry(
                patient_session_id=original.id,
                fiscal_year_id=entry.fiscal_year_id,
                date=date.today(),
                description=f"Storno: {entry.description} (Grund: {reason})",
                reference=storno_ref,
            )
            db.add(storno_entry)
            db.flush()

            for line in entry.lines:
                # Soll und Haben werden getauscht → Gegenbuchung
                db.add(JournalEntryLine(
                    journal_entry_id=storno_entry.id,
                    account_id=line.account_id,
                    debit=line.credit,   # ← getauscht
                    credit=line.debit,   # ← getauscht
                ))

        # ── 2. ORIGINAL ALS STORNIERT MARKIEREN ────────────────────────────
        original.status               = SessionStatus.CANCELLED
        original.cancellation_reason  = reason
        # is_invoiced bleibt über den Status erhalten; wir setzen keine
        # separaten Boolean-Felder mehr, da das Model nur noch `status` kennt.

        # ── 3. KLON MIT MEDIZINISCHEN DATEN ERSTELLEN ──────────────────────
        klon = PatientSession(
            patient_id         = original.patient_id,
            user_id            = original.user_id,
            date               = original.date,
            time_from          = original.time_from,
            time_to            = original.time_to,
            issue              = original.issue,
            approach           = original.approach,
            protocol           = original.protocol,
            booking_text       = original.booking_text,
            payment_method_id  = original.payment_method_id,
            vat_id             = original.vat_id,
            amount             = original.amount,
            parent_id          = original.id,      # ← Verknüpfung zum Original
            status             = SessionStatus.COMPLETED,
            invoice_number     = None,             # ← Klon braucht neue Nummer
            invoice_version    = 0,
        )
        db.add(klon)
        db.flush()

        db.commit()
        db.refresh(klon)
        app_logger.info(
            f"Sitzung {session_id} storniert. Klon-ID: {klon.id}. Grund: {reason}"
        )
        return klon

    except Exception as e:
        db.rollback()
        app_logger.error(f"Fehler beim Stornieren der Sitzung {session_id}: {e}")
        raise
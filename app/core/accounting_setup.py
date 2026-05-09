# app/core/accounting_setup.py
from sqlalchemy.orm import Session
from app.models.accounting import Account, FiscalYear
from app.core.logger import app_logger
from datetime import date


def seed_accounting_basics(db: Session):
    # 1. Geschäftsjahr initialisieren (falls keines existiert)
    current_year_name = str(date.today().year)
    year_exists = db.query(FiscalYear).filter_by(name=current_year_name).first()
    if not year_exists:
        new_year = FiscalYear(
            name=current_year_name,
            start_date=date(date.today().year, 1, 1),
            end_date=date(date.today().year, 12, 31)
        )
        db.add(new_year)
        app_logger.info(f"Geschäftsjahr {current_year_name} angelegt.")

    # 2. Schweizer KMU Kontenplan (Auszug der wichtigsten Konten)
    # Format: (Nummer, Name, Klasse, Gruppe)
    kmu_accounts = [
        # KLASSE 1: AKTIVEN
        (1000, "Kasse", 1, 10),
        (1020, "Bankguthaben", 1, 10),
        (1100, "Forderungen aus Lieferungen und Leistungen (Debitoren)", 1, 11),
        (1170, "Vorsteuer MWST auf Material und Dienstleistungen", 1, 11),
        (1171, "Vorsteuer MWST auf Investitionen und übrigem Betriebsaufwand", 1, 11),
        (1500, "Maschinen und Apparate", 1, 15),

        # KLASSE 2: PASSIVEN
        (2000, "Verbindlichkeiten aus Lieferungen und Leistungen (Kreditoren)", 2, 20),
        (2200, "Geschuldete Mehrwertsteuer (Umsatzsteuer)", 2, 22),
        (2270, "Sozialversicherungen", 2, 22),
        (2400, "Bankverbindlichkeiten (Darlehen)", 2, 24),
        (2800, "Eigenkapital", 2, 28),

        # KLASSE 3: BETRIEBSERTRAG
        (3000, "Dienstleistungsertrag / Honorare", 3, 30),
        (3400, "Handelserträge", 3, 34),
        (3805, "Verluste aus Forderungen (Erlösminderungen)", 3, 38),

        # KLASSE 4: AUFWAND FÜR MATERIAL, WAREN, DIENSTLEISTUNGEN
        (4000, "Materialaufwand", 4, 40),
        (4400, "Einkauf von Dienstleistungen", 4, 44),

        # KLASSE 5: PERSONALAUFWAND
        (5000, "Lohnaufwand", 5, 50),
        (5700, "Sozialversicherungsaufwand", 5, 57),

        # KLASSE 6: ÜBRIGER BETRIEBLICHER AUFWAND
        (6000, "Raumaufwand (Miete)", 6, 60),
        (6200, "Reparaturen und Unterhalt", 6, 62),
        (6500, "Verwaltungsaufwand", 6, 65),
        (6600, "Werbeaufwand", 6, 66),
        (6800, "Abschreibungen", 6, 68),
        (6900, "Finanzaufwand (Bankspesen/Zinsen)", 6, 69),
    ]

    for num, name, a_class, a_group in kmu_accounts:
        exists = db.query(Account).filter_by(account_number=num).first()
        if not exists:
            new_acc = Account(
                account_number=num,
                name=name,
                account_class=a_class,
                account_group=a_group
            )
            db.add(new_acc)

    db.commit()
    app_logger.info("Schweizer KMU-Kontenplan erfolgreich initialisiert.")
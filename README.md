# NiceApp

Eine modulare Single-Page-Application (SPA) gebaut mit **NiceGUI 2.x**, **SQLAlchemy 2.0** und **Python 3.13**. Aktuell im Aufbau als Therapeuten-Praxisverwaltung (Patienten, Termine, Sitzungsprotokolle, Rechnungen).

---

## Tech-Stack

| Komponente | Technologie |
|---|---|
| UI Framework | NiceGUI 2.x |
| ORM | SQLAlchemy 2.0 |
| Datenbank | SQLite |
| Migrationen | Alembic |
| Passwort-Hashing | bcrypt |
| Package Manager | uv |
| Konfiguration | python-dotenv |

---

## Projektstruktur

```
NiceApp/
├── main.py                          # Einstiegspunkt (immer vom Root starten)
├── alembic.ini                      # Alembic-Konfiguration
├── .env                             # Umgebungsvariablen (nicht ins Git)
├── migrations/
│   ├── env.py                       # Alembic-Umgebung (lädt alle Models automatisch)
│   ├── script.py.mako               # Template für neue Migrationen
│   └── versions/                    # Generierte Migrationsdateien
├── app/
│   ├── main.py                      # ui.run() + Routen + SPA-Navigation
│   ├── config.py                    # Zentrale Konfiguration via .env
│   ├── core/
│   │   ├── database.py              # Engine, Base, get_session(), init_db()
│   │   └── auth.py                  # hash_password, verify_password, authenticate_user, check_access()
│   ├── models/
│   │   ├── user.py
│   │   ├── role.py
│   │   ├── menu_item.py
│   │   ├── patient.py
│   │   ├── appointment.py
│   │   ├── session_note.py
│   │   └── invoice.py               # Invoice + InvoiceItem
│   ├── components/
│   │   └── layout.py                # main_layout(), Header, Sidebar, Nav-Items
│   ├── pages/
│   │   ├── login.py
│   │   ├── dashboard.py
│   │   ├── patients.py
│   │   └── admin/
│   │       ├── users.py
│   │       ├── roles.py
│   │       └── menu_items.py
│   └── static/
│       ├── style.css
│       └── icons/
│           ├── logo.png
│           └── favicon.ico
└── data/
    └── app.db
```

---

## Installation & Start

```bash
# 1. Abhängigkeiten installieren
uv sync

# 2. .env anlegen (siehe .env.example)
cp .env.example .env

# 3. Datenbank initialisieren & Migrationen anwenden
alembic upgrade head

# 4. App starten
uv run python main.py
```

---

## Konfiguration (.env)

```env
APP_TITLE=NiceApp
APP_LOGO=app/static/icons/logo.png
STORAGE_SECRET=dein-geheimer-schluessel
DB_PATH=data/app.db
PORT=8080
RELOAD=false
```

> `STORAGE_SECRET` muss in Produktion durch einen sicheren Zufallswert ersetzt werden.

---

## Datenbank & Migrationen (Alembic)

Alembic ist für alle Schemaänderungen zuständig. `init_db()` erstellt nur noch Seed-Daten – keine Tabellen mehr via `create_all()` in Produktion.

```bash
# Neue Migration aus Modeländerungen generieren
alembic revision --autogenerate -m "beschreibung der aenderung"

# Migration anwenden
alembic upgrade head

# Einen Schritt zurück
alembic downgrade -1

# Aktuellen Stand anzeigen
alembic current
```

**Wichtig für SQLite:** `render_as_batch=True` ist in `migrations/env.py` gesetzt. SQLite unterstützt kein natives `ALTER TABLE RENAME COLUMN` – Alembic baut die Tabelle in diesem Fall transparent neu.

Der Model-Autoloader in `env.py` scannt `app/models/` automatisch. Neue Models müssen **nicht** manuell in `env.py` eingetragen werden.

---

## SPA-Architektur

Die App verwendet eine einzige `@ui.page('/')` – kein Browser-Reload beim Navigieren.

```python
# Seite registrieren
@page('/meine-seite')
def _meine_seite() -> None:
    meine_page_funktion()

# Navigation
navigate('/meine-seite')  # löscht Content-Bereich und rendert neue Seite
```

Seiten werden in `PAGES: dict[str, Callable]` registriert. `navigate()` übernimmt Content-Clearing, aktiven Nav-Item-Wechsel und Zugriffscheck via `check_access()`.

---

## Auth & Zugriffssteuerung

- Login via bcrypt-Passwort-Hashing
- Session in `app.storage.user` (`authenticated`, `username`, `role`)
- `check_access(path)` prüft anhand der `menu_items`-Tabelle ob die aktuelle Rolle Zugriff hat
- Routen ohne DB-Eintrag sind für alle gesperrt (Sicherheits-Fallback)

---

## Datenmodell

```
User           → Login, Rolle, aktiv/inaktiv
Role           → Rollenname, Beschreibung
MenuItem       → Label, Icon, Pfad, Rollen (kommagetrennt), Sortierung

Patient        → Personalien, Kontakt, Adresse, Versicherung, Notizen
Appointment    → Patient, Therapeut, Start/Ende, Typ, Status
SessionNote    → Termin, Inhalt, nächste Schritte
Invoice        → Patient, Rechnungsnummer, Datum, Status, Währung, MwSt
InvoiceItem    → Rechnung, Beschreibung, Menge, Einzelpreis
```

**MwSt Schweiz:** Psychotherapeutische Leistungen sind nach Art. 21 MWSTG mehrwertsteuerbefreit → `vat_rate` defaultmässig `0.0`.

---

## Admin-Bereich

Erreichbar für Benutzer mit Rolle `admin`:

| Seite | Pfad |
|---|---|
| Benutzerverwaltung | `/admin/users` |
| Rollenverwaltung | `/admin/roles` |
| Menüverwaltung | `/admin/menu` |

---

## Bekannte Lösungen für häufige Probleme

| Problem | Lösung |
|---|---|
| `ModuleNotFoundError: app` | `main.py` im Root starten, nicht aus `app/` |
| Zirkulärer Import bei Models | Models erst in `init_db()` lokal importieren |
| `no such column` nach Modeländerung | `alembic revision --autogenerate` + `upgrade head` |
| AG Grid leer in SPA | `ui.table` verwenden statt AG Grid |
| `app.storage.user` Fehler | `storage_secret` in `ui.run()` setzen |
| CSS auf Drawer wirkt nicht | `.q-drawer__content` mit `!important` in `style.css` |
| SQLite ALTER TABLE schlägt fehl | `render_as_batch=True` in `migrations/env.py` |
| `NameError: open_dialog` | Funktionen vor dem Button/Table definieren |

---

## Entwicklungs-Workflow
Datei unter app/models/ erstellen
```bash
# Nach jeder Modeländerung
alembic revision --autogenerate -m "was geaendert wurde"
alembic upgrade head

# App im Dev-Modus (RELOAD=true in .env)
uv run python main.py
```
## 📝 Logging System

Die Applikation verfügt über ein professionelles, in das Frontend integriertes Logging-System. Um die Performance und Wartbarkeit der Anwendung zu optimieren, werden die Logs physisch von der Hauptdatenbank getrennt.

### ✨ Features
* **Isolierte Datenbank (`data/log.db`):** System-Logs werden in einer eigenen SQLite-Datenbank gespeichert. Das verhindert Database-Locking bei Schreiboperationen in der Hauptdatenbank (`app.db`) und hält regelmäßige Backups der Nutzerdaten schlank.
* **Wartungsfrei (Kein Alembic):** Die Log-Datenbank nutzt eine eigenständige SQLAlchemy-Engine. Sie wird beim App-Start automatisch erstellt und benötigt keine Alembic-Migrationen.
* **Admin-Dashboard:** Ein integrierter Tab in den Einstellungen ermöglicht das Filtern der Logs nach Level (`INFO`, `WARNING`, `ERROR`) sowie eine Volltextsuche in Echtzeit über die NiceGUI-Oberfläche.

### 🚀 Verwendung im Code
Der globale Logger fängt standardmäßig alle wichtigen Ereignisse ab und speichert sie sowohl in der Datenbank als auch im Konsolen-Output.
```python
from app.core.logger import app_logger

# Beispiele für Log-Einträge
app_logger.info("Anwendung erfolgreich gestartet.")
app_logger.warning("Unbekannter Login-Versuch.")
app_logger.error("Datenbankverbindung fehlgeschlagen!")
---

## Roadmap

- [x] Auth & Session
- [x] Rollenbasiertes Menü aus DB
- [x] SPA-Navigation (kein Browser-Reload)
- [x] Admin: Benutzer, Rollen, Menüpunkte
- [x] Dashboard mit Statistik-Karten
- [x] .env Konfiguration
- [x] Alembic Migrationen
- [x] Patientenverwaltung (CRUD)
- [ ] Terminkalender
- [ ] Sitzungsprotokolle
- [ ] Rechnungen & PDF-Export
- [ ] AI-gestützte Gesprächsführung
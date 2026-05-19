# app/config.py
import os
from pathlib import Path

from dotenv import load_dotenv

# .env im Root laden (funktioniert unabhängig vom CWD)
load_dotenv(Path(__file__).parent.parent / ".env")

APP_TITLE = os.getenv("APP_TITLE", "NiceApp")
APP_LOGO = os.getenv("APP_LOGO", "app/static/icons/logo.png")
STORAGE_SECRET = os.getenv("STORAGE_SECRET", "fallback-secret-change-me")
DB_PATH = os.getenv("DB_PATH", "data/app.db")
LOG_PATH = os.getenv("LOG_PATH", "data/log.db")
PORT = int(os.getenv("PORT", "8080"))
RELOAD = os.getenv("RELOAD", "false").lower() == "true"

ENCRYPTION_MASTER_KEY = os.getenv("ENCRYPTION_MASTER_KEY", "")
PATIENT_STORAGE_PATH = os.getenv("PATIENT_STORAGE_PATH", "./data/patients")

GERMAN_LOCALE = {
    "days": [
        "Sonntag",
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
    ],
    "daysShort": ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"],
    "months": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
    "monthsShort": [
        "Jan",
        "Feb",
        "Mär",
        "Apr",
        "Mai",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Okt",
        "Nov",
        "Dez",
    ],
    "firstDayOfWeek": 1,
}

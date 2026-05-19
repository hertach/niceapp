# app/core/download_tokens.py
"""
Kurzlebige In-Memory-Tokens für sichere Datei-Downloads.

Problem: NiceGUI's nicegui_app.storage.user ist aus FastAPI-Endpunkten heraus
nicht zugreifbar (NiceGUI-interne Abstraktion). Deshalb generiert der NiceGUI-Code
einen Token, der 30 Sekunden gültig und Single-Use ist.

Ablauf:
  1. NiceGUI-UI-Code:  token = create_download_token(file_uuid, user_id)
  2. NiceGUI-UI-Code:  ui.navigate.to(f"/files/download/{file_uuid}?token={token}", new_tab=True)
  3. FastAPI-Endpunkt: entry = consume_token(token)  → validiert & löscht sofort
"""

import time
import uuid
from threading import Lock

_store: dict[str, dict] = {}
_lock = Lock()

TOKEN_TTL = 30  # Sekunden — kurz genug um Missbrauch zu erschweren


def create_download_token(file_uuid: str, user_id: int) -> str:
    """
    Erzeugt einen neuen Single-Use-Token für einen bestimmten file_uuid + user_id.
    Bereinigt dabei automatisch abgelaufene Tokens (kein Memory-Leak).
    """
    token = str(uuid.uuid4())
    now   = time.monotonic()

    with _lock:
        # Abgelaufene Tokens entfernen
        expired = [k for k, v in _store.items() if v["expires"] < now]
        for k in expired:
            del _store[k]

        _store[token] = {
            "file_uuid": file_uuid,
            "user_id":   user_id,
            "expires":   now + TOKEN_TTL,
        }

    return token


def consume_token(token: str) -> dict | None:
    """
    Prüft den Token auf Gültigkeit (TTL) und löscht ihn sofort (Single-Use).
    Gibt die Token-Daten zurück oder None bei ungültigem / abgelaufenem Token.

    Rückgabe-Dict enthält: {"file_uuid": str, "user_id": int, "expires": float}
    """
    with _lock:
        entry = _store.pop(token, None)   # Sofort löschen = Single-Use garantiert

    if entry is None:
        return None

    if time.monotonic() > entry["expires"]:
        return None   # Abgelaufen (Race-Condition-sicher durch monotonic)

    return entry

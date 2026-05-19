"""
First-Run Setup-Wizard.
Wird angezeigt wenn kein ENCRYPTION_MASTER_KEY in .env gesetzt ist.
Generiert den Key, bietet das Notfall-PDF zum Download an und schreibt
den Key nach Bestätigung in die .env-Datei.
"""
import base64
import os
from pathlib import Path

from dotenv import set_key as dotenv_set_key
from nicegui import ui

from app.config import APP_TITLE
from app.core.emergency_kit import generate_emergency_kit_pdf

_ENV_PATH = Path(__file__).parent.parent.parent / ".env"


def _generate_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def setup_page() -> None:
    key = _generate_key()

    with ui.column().classes("w-full min-h-screen items-center justify-center bg-slate-50 p-4"):
        with ui.card().classes("w-full max-w-2xl p-8 shadow-lg"):

            # Header
            with ui.row().classes("items-center gap-3 mb-6"):
                ui.icon("key").classes("text-[32px] text-[#0078d4]")
                with ui.column().classes("gap-0"):
                    ui.label("Ersteinrichtung").classes(
                        "text-[22px] font-bold text-[#1e3a5f]"
                    )
                    ui.label(f"{APP_TITLE} – Verschlüsselungs-Setup").classes(
                        "text-sm text-slate-500"
                    )

            # Warnhinweis
            with ui.card().classes(
                "w-full bg-amber-50 border border-amber-300 p-4 mb-5"
            ):
                with ui.row().classes("items-start gap-2"):
                    ui.icon("warning").classes("text-amber-600 text-[20px] shrink-0 mt-0.5")
                    ui.label(
                        "Es wurde noch kein Verschlüsselungs-Master-Key konfiguriert. "
                        "Ein einmaliger 256-Bit-Key wurde für diese Sitzung generiert. "
                        "Sichern Sie ihn jetzt – er kann nicht wiederhergestellt werden."
                    ).classes("text-sm text-amber-800 leading-relaxed")

            # Key anzeigen
            ui.label("Generierter Master-Key").classes(
                "text-sm font-semibold text-slate-700 mb-1"
            )
            with ui.row().classes("w-full items-center gap-2 mb-1"):
                ui.input(value=key).props("readonly outlined dense").classes(
                    "flex-1"
                ).style("font-family: monospace; font-size: 12px;")
                ui.button(
                    icon="content_copy",
                    on_click=lambda: (
                        ui.run_javascript(
                            f"navigator.clipboard.writeText({repr(key)})"
                        ),
                        ui.notify("Key kopiert", type="positive"),
                    ),
                ).props("flat round dense").tooltip("In Zwischenablage kopieren")

            ui.label(
                "Niemals per E-Mail versenden oder unverschlüsselt speichern."
            ).classes("text-xs text-slate-400 mb-5")

            # Schritt 1: PDF
            with ui.card().classes(
                "w-full bg-blue-50 border border-blue-200 p-4 mb-4"
            ):
                ui.label("Schritt 1 – Notfall-Kit herunterladen").classes(
                    "text-sm font-semibold text-[#1e3a5f] mb-1"
                )
                ui.label(
                    "Laden Sie das Notfall-PDF herunter, drucken Sie es aus und "
                    "bewahren Sie es in einem Tresor oder Bankschließfach auf."
                ).classes("text-xs text-slate-600 mb-3")

                def download_pdf():
                    pdf = generate_emergency_kit_pdf(key, APP_TITLE)
                    ui.download(pdf, f"{APP_TITLE}_Notfall-Key.pdf")

                ui.button(
                    "Notfall-Kit als PDF herunterladen",
                    icon="download",
                    on_click=download_pdf,
                ).props("unelevated").classes("bg-[#0078d4] text-white")

            # Schritt 2: Bestätigen
            ui.label("Schritt 2 – Bestätigen und einrichten").classes(
                "text-sm font-semibold text-slate-700 mb-2"
            )

            finish_btn = (
                ui.button("Einrichtung abschließen", icon="check_circle")
                .props("unelevated disabled")
                .classes("bg-[#1e3a5f] text-white w-full mt-1")
            )

            def on_confirm(e):
                if e.value:
                    finish_btn.props(remove="disabled")
                else:
                    finish_btn.props("disabled")

            ui.checkbox(
                "Ich habe den Key gesichert und das Notfall-PDF heruntergeladen.",
                on_change=on_confirm,
            ).classes("text-sm text-slate-700 mb-1")

            def finish_setup():
                # In .env schreiben
                dotenv_set_key(str(_ENV_PATH), "ENCRYPTION_MASTER_KEY", key)
                # Sofort in Runtime setzen – kein Neustart nötig
                os.environ["ENCRYPTION_MASTER_KEY"] = key

                ui.notify(
                    "Master-Key erfolgreich konfiguriert. Willkommen!",
                    type="positive",
                )
                ui.navigate.to("/login")

            finish_btn.on("click", finish_setup)

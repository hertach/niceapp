# app/pages/login.py
from nicegui import ui, app
from app.core.auth import authenticate_user
from app.core.database import get_session
from app.config import APP_TITLE, APP_LOGO

def login_page() -> None:

    ui.query('body').style(
        'margin: 0; '
        'background-color: #f3f6f9; '
        'display: flex; '
        'justify-content: center; '
        'align-items: center; '
        'height: 100vh;'
    )

    with ui.card().style(
        'width: 380px; '
        'padding: 40px; '
        'border-radius: 8px; '
        'box-shadow: 0 4px 24px rgba(0,0,0,0.10);'
    ):
        with ui.column().style('align-items: center; width: 100%; gap: 4px;'):
            ui.image(APP_LOGO).style('height: 64px; width: 64px; margin-bottom: 8px;')
            ui.label(APP_TITLE).style(
                'font-size: 28px; font-weight: 700; color: #1e3a5f;'
            )

        username = ui.input(
            label='Benutzername',
            placeholder='dein.name',
        ).style('width: 100%;')

        password = ui.input(
            label='Passwort',
            placeholder='••••••••',
            password=True,
            password_toggle_button=True,
        ).style('width: 100%; margin-top: 12px;')

        error_label = ui.label('').style(
            'color: #d32f2f; font-size: 12px; min-height: 18px; margin-top: 4px;'
        )

        def handle_login() -> None:
            if not username.value or not password.value:
                error_label.set_text('Bitte alle Felder ausfüllen.')
                return

            with get_session() as session:
                user = authenticate_user(
                    username.value,
                    password.value,
                    session
                )

            if user is None:
                error_label.set_text('Ungültiger Benutzername oder Passwort.')
                password.set_value('')  # Passwortfeld leeren
                return

            # ✅ Einloggen: User-Daten in Session speichern
            app.storage.user['authenticated'] = True
            app.storage.user['username'] = user.username
            app.storage.user['role'] = user.role

            ui.navigate.to('/')

        ui.button('Anmelden', on_click=handle_login).style(
            'width: 100%; '
            'margin-top: 20px; '
            'background-color: #0078d4; '
            'color: white; '
            'font-weight: 600; '
            'height: 40px;'
        )

        password.on('keydown.enter', handle_login)
# app/pages/login.py
from nicegui import ui, app
from app.core.auth import authenticate_user
from app.core.database import get_session
from app.config import APP_TITLE, APP_LOGO

def login_page() -> None:

    ui.query('body').classes(
        'm-0 bg-[#f3f6f9] flex justify-center items-center h-screen'
    )

    with ui.card().classes(
        'w-[380px] p-10 rounded-[8px] shadow-[0_4px_24px_rgba(0,0,0,0.10)]'
    ):
        with ui.column().classes('items-center w-full gap-1'):
            ui.image(APP_LOGO).classes('h-16 w-16 mb-2')
            ui.label(APP_TITLE).classes(
                'text-[28px] font-bold text-[#1e3a5f]'
            )

        username = ui.input(
            label='Benutzername',
            placeholder='dein.name',
        ).classes('w-full')

        password = ui.input(
            label='Passwort',
            placeholder='••••••••',
            password=True,
            password_toggle_button=True,
        ).classes('w-full mt-3')

        error_label = ui.label('').classes(
            'text-[#d32f2f] text-[12px] min-h-[18px] mt-1'
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

        ui.button('Anmelden', on_click=handle_login).classes(
            'w-full mt-5 bg-[#0078d4] text-white font-semibold h-10'
        )

        password.on('keydown.enter', handle_login)
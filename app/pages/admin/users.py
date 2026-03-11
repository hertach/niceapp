from nicegui import ui
from app.core.database import get_session
from app.models.user import User
from app.core.auth import hash_password
from app.models.role import Role

def users_page() -> None:

    ui.label('Benutzerverwaltung').style(
        'font-size: 24px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
    )

    with ui.row().style('margin-bottom: 16px;'):
        ui.button(
            'Neuer Benutzer', icon='add',
            on_click=lambda: open_dialog(),
        ).props('unelevated').style('background-color: #0078d4; color: white;')

    grid = ui.aggrid({
        'columnDefs': [
            {'headerName': 'ID',           'field': 'id',        'width': 70},
            {'headerName': 'Benutzername', 'field': 'username',  'flex': 1},
            {'headerName': 'Rolle',        'field': 'role',      'width': 120},
            {'headerName': 'Aktiv',        'field': 'is_active', 'width': 90},
            {
                # Edit-Spalte: eigenes colId, kein sortieren/filtern
                'colId': 'action_edit',
                'headerName': '',
                'field': 'id',
                'width': 50,
                'sortable': False,
                'filter': False,
                ':cellRenderer': '''(params) => {
                    const btn = document.createElement("button");
                    btn.title = "Bearbeiten";
                    btn.style.cssText = "border:none;background:none;cursor:pointer;padding:2px;";
                    btn.innerHTML = "<span class=\'material-icons\' style=\'font-size:18px;color:#0078d4;vertical-align:middle\'>edit</span>";
                    return btn;
                }'''
            },
            {
                # Delete-Spalte
                'colId': 'action_delete',
                'headerName': '',
                'field': 'id',
                'width': 50,
                'sortable': False,
                'filter': False,
                ':cellRenderer': '''(params) => {
                    const btn = document.createElement("button");
                    btn.title = "Löschen";
                    btn.style.cssText = "border:none;background:none;cursor:pointer;padding:2px;";
                    btn.innerHTML = "<span class=\'material-icons\' style=\'font-size:18px;color:#d32f2f;vertical-align:middle\'>delete</span>";
                    return btn;
                }'''
            },
        ],
        'rowData': [],
        'rowSelection': 'none',
        'suppressRowClickSelection': True,
    }).style('height: 400px; width: 100%;')

    # ── cellClicked: nur colId + rowData (unsere einfachen Werte) ──
    def on_cell_clicked(e) -> None:
        col_id  = e.args.get('colId', '')
        data    = e.args.get('data', {})
        user_id = data.get('id')
        username = data.get('username', '')

        if col_id == 'action_edit':
            open_dialog(user_id)
        elif col_id == 'action_delete':
            confirm_delete(user_id, username)

    grid.on('cellClicked', on_cell_clicked)

    # ── Daten laden ──────────────────────────────────────────
    def load_users() -> None:
        with get_session() as session:
            users = session.query(User).all()
            row_data = [
                {
                    'id': u.id,
                    'username': u.username,
                    'role': u.role,
                    'is_active': '✅' if u.is_active else '❌',
                }
                for u in users
            ]
        # Direkt via AG Grid API setzen statt grid.update()
        grid.run_grid_method('setGridOption', 'rowData', row_data)

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog()

    def open_dialog(user_id: int | None = None) -> None:
        dialog.clear()
        with get_session() as session:
            all_roles = session.query(Role).order_by(Role.name).all()
            role_options = [r.name for r in all_roles]

        with dialog, ui.card().style('width: 400px; padding: 32px;'):
            title = 'Neuer Benutzer' if user_id is None else 'Benutzer bearbeiten'
            ui.label(title).style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
            )

            existing: User | None = None
            if user_id:
                with get_session() as session:
                    existing = session.get(User, user_id)

            username_input = ui.input(
                label='Benutzername',
                value=existing.username if existing else '',
            ).style('width: 100%;')

            password_input = ui.input(
                label='Passwort' if not existing else 'Neues Passwort (leer = unverändert)',
                password=True,
                password_toggle_button=True,
            ).style('width: 100%; margin-top: 12px;')

            role_select = ui.select(
                label='Rolle',
                options=role_options,  # ← aus DB ✅
                value=existing.role if existing else role_options[0],
            ).style('width: 100%; margin-top: 12px;')

            active_toggle = ui.switch(
                'Aktiv',
                value=existing.is_active if existing else True,
            ).style('margin-top: 12px;')

            error = ui.label('').style(
                'color: #d32f2f; font-size: 12px; min-height: 18px;'
            )

            def save() -> None:
                if not username_input.value:
                    error.set_text('Benutzername darf nicht leer sein.')
                    return
                with get_session() as session:
                    if user_id:
                        user = session.get(User, user_id)
                        user.username  = username_input.value
                        user.role      = role_select.value
                        user.is_active = active_toggle.value
                        if password_input.value:
                            user.password = hash_password(password_input.value)
                    else:
                        if not password_input.value:
                            error.set_text('Passwort ist erforderlich.')
                            return
                        session.add(User(
                            username=username_input.value,
                            password=hash_password(password_input.value),
                            role=role_select.value,
                            is_active=active_toggle.value,
                        ))
                    session.commit()

                ui.notify('Gespeichert ✅', type='positive')
                dialog.close()
                load_users()

            with ui.row().style('margin-top: 24px; gap: 8px; justify-content: flex-end;'):
                ui.button('Abbrechen', on_click=dialog.close).props('flat')
                ui.button('Speichern', on_click=save).props('unelevated').style(
                    'background-color: #0078d4; color: white;'
                )
        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(user_id: int, username: str) -> None:
        with ui.dialog() as confirm_dialog, ui.card().style('padding: 32px; width: 360px;'):
            ui.label('Benutzer löschen').style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f;'
            )
            ui.label(f'Soll "{username}" wirklich gelöscht werden?').style(
                'margin-top: 12px; color: #444; font-size: 14px;'
            )
            ui.label('Diese Aktion kann nicht rückgängig gemacht werden.').style(
                'color: #d32f2f; font-size: 12px; margin-top: 4px;'
            )

            def do_delete() -> None:
                with get_session() as session:
                    user = session.get(User, user_id)
                    if user:
                        session.delete(user)
                        session.commit()
                confirm_dialog.close()
                ui.notify(f'"{username}" gelöscht.', type='warning')
                load_users()

            with ui.row().style('margin-top: 24px; gap: 8px; justify-content: flex-end;'):
                ui.button('Abbrechen', on_click=confirm_dialog.close).props('flat')
                ui.button(
                    'Löschen', icon='delete', on_click=do_delete,
                ).props('unelevated').style('background-color: #d32f2f; color: white;')
        confirm_dialog.open()

    load_users()
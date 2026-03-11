# app/pages/admin/menu_items.py
from nicegui import ui
from app.core.database import get_session
from app.models.menu_item import MenuItem
from app.models.role import Role


def menu_items_page() -> None:

    ui.label('Menüverwaltung').style(
        'font-size: 24px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
    )

    with ui.row().style('margin-bottom: 16px;'):
        ui.button(
            'Neuer Menüpunkt', icon='add',
            on_click=lambda: open_dialog(),
        ).props('unelevated').style('background-color: #0078d4; color: white;')

    # ── AG Grid ─────────────────────────────────────────────
    grid = ui.aggrid({
        'columnDefs': [
            {'headerName': 'ID',         'field': 'id',         'width': 70},
            {'headerName': 'Label',      'field': 'label',      'width': 150},
            {'headerName': 'Icon',       'field': 'icon',       'width': 120},
            {'headerName': 'Pfad',       'field': 'path',       'flex': 1},
            {'headerName': 'Rollen',     'field': 'roles',      'width': 150},
            {'headerName': 'Reihenfolge','field': 'sort_order', 'width': 120},
            {
                'colId': 'action_edit',
                'headerName': '', 'field': 'id', 'width': 50,
                'sortable': False, 'filter': False,
                ':cellRenderer': '''(params) => {
                    const btn = document.createElement("button");
                    btn.title = "Bearbeiten";
                    btn.style.cssText = "border:none;background:none;cursor:pointer;padding:2px;";
                    btn.innerHTML = "<span class=\'material-icons\' style=\'font-size:18px;color:#0078d4;vertical-align:middle\'>edit</span>";
                    return btn;
                }'''
            },
            {
                'colId': 'action_delete',
                'headerName': '', 'field': 'id', 'width': 50,
                'sortable': False, 'filter': False,
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
    }).style('height: 450px; width: 100%;')

    # ── cellClicked ──────────────────────────────────────────
    def on_cell_clicked(e) -> None:
        col_id  = e.args.get('colId', '')
        data    = e.args.get('data', {})
        item_id = data.get('id')
        label   = data.get('label', '')

        if col_id == 'action_edit':
            open_dialog(item_id)
        elif col_id == 'action_delete':
            confirm_delete(item_id, label)

    grid.on('cellClicked', on_cell_clicked)

    # ── Daten laden ──────────────────────────────────────────
    def load_items() -> None:
        with get_session() as session:
            items = (
                session.query(MenuItem)
                .order_by(MenuItem.sort_order)
                .all()
            )
            row_data = [
                {
                    'id':         i.id,
                    'label':      i.label,
                    'icon':       i.icon,
                    'path':       i.path,
                    'roles':      i.roles if i.roles else '(alle)',
                    'sort_order': i.sort_order,
                }
                for i in items
            ]
        grid.run_grid_method('setGridOption', 'rowData', row_data)

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog()

    def open_dialog(item_id: int | None = None) -> None:
        dialog.clear()

        # Verfügbare Rollen für Checkboxen aus DB laden
        with get_session() as session:
            all_roles = session.query(Role).order_by(Role.name).all()
            role_names = [r.name for r in all_roles]

        with dialog, ui.card().style('width: 440px; padding: 32px;'):
            title = 'Neuer Menüpunkt' if item_id is None else 'Menüpunkt bearbeiten'
            ui.label(title).style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
            )

            existing: MenuItem | None = None
            if item_id:
                with get_session() as session:
                    existing = session.get(MenuItem, item_id)

            label_input = ui.input(
                label='Label',
                value=existing.label if existing else '',
                placeholder='z.B. Berichte',
            ).style('width: 100%;')

            icon_input = ui.input(
                label='Icon (Material Icon Name | (fonts.google.com/icons))',
                value=existing.icon if existing else '',
                placeholder='z.B. bar_chart',
            ).style('width: 100%; margin-top: 12px;')

            # Icon-Vorschau
            with ui.row().style('align-items: center; gap: 8px; margin-top: 4px;'):
                ui.label('Vorschau: ').style('font-size: 12px; color: #666;')
                preview_icon = ui.icon(
                    existing.icon if existing else 'help_outline'
                ).style('color: #1e3a5f; font-size: 24px;')

            # Icon-Vorschau live aktualisieren
            icon_input.on(
                'input',
                lambda e: preview_icon.set_name(e.args if e.args else 'help_outline')
            )

            path_input = ui.input(
                label='Pfad',
                value=existing.path if existing else '',
                placeholder='z.B. /reports',
            ).style('width: 100%; margin-top: 12px;')

            sort_input = ui.number(
                label='Reihenfolge',
                value=existing.sort_order if existing else 0,
                min=0,
                max=999,
                step=1,
            ).style('width: 100%; margin-top: 12px;')

            # ── Rollen-Checkboxen ────────────────────────────
            ui.label('Sichtbar für Rollen:').style(
                'margin-top: 16px; font-size: 13px; '
                'font-weight: 600; color: #1e3a5f;'
            )
            ui.label('(Keine Auswahl = für alle sichtbar)').style(
                'font-size: 11px; color: #999; margin-bottom: 4px;'
            )

            existing_roles = existing.roles_list() if existing else []
            role_checkboxes: dict[str, ui.checkbox] = {}

            with ui.row().style('gap: 16px; flex-wrap: wrap;'):
                for role_name in role_names:
                    cb = ui.checkbox(
                        role_name,
                        value=role_name in existing_roles,
                    )
                    role_checkboxes[role_name] = cb

            error = ui.label('').style(
                'color: #d32f2f; font-size: 12px; min-height: 18px; margin-top: 8px;'
            )

            def save() -> None:
                if not label_input.value:
                    error.set_text('Label darf nicht leer sein.')
                    return
                if not path_input.value:
                    error.set_text('Pfad darf nicht leer sein.')
                    return

                # Ausgewählte Rollen als Komma-String
                selected_roles = ','.join(
                    name for name, cb in role_checkboxes.items() if cb.value
                )

                with get_session() as session:
                    if item_id:
                        item = session.get(MenuItem, item_id)
                        item.label      = label_input.value
                        item.icon       = icon_input.value
                        item.path       = path_input.value
                        item.roles      = selected_roles
                        item.sort_order = int(sort_input.value)
                    else:
                        session.add(MenuItem(
                            label      = label_input.value,
                            icon       = icon_input.value,
                            path       = path_input.value,
                            roles      = selected_roles,
                            sort_order = int(sort_input.value),
                        ))
                    session.commit()

                ui.notify('Gespeichert ✅', type='positive')
                dialog.close()
                load_items()

            with ui.row().style(
                'margin-top: 24px; gap: 8px; justify-content: flex-end;'
            ):
                ui.button('Abbrechen', on_click=dialog.close).props('flat')
                ui.button('Speichern', on_click=save).props('unelevated').style(
                    'background-color: #0078d4; color: white;'
                )
        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(item_id: int, label: str) -> None:
        with ui.dialog() as confirm_dialog, ui.card().style(
            'padding: 32px; width: 360px;'
        ):
            ui.label('Menüpunkt löschen').style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f;'
            )
            ui.label(f'Soll "{label}" wirklich gelöscht werden?').style(
                'margin-top: 12px; color: #444; font-size: 14px;'
            )

            def do_delete() -> None:
                with get_session() as session:
                    item = session.get(MenuItem, item_id)
                    if item:
                        session.delete(item)
                        session.commit()
                confirm_dialog.close()
                ui.notify(f'"{label}" gelöscht.', type='warning')
                load_items()

            with ui.row().style(
                'margin-top: 24px; gap: 8px; justify-content: flex-end;'
            ):
                ui.button('Abbrechen', on_click=confirm_dialog.close).props('flat')
                ui.button(
                    'Löschen', icon='delete', on_click=do_delete,
                ).props('unelevated').style(
                    'background-color: #d32f2f; color: white;'
                )
        confirm_dialog.open()

    load_items()
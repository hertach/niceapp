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

    # ── Daten laden ──────────────────────────────────────────
    def get_menu_data() -> list[dict]:
        with get_session() as session:
            items = (
                session.query(MenuItem)
                .order_by(MenuItem.sort_order)
                .all()
            )
            return [
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

    # ── Tabelle ──────────────────────────────────────────────
    table = ui.table(
        columns=[
            {'name': 'id',         'label': 'ID',           'field': 'id',         'align': 'left', 'sortable': True},
            {'name': 'label',      'label': 'Label',        'field': 'label',      'align': 'left', 'sortable': True},
            {'name': 'icon',       'label': 'Icon',         'field': 'icon',       'align': 'left'},
            {'name': 'path',       'label': 'Pfad',         'field': 'path',       'align': 'left'},
            {'name': 'roles',      'label': 'Rollen',       'field': 'roles',      'align': 'left'},
            {'name': 'sort_order', 'label': 'Reihenfolge',  'field': 'sort_order', 'align': 'left', 'sortable': True},
            {'name': 'actions',    'label': 'Aktionen',     'field': 'actions',    'align': 'left'},
        ],
        rows=get_menu_data(),
        row_key='id',
    ).style('width: 100%;')

    table.add_slot('body-cell-actions', '''
        <q-td :props="props">
            <q-btn flat round
                icon="edit"
                color="primary"
                size="sm"
                @click="$parent.$emit('edit', props.row)"
            />
            <q-btn flat round
                icon="delete"
                color="negative"
                size="sm"
                @click="$parent.$emit('delete', props.row)"
            />
        </q-td>
    ''')

    table.on('edit',   lambda e: open_dialog(e.args['id']))
    table.on('delete', lambda e: confirm_delete(e.args['id'], e.args['label']))

    def load_items() -> None:
        table.rows = get_menu_data()
        table.update()

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog()

    def open_dialog(item_id: int | None = None) -> None:
        dialog.clear()

        with get_session() as session:
            all_roles  = session.query(Role).order_by(Role.name).all()
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
                label='Icon (Material Icon Name | fonts.google.com/icons)',
                value=existing.icon if existing else '',
                placeholder='z.B. bar_chart',
            ).style('width: 100%; margin-top: 12px;')

            with ui.row().style('align-items: center; gap: 8px; margin-top: 4px;'):
                ui.label('Vorschau: ').style('font-size: 12px; color: #666;')
                preview_icon = ui.icon(
                    existing.icon if existing else 'help_outline'
                ).style('color: #1e3a5f; font-size: 24px;')

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
                min=0, max=999, step=1,
            ).style('width: 100%; margin-top: 12px;')

            ui.label('Sichtbar für Rollen:').style(
                'margin-top: 16px; font-size: 13px; font-weight: 600; color: #1e3a5f;'
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

                selected_roles = ','.join(
                    name for name, cb in role_checkboxes.items() if cb.value
                )

                with get_session() as session:
                    if item_id:
                        item            = session.get(MenuItem, item_id)
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
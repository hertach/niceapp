# app/pages/admin/roles.py
from nicegui import ui
from app.core.database import get_session
from app.models.role import Role


def roles_page() -> None:

    ui.label('Rollenverwaltung').style(
        'font-size: 24px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
    )

    with ui.row().style('margin-bottom: 16px;'):
        ui.button(
            'Neue Rolle', icon='add',
            on_click=lambda: open_dialog(),
        ).props('unelevated').style('background-color: #0078d4; color: white;')

    # ── Daten laden ──────────────────────────────────────────
    def get_role_data() -> list[dict]:
        with get_session() as session:
            roles = session.query(Role).all()
            return [
                {
                    'id':          r.id,
                    'name':        r.name,
                    'description': r.description,
                }
                for r in roles
            ]

    # ── Tabelle ──────────────────────────────────────────────
    table = ui.table(
        columns=[
            {'name': 'id',          'label': 'ID',           'field': 'id',          'align': 'left', 'sortable': True},
            {'name': 'name',        'label': 'Name',         'field': 'name',        'align': 'left', 'sortable': True},
            {'name': 'description', 'label': 'Beschreibung', 'field': 'description', 'align': 'left'},
            {'name': 'actions',     'label': 'Aktionen',     'field': 'actions',     'align': 'left'},
        ],
        rows=get_role_data(),
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
    table.on('delete', lambda e: confirm_delete(e.args['id'], e.args['name']))

    def load_roles() -> None:
        table.rows = get_role_data()
        table.update()

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog()

    def open_dialog(role_id: int | None = None) -> None:
        dialog.clear()
        with dialog, ui.card().style('width: 400px; padding: 32px;'):
            title = 'Neue Rolle' if role_id is None else 'Rolle bearbeiten'
            ui.label(title).style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f; margin-bottom: 16px;'
            )

            existing: Role | None = None
            if role_id:
                with get_session() as session:
                    existing = session.get(Role, role_id)

            name_input = ui.input(
                label='Rollenname',
                value=existing.name if existing else '',
                placeholder='z.B. manager',
            ).style('width: 100%;')

            desc_input = ui.input(
                label='Beschreibung',
                value=existing.description if existing else '',
                placeholder='Kurze Beschreibung der Rolle',
            ).style('width: 100%; margin-top: 12px;')

            error = ui.label('').style(
                'color: #d32f2f; font-size: 12px; min-height: 18px;'
            )

            def save() -> None:
                if not name_input.value:
                    error.set_text('Rollenname darf nicht leer sein.')
                    return
                with get_session() as session:
                    duplicate = session.query(Role).filter_by(
                        name=name_input.value
                    ).first()
                    if duplicate and duplicate.id != role_id:
                        error.set_text(f'Rolle "{name_input.value}" existiert bereits.')
                        return
                    if role_id:
                        role             = session.get(Role, role_id)
                        role.name        = name_input.value
                        role.description = desc_input.value
                    else:
                        session.add(Role(
                            name        = name_input.value,
                            description = desc_input.value,
                        ))
                    session.commit()

                ui.notify('Gespeichert ✅', type='positive')
                dialog.close()
                load_roles()

            with ui.row().style(
                'margin-top: 24px; gap: 8px; justify-content: flex-end;'
            ):
                ui.button('Abbrechen', on_click=dialog.close).props('flat')
                ui.button('Speichern', on_click=save).props('unelevated').style(
                    'background-color: #0078d4; color: white;'
                )
        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(role_id: int, name: str) -> None:
        if name in ('admin', 'user'):
            ui.notify(
                f'Standard-Rolle "{name}" kann nicht gelöscht werden.',
                type='warning'
            )
            return

        with ui.dialog() as confirm_dialog, ui.card().style(
            'padding: 32px; width: 360px;'
        ):
            ui.label('Rolle löschen').style(
                'font-size: 18px; font-weight: 600; color: #1e3a5f;'
            )
            ui.label(f'Soll die Rolle "{name}" wirklich gelöscht werden?').style(
                'margin-top: 12px; color: #444; font-size: 14px;'
            )
            ui.label('Diese Aktion kann nicht rückgängig gemacht werden.').style(
                'color: #d32f2f; font-size: 12px; margin-top: 4px;'
            )

            def do_delete() -> None:
                with get_session() as session:
                    role = session.get(Role, role_id)
                    if role:
                        session.delete(role)
                        session.commit()
                confirm_dialog.close()
                ui.notify(f'Rolle "{name}" gelöscht.', type='warning')
                load_roles()

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
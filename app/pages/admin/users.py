# app/pages/admin/users.py
from nicegui import ui

from app.core.auth import hash_password
from app.core.database import get_session
from app.models.role import Role
from app.models.user import User


def users_page() -> None:

    ui.label("Benutzerverwaltung").classes(
        "text-[24px] font-semibold text-[#1e3a5f] mb-4"
    )

    with ui.row().classes("mb-4"):
        ui.button(
            "Neuer Benutzer",
            icon="add",
            on_click=lambda: open_dialog(),
        ).props(
            "unelevated"
        ).classes("bg-[#0078d4] text-white")

    # ── Daten laden ──────────────────────────────────────────
    def get_user_data() -> list[dict]:
        with get_session() as session:
            users = session.query(User).all()
            return [
                {
                    "id": u.id,
                    "username": u.username,
                    "role": u.role,
                    "is_active": "✅" if u.is_active else "❌",
                }
                for u in users
            ]

    # ── Tabelle ──────────────────────────────────────────────
    table = ui.table(
        columns=[
            {
                "name": "id",
                "label": "ID",
                "field": "id",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "username",
                "label": "Benutzername",
                "field": "username",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "role",
                "label": "Rolle",
                "field": "role",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "is_active",
                "label": "Aktiv",
                "field": "is_active",
                "align": "left",
            },
            {
                "name": "actions",
                "label": "Aktionen",
                "field": "actions",
                "align": "left",
            },
        ],
        rows=get_user_data(),
        row_key="id",
    ).classes("w-full")

    # ── Edit/Delete Buttons via Quasar Slot ──────────────────
    table.add_slot(
        "body-cell-actions",
        """
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
    """,
    )

    table.on("edit", lambda e: open_dialog(e.args["id"]))
    table.on("delete", lambda e: confirm_delete(e.args["id"], e.args["username"]))

    def load_users() -> None:
        table.rows = get_user_data()
        table.update()

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog()

    def open_dialog(user_id: int | None = None) -> None:
        dialog.clear()

        with get_session() as session:
            all_roles = session.query(Role).order_by(Role.name).all()
            role_options = [r.name for r in all_roles]

        with dialog, ui.card().classes("w-[400px] p-8"):
            title = "Neuer Benutzer" if user_id is None else "Benutzer bearbeiten"
            ui.label(title).classes("text-[18px] font-semibold text-[#1e3a5f] mb-4")

            existing: User | None = None
            if user_id:
                with get_session() as session:
                    existing = session.get(User, user_id)

            username_input = ui.input(
                label="Benutzername",
                value=existing.username if existing else "",
            ).classes("w-full")

            password_input = ui.input(
                label=(
                    "Passwort"
                    if not existing
                    else "Neues Passwort (leer = unverändert)"
                ),
                password=True,
                password_toggle_button=True,
            ).classes("w-full mt-3")

            role_select = ui.select(
                label="Rolle",
                options=role_options,
                value=existing.role if existing else role_options[0],
            ).classes("w-full mt-3")

            active_toggle = ui.switch(
                "Aktiv",
                value=existing.is_active if existing else True,
            ).classes("mt-3")

            error = ui.label("").classes("text-[#d32f2f] text-[12px] min-h-[18px]")

            def save() -> None:
                if not username_input.value:
                    error.set_text("Benutzername darf nicht leer sein.")
                    return
                with get_session() as session:
                    if user_id:
                        user = session.get(User, user_id)
                        user.username = username_input.value
                        user.role = role_select.value
                        user.is_active = active_toggle.value
                        if password_input.value:
                            user.password = hash_password(password_input.value)
                    else:
                        if not password_input.value:
                            error.set_text("Passwort ist erforderlich.")
                            return
                        session.add(
                            User(
                                username=username_input.value,
                                password=hash_password(password_input.value),
                                role=role_select.value,
                                is_active=active_toggle.value,
                            )
                        )
                    session.commit()

                ui.notify("Gespeichert ✅", type="positive")
                dialog.close()
                load_users()

            with ui.row().classes("mt-6 gap-2 justify-end w-full"):
                ui.button("Abbrechen", on_click=dialog.close).props("flat")
                ui.button("Speichern", on_click=save).props("unelevated").classes(
                    "bg-[#0078d4] text-white"
                )
        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(user_id: int, username: str) -> None:
        with ui.dialog() as confirm_dialog, ui.card().classes("p-8 w-[360px]"):
            ui.label("Benutzer löschen").classes(
                "text-[18px] font-semibold text-[#1e3a5f]"
            )
            ui.label(f'Soll "{username}" wirklich gelöscht werden?').classes(
                "mt-3 text-[#444] text-[14px]"
            )
            ui.label("Diese Aktion kann nicht rückgängig gemacht werden.").classes(
                "text-[#d32f2f] text-[12px] mt-1"
            )

            def do_delete() -> None:
                with get_session() as session:
                    user = session.get(User, user_id)
                    if user:
                        session.delete(user)
                        session.commit()
                confirm_dialog.close()
                ui.notify(f'"{username}" gelöscht.', type="warning")
                load_users()

            with ui.row().classes("mt-6 gap-2 justify-end w-full"):
                ui.button("Abbrechen", on_click=confirm_dialog.close).props("flat")
                ui.button(
                    "Löschen",
                    icon="delete",
                    on_click=do_delete,
                ).props(
                    "unelevated"
                ).classes("bg-[#d32f2f] text-white")
        confirm_dialog.open()

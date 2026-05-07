# app/pages/admin/users.py
from nicegui import ui
from app.core.auth import hash_password
from app.core.database import get_session
from app.models.role import Role
from app.models.user import User


def users_page() -> None:
    ui.label("Benutzerverwaltung").classes("text-[24px] font-semibold text-[#1e3a5f] mb-4")

    # ── Daten laden ──────────────────────────────────────────
    def get_user_data() -> list[dict]:
        with get_session() as session:
            users = session.query(User).all()
            return [
                {
                    "id": u.id,
                    "username": u.username,
                    "full_name": f"{u.first_name or ''} {u.last_name or ''}".strip() or "-",
                    "email": u.email or "",
                    "phone": u.phone or "",
                    "role": u.role,
                    "is_active": "✅" if u.is_active else "❌",
                    # Rohdaten für den Dialog-Edit
                    "first_name": u.first_name,
                    "last_name": u.last_name,
                }
                for u in users
            ]

    def load_users():
        table.rows[:] = get_user_data()
        table.update()

    with ui.row().classes("mb-4"):
        ui.button("Neuer Benutzer", icon="add", on_click=lambda: open_dialog()).props("unelevated").classes(
            "bg-[#0078d4] text-white")

    # ── Tabelle ──────────────────────────────────────────────
    columns = [
        {"name": "username", "label": "Login", "field": "username", "align": "left", "sortable": True},
        {"name": "full_name", "label": "Name", "field": "full_name", "align": "left", "sortable": True},
        {"name": "email", "label": "E-Mail", "field": "email", "align": "left"},
        {"name": "phone", "label": "Telefon", "field": "phone", "align": "left"},
        {"name": "role", "label": "Rolle", "field": "role", "align": "left"},
        {"name": "status", "label": "Aktiv", "field": "is_active", "align": "center"},
        {"name": "actions", "label": "Aktionen", "field": "id", "align": "right"},
    ]

    table = ui.table(columns=columns, rows=get_user_data(), row_key="id").classes(
        "w-full shadow-sm border border-slate-200 bg-white")

    table.add_slot("body-cell-actions", r"""
        <q-td :props="props">
            <q-btn flat round dense icon="edit" color="primary" @click="$parent.$emit('edit', props.row)" />
            <q-btn flat round dense icon="delete" color="negative" @click="$parent.$emit('delete', props.row)" />
        </q-td>
    """)

    table.on("edit", lambda e: open_dialog(e.args))
    table.on("delete", lambda e: confirm_delete(e.args["id"], e.args["username"]))

    # ── Dialog (Erstellen / Bearbeiten) ──────────────────────
    def open_dialog(user_data: dict = None) -> None:
        is_edit = user_data is not None
        title = "Benutzer bearbeiten" if is_edit else "Neuer Benutzer"

        with ui.dialog() as dialog, ui.card().classes("p-8 w-[500px]"):
            ui.label(title).classes("text-[18px] font-semibold text-[#1e3a5f] mb-4")

            with ui.column().classes("w-full gap-3"):
                # Login-Daten
                username = ui.input("Benutzername (Login)", value=user_data["username"] if is_edit else "").classes(
                    "w-full").props("outlined dense")
                password = ui.input("Passwort", password=True).classes("w-full").props(
                    f"outlined dense placeholder='{'Unverändert lassen' if is_edit else ''}'")

                ui.separator().classes("my-2")

                # Persönliche Daten (Die neuen Felder)
                with ui.row().classes("w-full gap-2"):
                    fname = ui.input("Vorname", value=user_data["first_name"] if is_edit else "").classes(
                        "flex-1").props("outlined dense")
                    lname = ui.input("Name", value=user_data["last_name"] if is_edit else "").classes("flex-1").props(
                        "outlined dense")

                email = ui.input("E-Mail", value=user_data["email"] if is_edit else "").classes("w-full").props(
                    "outlined dense type='email'")
                phone = ui.input("Telefon", value=user_data["phone"] if is_edit else "").classes("w-full").props(
                    "outlined dense")

                ui.separator().classes("my-2")

                # Rollen und Status
                with get_session() as session:
                    roles = [r.name for r in session.query(Role).all()]

                role_select = ui.select(roles, label="Rolle", value=user_data["role"] if is_edit else "user").classes(
                    "w-full").props("outlined dense")
                active_toggle = ui.checkbox("Benutzer ist aktiv",
                                            value=True if not is_edit else (user_data["is_active"] == "✅")).classes(
                    "mt-2")

            def save() -> None:
                if not username.value:
                    return ui.notify("Benutzername ist erforderlich", type="warning")

                with get_session() as session:
                    if is_edit:
                        u = session.get(User, user_data["id"])
                    else:
                        u = User(username=username.value)
                        session.add(u)

                    u.username = username.value
                    u.first_name = fname.value
                    u.last_name = lname.value
                    u.email = email.value
                    u.phone = phone.value
                    u.role = role_select.value
                    u.is_active = active_toggle.value

                    if password.value:
                        u.password = hash_password(password.value)

                    session.commit()

                dialog.close()
                ui.notify("Benutzer gespeichert", type="positive")
                load_users()

            with ui.row().classes("mt-6 gap-2 justify-end w-full"):
                ui.button("Abbrechen", on_click=dialog.close).props("flat")
                ui.button("Speichern", on_click=save).props("unelevated").classes("bg-[#0078d4] text-white")

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

# app/pages/admin/menu_items.py
from nicegui import ui

from app.core.database import get_session
from app.models.menu_item import MenuItem
from app.models.role import Role


def menu_items_page() -> None:

    ui.label("Menüverwaltung").classes("text-[24px] font-semibold text-[#1e3a5f] mb-4")

    with ui.row().classes("mb-4"):
        ui.button(
            "Neuer Menüpunkt",
            icon="add",
            on_click=lambda: open_dialog(),
        ).props(
            "unelevated"
        ).classes("bg-[#0078d4] text-white")

    # ── Daten laden ──────────────────────────────────────────
    def get_menu_data() -> list[dict]:
        with get_session() as session:
            items = session.query(MenuItem).order_by(MenuItem.sort_order).all()
            return [
                {
                    "id": i.id,
                    "label": i.label,
                    "icon": i.icon,
                    "path": i.path,
                    "roles": i.roles if i.roles else "(alle)",
                    "sort_order": i.sort_order,
                }
                for i in items
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
                "name": "label",
                "label": "Label",
                "field": "label",
                "align": "left",
                "sortable": True,
            },
            {"name": "icon", "label": "Icon", "field": "icon", "align": "left"},
            {"name": "path", "label": "Pfad", "field": "path", "align": "left"},
            {"name": "roles", "label": "Rollen", "field": "roles", "align": "left"},
            {
                "name": "sort_order",
                "label": "Reihenfolge",
                "field": "sort_order",
                "align": "left",
                "sortable": True,
            },
            {
                "name": "actions",
                "label": "Aktionen",
                "field": "actions",
                "align": "left",
            },
        ],
        rows=get_menu_data(),
        row_key="id",
    ).classes("w-full")

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
    table.on("delete", lambda e: confirm_delete(e.args["id"], e.args["label"]))

    def load_items() -> None:
        table.rows = get_menu_data()
        table.update()

    # ── Edit-Dialog ──────────────────────────────────────────
    dialog = ui.dialog()

    def open_dialog(item_id: int | None = None) -> None:
        dialog.clear()

        with get_session() as session:
            all_roles = session.query(Role).order_by(Role.name).all()
            role_names = [r.name for r in all_roles]

        with dialog, ui.card().classes("w-[440px] p-8"):
            title = "Neuer Menüpunkt" if item_id is None else "Menüpunkt bearbeiten"
            ui.label(title).classes("text-[18px] font-semibold text-[#1e3a5f] mb-4")

            existing: MenuItem | None = None
            if item_id:
                with get_session() as session:
                    existing = session.get(MenuItem, item_id)

            label_input = ui.input(
                label="Label",
                value=existing.label if existing else "",
                placeholder="z.B. Berichte",
            ).classes("w-full")

            icon_input = ui.input(
                label="Icon (Material Icon Name | fonts.google.com/icons)",
                value=existing.icon if existing else "",
                placeholder="z.B. bar_chart",
            ).classes("w-full mt-3")

            with ui.row().classes("items-center gap-2 mt-1"):
                ui.label("Vorschau: ").classes("text-[12px] text-[#666]")
                preview_icon = ui.icon(
                    existing.icon if existing else "help_outline"
                ).classes("text-[#1e3a5f] text-[24px]")

            icon_input.on(
                "input",
                lambda e: preview_icon.set_name(e.args if e.args else "help_outline"),
            )

            path_input = ui.input(
                label="Pfad",
                value=existing.path if existing else "",
                placeholder="z.B. /reports",
            ).classes("w-full mt-3")

            sort_input = ui.number(
                label="Reihenfolge",
                value=existing.sort_order if existing else 0,
                min=0,
                max=999,
                step=1,
            ).classes("w-full mt-3")

            ui.label("Sichtbar für Rollen:").classes(
                "mt-4 text-[13px] font-semibold text-[#1e3a5f]"
            )
            ui.label("(Keine Auswahl = für alle sichtbar)").classes(
                "text-[11px] text-[#999] mb-1"
            )

            existing_roles = existing.roles_list() if existing else []
            role_checkboxes: dict[str, ui.checkbox] = {}

            with ui.row().classes("gap-4 flex-wrap"):
                for role_name in role_names:
                    cb = ui.checkbox(
                        role_name,
                        value=role_name in existing_roles,
                    )
                    role_checkboxes[role_name] = cb

            error = ui.label("").classes("text-[#d32f2f] text-[12px] min-h-[18px] mt-2")

            def save() -> None:
                if not label_input.value:
                    error.set_text("Label darf nicht leer sein.")
                    return
                if not path_input.value:
                    error.set_text("Pfad darf nicht leer sein.")
                    return

                selected_roles = ",".join(
                    name for name, cb in role_checkboxes.items() if cb.value
                )

                with get_session() as session:
                    if item_id:
                        item = session.get(MenuItem, item_id)
                        item.label = label_input.value
                        item.icon = icon_input.value
                        item.path = path_input.value
                        item.roles = selected_roles
                        item.sort_order = int(sort_input.value)
                    else:
                        session.add(
                            MenuItem(
                                label=label_input.value,
                                icon=icon_input.value,
                                path=path_input.value,
                                roles=selected_roles,
                                sort_order=int(sort_input.value),
                            )
                        )
                    session.commit()

                ui.notify("Gespeichert ✅", type="positive")
                dialog.close()
                load_items()

            with ui.row().classes("mt-6 gap-2 justify-end w-full"):
                ui.button("Abbrechen", on_click=dialog.close).props("flat")
                ui.button("Speichern", on_click=save).props("unelevated").classes(
                    "bg-[#0078d4] text-white"
                )
        dialog.open()

    # ── Delete-Dialog ────────────────────────────────────────
    def confirm_delete(item_id: int, label: str) -> None:
        with ui.dialog() as confirm_dialog, ui.card().classes("p-8 w-[360px]"):
            ui.label("Menüpunkt löschen").classes(
                "text-[18px] font-semibold text-[#1e3a5f]"
            )
            ui.label(f'Soll "{label}" wirklich gelöscht werden?').classes(
                "mt-3 text-[#444] text-[14px]"
            )

            def do_delete() -> None:
                with get_session() as session:
                    item = session.get(MenuItem, item_id)
                    if item:
                        session.delete(item)
                        session.commit()
                confirm_dialog.close()
                ui.notify(f'"{label}" gelöscht.', type="warning")
                load_items()

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

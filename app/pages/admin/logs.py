# app/pages/admin/logs.py
from nicegui import ui
from sqlalchemy import desc
from app.models.log_entry import LogEntry, LogSessionLocal


def logs_page() -> None:
    ui.label('System-Logs').classes('text-[24px] font-semibold text-[#1e3a5f] mb-4')

    filter_state = {'level': 'Alle', 'search': ''}

    def fetch_logs():
        # Nutzt die isolierte Log-Session!
        with LogSessionLocal() as session:
            query = session.query(LogEntry)

            if filter_state['level'] != 'Alle':
                query = query.filter(LogEntry.level == filter_state['level'])

            if filter_state['search']:
                search_term = f"%{filter_state['search']}%"
                query = query.filter(LogEntry.message.ilike(search_term) | LogEntry.module.ilike(search_term))

            logs = query.order_by(desc(LogEntry.timestamp)).limit(100).all()

            return [
                {
                    'id': l.id,
                    'timestamp': l.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
                    'level': l.level,
                    'module': l.module,
                    'message': l.message
                } for l in logs
            ]

    def update_table():
        table.rows = fetch_logs()
        table.update()

    with ui.row().classes('w-full items-center gap-4 mb-4'):
        ui.select(
            ['Alle', 'INFO', 'WARNING', 'ERROR'],
            label='Loglevel',
            value='Alle',
            on_change=lambda e: (filter_state.update({'level': e.value}), update_table())
        ).classes('w-[150px]').props('dense')

        search_input = ui.input(
            label='Suchen...',
            on_change=lambda e: (filter_state.update({'search': e.value}), update_table())
        ).classes('w-[300px]').props('dense clearable')

        with search_input.add_slot('append'):
            ui.icon('search')

        ui.space()
        ui.button('Aktualisieren', icon='refresh', on_click=update_table).props('flat')

    table = ui.table(
        columns=[
            {'name': 'timestamp', 'label': 'Zeit', 'field': 'timestamp', 'align': 'left'},
            {'name': 'level', 'label': 'Level', 'field': 'level', 'align': 'left'},
            {'name': 'module', 'label': 'Modul', 'field': 'module', 'align': 'left'},
            {'name': 'message', 'label': 'Nachricht', 'field': 'message', 'align': 'left'},
        ],
        rows=fetch_logs(),
        row_key='id'
    ).classes('w-full')

    table.add_slot('body-cell-level', '''
        <q-td :props="props">
            <q-badge :color="props.value === 'ERROR' ? 'negative' : (props.value === 'WARNING' ? 'warning' : 'info')">
                {{ props.value }}
            </q-badge>
        </q-td>
    ''')
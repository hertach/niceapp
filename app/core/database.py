from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session
from app.config import DB_PATH

engine = create_engine(
    f'sqlite:///{DB_PATH}',
    connect_args={'check_same_thread': False},
)

class Base(DeclarativeBase):
    pass


def get_session() -> Session:
    return Session(engine)


def init_db() -> None:
    from app.models.patient import Patient
    Base.metadata.create_all(engine)
    _seed_roles()
    _seed_menu_items()

def _seed_roles() -> None:
    # ← Import HIER drin, nicht oben – verhindert den Zirkel
    from app.models.role import Role

    with Session(engine) as session:
        for name, description in [
            ('admin', 'Voller Zugriff auf alle Bereiche'),
            ('user',  'Standardzugriff'),
        ]:
            exists = session.query(Role).filter_by(name=name).first()
            if not exists:
                session.add(Role(name=name, description=description))
        session.commit()

def _seed_menu_items() -> None:
    from app.models.menu_item import MenuItem

    defaults = [
        MenuItem(label='Dashboard', icon='dashboard', path='/',             roles='',      sort_order=0),
        MenuItem(label='Patienten', icon='people', path='/patients', roles='', sort_order=10),
        MenuItem(label='Benutzer',  icon='people',    path='/admin/users',  roles='admin', sort_order=97),
        MenuItem(label='Rollen',    icon='shield',    path='/admin/roles',  roles='admin', sort_order=98),
        MenuItem(label='Menü', icon='menu', path='/admin/menu', roles='admin', sort_order=99),
    ]

    with Session(engine) as session:
        for item in defaults:
            exists = session.query(MenuItem).filter_by(path=item.path).first()
            if not exists:
                session.add(item)
        session.commit()
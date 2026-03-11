# migrations/env.py
import sys
import importlib
import pkgutil
from pathlib import Path

# Projektroot in den Python-Path einfügen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Models automatisch laden ──────────────────────────────────────────────────
# Jedes neu erstellte Model unter app/models/ wird automatisch erkannt,
# ohne dass env.py manuell angepasst werden muss.
import app.models as _models_pkg
from app.config import DB_PATH
from app.core.database import Base


def _load_all_models() -> None:
    """Importiert alle Module unter app/models/ → registriert sie bei Base.metadata."""
    for _, module_name, _ in pkgutil.walk_packages(
        path=_models_pkg.__path__,
        prefix=_models_pkg.__name__ + '.',
    ):
        importlib.import_module(module_name)


_load_all_models()

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config

# DB-URL aus config.py injizieren (überschreibt leeren Wert in alembic.ini)
config.set_main_option('sqlalchemy.url', f'sqlite:///{DB_PATH}')

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Offline-Modus ─────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
        render_as_batch=True,  # nötig für SQLite ALTER TABLE
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online-Modus ──────────────────────────────────────────────────────────────
def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # nötig für SQLite ALTER TABLE
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
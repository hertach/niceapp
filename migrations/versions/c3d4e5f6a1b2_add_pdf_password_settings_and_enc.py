"""Add pdf_password to app_settings and pdf_password_enc to patient_files

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a1b2"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Globales PDF-Passwort in den App-Settings
    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("pdf_password", sa.String(length=100), nullable=True)
        )

    # Gespeichertes (verschlüsseltes) Passwort pro Datei
    with op.batch_alter_table("patient_files", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("pdf_password_enc", sa.String(length=512), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("patient_files", schema=None) as batch_op:
        batch_op.drop_column("pdf_password_enc")

    with op.batch_alter_table("app_settings", schema=None) as batch_op:
        batch_op.drop_column("pdf_password")

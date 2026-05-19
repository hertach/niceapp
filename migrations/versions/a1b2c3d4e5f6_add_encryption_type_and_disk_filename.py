"""Add encryption_type and disk_filename to patient_files

Revision ID: a1b2c3d4e5f6
Revises: 695219a9111b
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "695219a9111b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("patient_files", schema=None) as batch_op:
        # Dateiname auf Disk (uuid oder uuid.pdf)
        batch_op.add_column(
            sa.Column("disk_filename", sa.String(length=41), nullable=True)
        )
        # Verschlüsselungstyp: pdf_password oder aes_gcm
        batch_op.add_column(
            sa.Column(
                "encryption_type",
                sa.String(length=20),
                nullable=False,
                server_default="pdf_password",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("patient_files", schema=None) as batch_op:
        batch_op.drop_column("encryption_type")
        batch_op.drop_column("disk_filename")

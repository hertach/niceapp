"""Add custom_pdf_password to patients

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a1"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("custom_pdf_password", sa.String(length=100), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.drop_column("custom_pdf_password")

"""Add doc_type to patient_files

Revision ID: e6f7a8b9c0d1
Revises: d527451a44aa
Create Date: 2026-05-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d527451a44aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("patient_files", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("doc_type", sa.String(length=50), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("patient_files", schema=None) as batch_op:
        batch_op.drop_column("doc_type")

"""ingestion backoff controls

Revision ID: 20260307_0005
Revises: 20260307_0004
Create Date: 2026-03-07 13:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260307_0005"
down_revision = "20260307_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("sourcehealth")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("sourcehealth")}

    with op.batch_alter_table("sourcehealth") as batch_op:
        if "consecutive_errors" not in existing_columns:
            batch_op.add_column(sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"))
        if "backoff_until" not in existing_columns:
            batch_op.add_column(sa.Column("backoff_until", sa.DateTime(timezone=True), nullable=True))
        if "ix_sourcehealth_backoff_until" not in existing_indexes:
            batch_op.create_index("ix_sourcehealth_backoff_until", ["backoff_until"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("sourcehealth")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("sourcehealth")}

    with op.batch_alter_table("sourcehealth") as batch_op:
        if "ix_sourcehealth_backoff_until" in existing_indexes:
            batch_op.drop_index("ix_sourcehealth_backoff_until")
        if "backoff_until" in existing_columns:
            batch_op.drop_column("backoff_until")
        if "consecutive_errors" in existing_columns:
            batch_op.drop_column("consecutive_errors")

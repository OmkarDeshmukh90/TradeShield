"""playbook approvals

Revision ID: 20260307_0006
Revises: 20260307_0005
Create Date: 2026-03-07 15:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260307_0006"
down_revision = "20260307_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playbookapproval",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("playbook_id", sa.String(), sa.ForeignKey("playbook.id"), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("owner_user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("decision_note", sa.String(), nullable=False, server_default=""),
        sa.Column("decided_by_user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("playbook_id", "step_order", name="uq_playbookapproval_playbook_step"),
    )
    op.create_index("ix_playbookapproval_id", "playbookapproval", ["id"], unique=False)
    op.create_index("ix_playbookapproval_client_id", "playbookapproval", ["client_id"], unique=False)
    op.create_index("ix_playbookapproval_playbook_id", "playbookapproval", ["playbook_id"], unique=False)
    op.create_index("ix_playbookapproval_step_order", "playbookapproval", ["step_order"], unique=False)
    op.create_index("ix_playbookapproval_status", "playbookapproval", ["status"], unique=False)
    op.create_index("ix_playbookapproval_owner_user_id", "playbookapproval", ["owner_user_id"], unique=False)
    op.create_index("ix_playbookapproval_decided_by_user_id", "playbookapproval", ["decided_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_playbookapproval_decided_by_user_id", table_name="playbookapproval")
    op.drop_index("ix_playbookapproval_owner_user_id", table_name="playbookapproval")
    op.drop_index("ix_playbookapproval_status", table_name="playbookapproval")
    op.drop_index("ix_playbookapproval_step_order", table_name="playbookapproval")
    op.drop_index("ix_playbookapproval_playbook_id", table_name="playbookapproval")
    op.drop_index("ix_playbookapproval_client_id", table_name="playbookapproval")
    op.drop_index("ix_playbookapproval_id", table_name="playbookapproval")
    op.drop_table("playbookapproval")

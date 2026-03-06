"""workflow tracking

Revision ID: 20260307_0003
Revises: 20260306_0002
Create Date: 2026-03-07 10:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260307_0003"
down_revision = "20260306_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "playbookcomment",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("playbook_id", sa.String(), sa.ForeignKey("playbook.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("author_user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("comment", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_playbookcomment_id", "playbookcomment", ["id"], unique=False)
    op.create_index("ix_playbookcomment_client_id", "playbookcomment", ["client_id"], unique=False)
    op.create_index("ix_playbookcomment_playbook_id", "playbookcomment", ["playbook_id"], unique=False)
    op.create_index("ix_playbookcomment_event_id", "playbookcomment", ["event_id"], unique=False)
    op.create_index("ix_playbookcomment_author_user_id", "playbookcomment", ["author_user_id"], unique=False)

    op.create_table(
        "incidentoutcome",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("playbook_id", sa.String(), sa.ForeignKey("playbook.id"), nullable=True),
        sa.Column("owner_user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("actions_taken", sa.JSON(), nullable=False),
        sa.Column("eta_recovery_hours", sa.Integer(), nullable=True),
        sa.Column("service_level_impact_pct", sa.Float(), nullable=True),
        sa.Column("margin_impact_pct", sa.Float(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_incidentoutcome_id", "incidentoutcome", ["id"], unique=False)
    op.create_index("ix_incidentoutcome_client_id", "incidentoutcome", ["client_id"], unique=False)
    op.create_index("ix_incidentoutcome_event_id", "incidentoutcome", ["event_id"], unique=False)
    op.create_index("ix_incidentoutcome_playbook_id", "incidentoutcome", ["playbook_id"], unique=False)
    op.create_index("ix_incidentoutcome_owner_user_id", "incidentoutcome", ["owner_user_id"], unique=False)
    op.create_index("ix_incidentoutcome_status", "incidentoutcome", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_incidentoutcome_status", table_name="incidentoutcome")
    op.drop_index("ix_incidentoutcome_owner_user_id", table_name="incidentoutcome")
    op.drop_index("ix_incidentoutcome_playbook_id", table_name="incidentoutcome")
    op.drop_index("ix_incidentoutcome_event_id", table_name="incidentoutcome")
    op.drop_index("ix_incidentoutcome_client_id", table_name="incidentoutcome")
    op.drop_index("ix_incidentoutcome_id", table_name="incidentoutcome")
    op.drop_table("incidentoutcome")

    op.drop_index("ix_playbookcomment_author_user_id", table_name="playbookcomment")
    op.drop_index("ix_playbookcomment_event_id", table_name="playbookcomment")
    op.drop_index("ix_playbookcomment_playbook_id", table_name="playbookcomment")
    op.drop_index("ix_playbookcomment_client_id", table_name="playbookcomment")
    op.drop_index("ix_playbookcomment_id", table_name="playbookcomment")
    op.drop_table("playbookcomment")

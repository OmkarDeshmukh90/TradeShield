"""client specific recommendations

Revision ID: 20260307_0004
Revises: 20260307_0003
Create Date: 2026-03-07 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260307_0004"
down_revision = "20260307_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("client") as batch_op:
        batch_op.add_column(sa.Column("supply_map_version", sa.Integer(), nullable=False, server_default="1"))

    with op.batch_alter_table("impactassessment") as batch_op:
        batch_op.add_column(sa.Column("supply_map_version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("event_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("override_applied", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("override_notes", sa.String(), nullable=False, server_default=""))
        batch_op.create_index("ix_impactassessment_supply_map_version", ["supply_map_version"], unique=False)
        batch_op.create_index("ix_impactassessment_event_updated_at", ["event_updated_at"], unique=False)

    with op.batch_alter_table("playbook") as batch_op:
        batch_op.add_column(sa.Column("supply_map_version", sa.Integer(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("event_updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("override_applied", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("override_notes", sa.String(), nullable=False, server_default=""))
        batch_op.create_index("ix_playbook_supply_map_version", ["supply_map_version"], unique=False)
        batch_op.create_index("ix_playbook_event_updated_at", ["event_updated_at"], unique=False)

    op.create_table(
        "recommendationoverride",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("analyst_user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("lead_time_delta_days", sa.Float(), nullable=True),
        sa.Column("cost_delta_pct", sa.Float(), nullable=True),
        sa.Column("revenue_risk_band", sa.String(), nullable=True),
        sa.Column("recommended_option", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("analyst_note", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "event_id", name="uq_recommendationoverride_client_event"),
    )
    op.create_index("ix_recommendationoverride_id", "recommendationoverride", ["id"], unique=False)
    op.create_index("ix_recommendationoverride_client_id", "recommendationoverride", ["client_id"], unique=False)
    op.create_index("ix_recommendationoverride_event_id", "recommendationoverride", ["event_id"], unique=False)
    op.create_index("ix_recommendationoverride_analyst_user_id", "recommendationoverride", ["analyst_user_id"], unique=False)
    op.create_index("ix_recommendationoverride_is_active", "recommendationoverride", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recommendationoverride_is_active", table_name="recommendationoverride")
    op.drop_index("ix_recommendationoverride_analyst_user_id", table_name="recommendationoverride")
    op.drop_index("ix_recommendationoverride_event_id", table_name="recommendationoverride")
    op.drop_index("ix_recommendationoverride_client_id", table_name="recommendationoverride")
    op.drop_index("ix_recommendationoverride_id", table_name="recommendationoverride")
    op.drop_table("recommendationoverride")

    with op.batch_alter_table("playbook") as batch_op:
        batch_op.drop_index("ix_playbook_event_updated_at")
        batch_op.drop_index("ix_playbook_supply_map_version")
        batch_op.drop_column("override_notes")
        batch_op.drop_column("override_applied")
        batch_op.drop_column("event_updated_at")
        batch_op.drop_column("supply_map_version")

    with op.batch_alter_table("impactassessment") as batch_op:
        batch_op.drop_index("ix_impactassessment_event_updated_at")
        batch_op.drop_index("ix_impactassessment_supply_map_version")
        batch_op.drop_column("override_notes")
        batch_op.drop_column("override_applied")
        batch_op.drop_column("event_updated_at")
        batch_op.drop_column("supply_map_version")

    with op.batch_alter_table("client") as batch_op:
        batch_op.drop_column("supply_map_version")

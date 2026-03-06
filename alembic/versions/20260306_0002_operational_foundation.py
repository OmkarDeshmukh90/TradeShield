"""operational foundation

Revision ID: 20260306_0002
Revises: 20260306_0001
Create Date: 2026-03-06 01:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260306_0002"
down_revision = "20260306_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("client") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("supplier") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("lane") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("skugroup") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("event") as batch_op:
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.add_column(sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.create_index("ix_event_last_seen_at", ["last_seen_at"], unique=False)

    with op.batch_alter_table("app_user") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("impactassessment") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("playbook") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("alertsubscription") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))

    with op.batch_alter_table("alertdelivery") as batch_op:
        batch_op.add_column(sa.Column("client_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("channel", sa.String(), nullable=False, server_default="dashboard"))
        batch_op.add_column(sa.Column("target", sa.String(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"))
        )
        batch_op.add_column(sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
        batch_op.create_foreign_key("fk_alertdelivery_client_id_client", "client", ["client_id"], ["id"])
        batch_op.create_index("ix_alertdelivery_client_id", ["client_id"], unique=False)
        batch_op.create_index("ix_alertdelivery_channel", ["channel"], unique=False)
        batch_op.create_index("ix_alertdelivery_status", ["status"], unique=False)
        batch_op.create_index("ix_alertdelivery_next_attempt_at", ["next_attempt_at"], unique=False)
        batch_op.create_unique_constraint("uq_alertdelivery_subscription_event", ["subscription_id", "event_id"])

    op.create_table(
        "ingestionrun",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("trigger", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("queued_alerts", sa.Integer(), nullable=False),
        sa.Column("connector_health", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ingestionrun_id", "ingestionrun", ["id"], unique=False)
    op.create_index("ix_ingestionrun_trigger", "ingestionrun", ["trigger"], unique=False)
    op.create_index("ix_ingestionrun_status", "ingestionrun", ["status"], unique=False)
    op.create_index("ix_ingestionrun_started_at", "ingestionrun", ["started_at"], unique=False)

    op.create_table(
        "sourcehealth",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("last_run_status", sa.String(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_name", name="uq_sourcehealth_source_name"),
    )
    op.create_index("ix_sourcehealth_id", "sourcehealth", ["id"], unique=False)
    op.create_index("ix_sourcehealth_source_name", "sourcehealth", ["source_name"], unique=False)
    op.create_index("ix_sourcehealth_last_run_status", "sourcehealth", ["last_run_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sourcehealth_last_run_status", table_name="sourcehealth")
    op.drop_index("ix_sourcehealth_source_name", table_name="sourcehealth")
    op.drop_index("ix_sourcehealth_id", table_name="sourcehealth")
    op.drop_table("sourcehealth")

    op.drop_index("ix_ingestionrun_started_at", table_name="ingestionrun")
    op.drop_index("ix_ingestionrun_status", table_name="ingestionrun")
    op.drop_index("ix_ingestionrun_trigger", table_name="ingestionrun")
    op.drop_index("ix_ingestionrun_id", table_name="ingestionrun")
    op.drop_table("ingestionrun")

    with op.batch_alter_table("alertdelivery") as batch_op:
        batch_op.drop_constraint("uq_alertdelivery_subscription_event", type_="unique")
        batch_op.drop_constraint("fk_alertdelivery_client_id_client", type_="foreignkey")
        batch_op.drop_index("ix_alertdelivery_next_attempt_at")
        batch_op.drop_index("ix_alertdelivery_status")
        batch_op.drop_index("ix_alertdelivery_channel")
        batch_op.drop_index("ix_alertdelivery_client_id")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("last_error")
        batch_op.drop_column("delivered_at")
        batch_op.drop_column("next_attempt_at")
        batch_op.drop_column("attempt_count")
        batch_op.drop_column("target")
        batch_op.drop_column("channel")
        batch_op.drop_column("client_id")

    with op.batch_alter_table("alertsubscription") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("playbook") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("impactassessment") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("app_user") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("event") as batch_op:
        batch_op.drop_index("ix_event_last_seen_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("duplicate_count")
        batch_op.drop_column("last_seen_at")

    with op.batch_alter_table("skugroup") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("lane") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("supplier") as batch_op:
        batch_op.drop_column("updated_at")

    with op.batch_alter_table("client") as batch_op:
        batch_op.drop_column("updated_at")

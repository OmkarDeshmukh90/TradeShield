"""product foundation

Revision ID: 20260306_0001
Revises:
Create Date: 2026-03-06 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260306_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("industry", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_client_id", "client", ["id"], unique=False)
    op.create_index("ix_client_industry", "client", ["industry"], unique=False)
    op.create_index("ix_client_name", "client", ["name"], unique=False)

    op.create_table(
        "event",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_event_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("geos", sa.JSON(), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("industry_tags", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fingerprint", name="uq_event_fingerprint"),
    )
    op.create_index("ix_event_id", "event", ["id"], unique=False)
    op.create_index("ix_event_source", "event", ["source"], unique=False)
    op.create_index("ix_event_source_event_id", "event", ["source_event_id"], unique=False)
    op.create_index("ix_event_type", "event", ["type"], unique=False)
    op.create_index("ix_event_occurred_at", "event", ["occurred_at"], unique=False)
    op.create_index("ix_event_detected_at", "event", ["detected_at"], unique=False)
    op.create_index("ix_event_fingerprint", "event", ["fingerprint"], unique=True)

    op.create_table(
        "app_user",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_user_email"),
    )
    op.create_index("ix_app_user_id", "app_user", ["id"], unique=False)
    op.create_index("ix_app_user_client_id", "app_user", ["client_id"], unique=False)
    op.create_index("ix_app_user_email", "app_user", ["email"], unique=False)
    op.create_index("ix_app_user_role", "app_user", ["role"], unique=False)

    op.create_table(
        "supplier",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country", sa.String(), nullable=False),
        sa.Column("region", sa.String(), nullable=False),
        sa.Column("commodity", sa.String(), nullable=False),
        sa.Column("criticality", sa.Float(), nullable=False),
        sa.Column("substitution_score", sa.Float(), nullable=False),
        sa.Column("lead_time_sensitivity", sa.Float(), nullable=False),
        sa.Column("inventory_buffer_days", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "name", "country", "commodity", name="uq_supplier_client_key"),
    )
    op.create_index("ix_supplier_client_id", "supplier", ["client_id"], unique=False)
    op.create_index("ix_supplier_name", "supplier", ["name"], unique=False)

    op.create_table(
        "lane",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("origin", sa.String(), nullable=False),
        sa.Column("destination", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("chokepoint", sa.String(), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "origin", "destination", "mode", "chokepoint", name="uq_lane_client_key"),
    )
    op.create_index("ix_lane_client_id", "lane", ["client_id"], unique=False)

    op.create_table(
        "skugroup",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("monthly_volume", sa.Float(), nullable=False),
        sa.Column("margin_sensitivity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("client_id", "name", "category", name="uq_skugroup_client_key"),
    )
    op.create_index("ix_skugroup_client_id", "skugroup", ["client_id"], unique=False)

    op.create_table(
        "exposure",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("supplier_id", sa.String(), sa.ForeignKey("supplier.id"), nullable=True),
        sa.Column("lane_id", sa.String(), sa.ForeignKey("lane.id"), nullable=True),
        sa.Column("sku_group_id", sa.String(), sa.ForeignKey("skugroup.id"), nullable=True),
        sa.Column("exposure_score", sa.Float(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("notes", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_exposure_client_id", "exposure", ["client_id"], unique=False)
    op.create_index("ix_exposure_event_id", "exposure", ["event_id"], unique=False)
    op.create_index("ix_exposure_supplier_id", "exposure", ["supplier_id"], unique=False)
    op.create_index("ix_exposure_lane_id", "exposure", ["lane_id"], unique=False)
    op.create_index("ix_exposure_sku_group_id", "exposure", ["sku_group_id"], unique=False)

    op.create_table(
        "impactassessment",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("lead_time_delta_days", sa.Float(), nullable=False),
        sa.Column("cost_delta_pct", sa.Float(), nullable=False),
        sa.Column("revenue_risk_band", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_impactassessment_client_id", "impactassessment", ["client_id"], unique=False)
    op.create_index("ix_impactassessment_event_id", "impactassessment", ["event_id"], unique=False)

    op.create_table(
        "playbook",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("recommended_option", sa.String(), nullable=False),
        sa.Column("approval_steps", sa.JSON(), nullable=False),
        sa.Column("owner_assignments", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_playbook_id", "playbook", ["id"], unique=False)
    op.create_index("ix_playbook_client_id", "playbook", ["client_id"], unique=False)
    op.create_index("ix_playbook_event_id", "playbook", ["event_id"], unique=False)

    op.create_table(
        "alertsubscription",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("target", sa.String(), nullable=False),
        sa.Column("min_severity", sa.Float(), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("industries", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alertsubscription_id", "alertsubscription", ["id"], unique=False)
    op.create_index("ix_alertsubscription_client_id", "alertsubscription", ["client_id"], unique=False)
    op.create_index("ix_alertsubscription_channel", "alertsubscription", ["channel"], unique=False)

    op.create_table(
        "alertdelivery",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("subscription_id", sa.String(), sa.ForeignKey("alertsubscription.id"), nullable=False),
        sa.Column("event_id", sa.String(), sa.ForeignKey("event.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("channel_response", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alertdelivery_subscription_id", "alertdelivery", ["subscription_id"], unique=False)
    op.create_index("ix_alertdelivery_event_id", "alertdelivery", ["event_id"], unique=False)

    op.create_table(
        "auditlog",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.String(), sa.ForeignKey("client.id"), nullable=True),
        sa.Column("actor_user_id", sa.String(), sa.ForeignKey("app_user.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auditlog_id", "auditlog", ["id"], unique=False)
    op.create_index("ix_auditlog_client_id", "auditlog", ["client_id"], unique=False)
    op.create_index("ix_auditlog_actor_user_id", "auditlog", ["actor_user_id"], unique=False)
    op.create_index("ix_auditlog_action", "auditlog", ["action"], unique=False)
    op.create_index("ix_auditlog_entity_type", "auditlog", ["entity_type"], unique=False)
    op.create_index("ix_auditlog_entity_id", "auditlog", ["entity_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_auditlog_entity_id", table_name="auditlog")
    op.drop_index("ix_auditlog_entity_type", table_name="auditlog")
    op.drop_index("ix_auditlog_action", table_name="auditlog")
    op.drop_index("ix_auditlog_actor_user_id", table_name="auditlog")
    op.drop_index("ix_auditlog_client_id", table_name="auditlog")
    op.drop_index("ix_auditlog_id", table_name="auditlog")
    op.drop_table("auditlog")

    op.drop_index("ix_alertdelivery_event_id", table_name="alertdelivery")
    op.drop_index("ix_alertdelivery_subscription_id", table_name="alertdelivery")
    op.drop_table("alertdelivery")

    op.drop_index("ix_alertsubscription_channel", table_name="alertsubscription")
    op.drop_index("ix_alertsubscription_client_id", table_name="alertsubscription")
    op.drop_index("ix_alertsubscription_id", table_name="alertsubscription")
    op.drop_table("alertsubscription")

    op.drop_index("ix_playbook_event_id", table_name="playbook")
    op.drop_index("ix_playbook_client_id", table_name="playbook")
    op.drop_index("ix_playbook_id", table_name="playbook")
    op.drop_table("playbook")

    op.drop_index("ix_impactassessment_event_id", table_name="impactassessment")
    op.drop_index("ix_impactassessment_client_id", table_name="impactassessment")
    op.drop_table("impactassessment")

    op.drop_index("ix_exposure_sku_group_id", table_name="exposure")
    op.drop_index("ix_exposure_lane_id", table_name="exposure")
    op.drop_index("ix_exposure_supplier_id", table_name="exposure")
    op.drop_index("ix_exposure_event_id", table_name="exposure")
    op.drop_index("ix_exposure_client_id", table_name="exposure")
    op.drop_table("exposure")

    op.drop_index("ix_skugroup_client_id", table_name="skugroup")
    op.drop_table("skugroup")

    op.drop_index("ix_lane_client_id", table_name="lane")
    op.drop_table("lane")

    op.drop_index("ix_supplier_name", table_name="supplier")
    op.drop_index("ix_supplier_client_id", table_name="supplier")
    op.drop_table("supplier")

    op.drop_index("ix_app_user_role", table_name="app_user")
    op.drop_index("ix_app_user_email", table_name="app_user")
    op.drop_index("ix_app_user_client_id", table_name="app_user")
    op.drop_index("ix_app_user_id", table_name="app_user")
    op.drop_table("app_user")

    op.drop_index("ix_event_fingerprint", table_name="event")
    op.drop_index("ix_event_detected_at", table_name="event")
    op.drop_index("ix_event_occurred_at", table_name="event")
    op.drop_index("ix_event_type", table_name="event")
    op.drop_index("ix_event_source_event_id", table_name="event")
    op.drop_index("ix_event_source", table_name="event")
    op.drop_index("ix_event_id", table_name="event")
    op.drop_table("event")

    op.drop_index("ix_client_name", table_name="client")
    op.drop_index("ix_client_industry", table_name="client")
    op.drop_index("ix_client_id", table_name="client")
    op.drop_table("client")

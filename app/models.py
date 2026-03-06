from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlalchemy.schema import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.utils import now_utc


class Client(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    name: str = Field(index=True)
    industry: str = Field(index=True)
    country: str = Field(default="India")
    preferences: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    supply_map_version: int = Field(default=1, nullable=False)
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class Supplier(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("client_id", "name", "country", "commodity", name="uq_supplier_client_key"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    name: str = Field(index=True)
    country: str
    region: str
    commodity: str
    criticality: float = 0.5
    substitution_score: float = 0.5
    lead_time_sensitivity: float = 0.5
    inventory_buffer_days: float = 14.0
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class Lane(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("client_id", "origin", "destination", "mode", "chokepoint", name="uq_lane_client_key"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    origin: str
    destination: str
    mode: str = "sea"
    chokepoint: str | None = None
    importance: float = 0.5
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class SkuGroup(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("client_id", "name", "category", name="uq_skugroup_client_key"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    name: str
    category: str
    monthly_volume: float = 0.0
    margin_sensitivity: float = 0.5
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class Event(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("fingerprint", name="uq_event_fingerprint"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    source: str = Field(index=True)
    source_event_id: str = Field(index=True)
    fingerprint: str = Field(index=True, unique=True)
    type: str = Field(default="other", index=True)
    title: str
    description: str = ""
    occurred_at: datetime = Field(default_factory=now_utc, index=True)
    detected_at: datetime = Field(default_factory=now_utc, index=True)
    last_seen_at: datetime = Field(default_factory=now_utc, index=True)
    geos: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    entities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    severity: float = 0.4
    confidence: float = 0.6
    duplicate_count: int = 0
    evidence: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    industry_tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class User(SQLModel, table=True):
    __tablename__ = "app_user"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    full_name: str
    email: str = Field(index=True)
    role: str = Field(default="viewer", index=True)
    password_hash: str
    is_active: bool = True
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class Exposure(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    supplier_id: str | None = Field(default=None, foreign_key="supplier.id", index=True)
    lane_id: str | None = Field(default=None, foreign_key="lane.id", index=True)
    sku_group_id: str | None = Field(default=None, foreign_key="skugroup.id", index=True)
    exposure_score: float = 0.0
    relevance_score: float = 0.0
    notes: str = ""
    created_at: datetime = Field(default_factory=now_utc, nullable=False)


class ImpactAssessment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    risk_score: float = 0.0
    lead_time_delta_days: float = 0.0
    cost_delta_pct: float = 0.0
    revenue_risk_band: str = "low"
    confidence: float = 0.6
    supply_map_version: int = Field(default=1, index=True)
    event_updated_at: datetime = Field(default_factory=now_utc, index=True)
    override_applied: bool = False
    override_notes: str = ""
    rationale: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    assumptions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class Playbook(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    options: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    recommended_option: str = ""
    supply_map_version: int = Field(default=1, index=True)
    event_updated_at: datetime = Field(default_factory=now_utc, index=True)
    override_applied: bool = False
    override_notes: str = ""
    approval_steps: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    owner_assignments: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    model_version: str = "ts-risk-v1.0.0"
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class PlaybookComment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    playbook_id: str = Field(foreign_key="playbook.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    author_user_id: str = Field(foreign_key="app_user.id", index=True)
    comment: str
    created_at: datetime = Field(default_factory=now_utc, nullable=False)


class PlaybookApproval(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("playbook_id", "step_order", name="uq_playbookapproval_playbook_step"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    playbook_id: str = Field(foreign_key="playbook.id", index=True)
    step_order: int = Field(index=True)
    step_name: str
    status: str = Field(default="pending", index=True)
    owner_user_id: str | None = Field(default=None, foreign_key="app_user.id", index=True)
    decision_note: str = ""
    decided_by_user_id: str | None = Field(default=None, foreign_key="app_user.id", index=True)
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class IncidentOutcome(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    playbook_id: str | None = Field(default=None, foreign_key="playbook.id", index=True)
    owner_user_id: str | None = Field(default=None, foreign_key="app_user.id", index=True)
    status: str = Field(default="open", index=True)
    summary: str = ""
    actions_taken: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    eta_recovery_hours: int | None = None
    service_level_impact_pct: float | None = None
    margin_impact_pct: float | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class RecommendationOverride(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("client_id", "event_id", name="uq_recommendationoverride_client_event"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    analyst_user_id: str = Field(foreign_key="app_user.id", index=True)
    is_active: bool = Field(default=True, index=True)
    risk_score: float | None = None
    lead_time_delta_days: float | None = None
    cost_delta_pct: float | None = None
    revenue_risk_band: str | None = None
    recommended_option: str | None = None
    confidence: float | None = None
    analyst_note: str = ""
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class AlertSubscription(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    channel: str = Field(index=True)
    target: str
    min_severity: float = 0.5
    regions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    industries: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    active: bool = True
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class AlertDelivery(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("subscription_id", "event_id", name="uq_alertdelivery_subscription_event"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    client_id: str = Field(foreign_key="client.id", index=True)
    subscription_id: str = Field(foreign_key="alertsubscription.id", index=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    channel: str = Field(index=True)
    target: str
    status: str = Field(default="queued", index=True)
    message: str = ""
    attempt_count: int = 0
    next_attempt_at: datetime = Field(default_factory=now_utc, index=True)
    delivered_at: datetime | None = None
    last_error: str | None = None
    channel_response: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class IngestionRun(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    trigger: str = Field(default="manual", index=True)
    status: str = Field(default="running", index=True)
    started_at: datetime = Field(default_factory=now_utc, index=True)
    finished_at: datetime | None = None
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    queued_alerts: int = 0
    connector_health: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc, nullable=False)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class SourceHealth(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("source_name", name="uq_sourcehealth_source_name"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    source_name: str = Field(index=True)
    last_run_status: str = Field(default="unknown", index=True)
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    fetched_count: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    duplicate_count: int = 0
    consecutive_errors: int = 0
    backoff_until: datetime | None = Field(default=None, index=True)
    updated_at: datetime = Field(default_factory=now_utc, nullable=False)


class AuditLog(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, index=True)
    client_id: str | None = Field(default=None, foreign_key="client.id", index=True)
    actor_user_id: str | None = Field(default=None, foreign_key="app_user.id", index=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now_utc, nullable=False)

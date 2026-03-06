from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    industry: str
    country: str = "India"
    preferences: dict[str, Any] = Field(default_factory=dict)


class ClientRead(BaseModel):
    id: str
    name: str
    industry: str
    country: str
    preferences: dict[str, Any]
    supply_map_version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupplierInput(BaseModel):
    name: str
    country: str
    region: str
    commodity: str
    criticality: float = Field(default=0.5, ge=0.0, le=1.0)
    substitution_score: float = Field(default=0.5, ge=0.0, le=1.0)
    lead_time_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    inventory_buffer_days: float = Field(default=14.0, ge=0.0)


class LaneInput(BaseModel):
    origin: str
    destination: str
    mode: Literal["sea", "air", "road", "rail"] = "sea"
    chokepoint: str | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class SkuGroupInput(BaseModel):
    name: str
    category: str
    monthly_volume: float = Field(default=0.0, ge=0.0)
    margin_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)


class SupplyMapUpsertRequest(BaseModel):
    suppliers: list[SupplierInput] = Field(default_factory=list)
    lanes: list[LaneInput] = Field(default_factory=list)
    sku_groups: list[SkuGroupInput] = Field(default_factory=list)


class SupplyMapUpsertResponse(BaseModel):
    client_id: str
    suppliers_added: int
    suppliers_updated: int
    lanes_added: int
    lanes_updated: int
    sku_groups_added: int
    sku_groups_updated: int


class SupplierRead(BaseModel):
    id: str
    client_id: str
    name: str
    country: str
    region: str
    commodity: str
    criticality: float
    substitution_score: float
    lead_time_sensitivity: float
    inventory_buffer_days: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LaneRead(BaseModel):
    id: str
    client_id: str
    origin: str
    destination: str
    mode: str
    chokepoint: str | None
    importance: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkuGroupRead(BaseModel):
    id: str
    client_id: str
    name: str
    category: str
    monthly_volume: float
    margin_sensitivity: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SupplyMapRead(BaseModel):
    client_id: str
    supply_map_version: int
    suppliers: list[SupplierRead]
    lanes: list[LaneRead]
    sku_groups: list[SkuGroupRead]


class SupplyMapCsvImportRequest(BaseModel):
    suppliers_csv: str = Field(min_length=1)
    lanes_csv: str = Field(min_length=1)
    sku_groups_csv: str = Field(min_length=1)


class UserRead(BaseModel):
    id: str
    client_id: str
    full_name: str
    email: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    role: Literal["admin", "analyst", "viewer"] = "viewer"
    password: str = Field(min_length=10, max_length=128)


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Literal["admin", "analyst", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=10, max_length=128)


class AuthRegisterRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    industry: str
    country: str = "India"
    preferences: dict[str, Any] = Field(default_factory=dict)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=128)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=10, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    client: ClientRead
    user: UserRead


class SessionRead(BaseModel):
    client: ClientRead
    user: UserRead


class Evidence(BaseModel):
    title: str
    url: str
    source: str


class EventRead(BaseModel):
    id: str
    source: str
    source_event_id: str
    type: str
    title: str
    description: str
    occurred_at: datetime
    detected_at: datetime
    last_seen_at: datetime
    geos: list[str]
    entities: list[str]
    severity: float
    confidence: float
    duplicate_count: int
    evidence: list[dict[str, Any]]
    industry_tags: list[str]
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExposureRead(BaseModel):
    id: str
    client_id: str
    event_id: str
    supplier_id: str | None
    lane_id: str | None
    sku_group_id: str | None
    exposure_score: float
    relevance_score: float
    notes: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RiskScoreItem(BaseModel):
    event_id: str
    event_title: str
    event_type: str
    risk_score: float
    confidence: float
    revenue_risk_band: str
    override_applied: bool = False
    created_at: datetime


class RiskScoresResponse(BaseModel):
    client_id: str
    window_hours: int
    average_risk_score: float
    max_risk_score: float
    items: list[RiskScoreItem]


class PlaybookGenerateRequest(BaseModel):
    event_id: str


class PlaybookRead(BaseModel):
    id: str
    client_id: str
    event_id: str
    options: list[dict[str, Any]]
    recommended_option: str
    override_applied: bool
    override_notes: str
    approval_steps: list[str]
    owner_assignments: dict[str, str]
    model_version: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlaybookCommentCreate(BaseModel):
    comment: str = Field(min_length=2, max_length=2000)


class PlaybookCommentRead(BaseModel):
    id: str
    client_id: str
    playbook_id: str
    event_id: str
    author_user_id: str
    comment: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaybookApprovalRead(BaseModel):
    id: str
    client_id: str
    playbook_id: str
    step_order: int
    step_name: str
    status: str
    owner_user_id: str | None
    decision_note: str
    decided_by_user_id: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlaybookApprovalUpdateRequest(BaseModel):
    status: Literal["pending", "approved", "rejected"]
    owner_user_id: str | None = None
    decision_note: str = Field(default="", max_length=2000)


class IncidentOutcomeUpsertRequest(BaseModel):
    playbook_id: str | None = None
    owner_user_id: str | None = None
    status: Literal["open", "monitoring", "mitigated", "resolved"] = "open"
    summary: str = Field(default="", max_length=2000)
    actions_taken: list[str] = Field(default_factory=list)
    eta_recovery_hours: int | None = Field(default=None, ge=0)
    service_level_impact_pct: float | None = None
    margin_impact_pct: float | None = None
    completed_at: datetime | None = None


class IncidentOutcomeRead(BaseModel):
    id: str
    client_id: str
    event_id: str
    playbook_id: str | None
    owner_user_id: str | None
    status: str
    summary: str
    actions_taken: list[str]
    eta_recovery_hours: int | None
    service_level_impact_pct: float | None
    margin_impact_pct: float | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecommendationOverrideUpsertRequest(BaseModel):
    is_active: bool = True
    risk_score: float | None = Field(default=None, ge=0.0, le=1.0)
    lead_time_delta_days: float | None = Field(default=None, ge=0.0)
    cost_delta_pct: float | None = Field(default=None, ge=0.0)
    revenue_risk_band: Literal["low", "medium", "high", "critical"] | None = None
    recommended_option: Literal["continuity-first", "cost-balanced", "margin-protect"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    analyst_note: str = Field(default="", max_length=2000)


class RecommendationOverrideRead(BaseModel):
    id: str
    client_id: str
    event_id: str
    analyst_user_id: str
    is_active: bool
    risk_score: float | None
    lead_time_delta_days: float | None
    cost_delta_pct: float | None
    revenue_risk_band: str | None
    recommended_option: str | None
    confidence: float | None
    analyst_note: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertSubscriptionCreate(BaseModel):
    channel: Literal["email", "whatsapp", "dashboard", "webhook"]
    target: str
    min_severity: float = Field(default=0.5, ge=0.0, le=1.0)
    regions: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    active: bool = True


class AlertSubscriptionUpdate(BaseModel):
    target: str | None = None
    min_severity: float | None = Field(default=None, ge=0.0, le=1.0)
    regions: list[str] | None = None
    industries: list[str] | None = None
    active: bool | None = None


class AlertSubscriptionRead(BaseModel):
    id: str
    client_id: str
    channel: str
    target: str
    min_severity: float
    regions: list[str]
    industries: list[str]
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertDeliveryRead(BaseModel):
    id: str
    client_id: str
    subscription_id: str
    event_id: str
    channel: str
    target: str
    status: str
    message: str
    attempt_count: int
    next_attempt_at: datetime
    delivered_at: datetime | None
    last_error: str | None
    channel_response: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertDispatchResponse(BaseModel):
    processed_count: int
    delivered_count: int
    retry_count: int
    blocked_count: int
    failed_count: int


class WebhookTestRequest(BaseModel):
    url: str
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookTestResponse(BaseModel):
    status_code: int
    delivered: bool
    response_excerpt: str


class SourceHealthRead(BaseModel):
    id: str
    source_name: str
    last_run_status: str
    last_run_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    fetched_count: int
    inserted_count: int
    updated_count: int
    duplicate_count: int
    consecutive_errors: int
    backoff_until: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestionRunRead(BaseModel):
    id: str
    trigger: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    inserted_count: int
    updated_count: int
    duplicate_count: int
    queued_alerts: int
    connector_health: dict[str, Any]
    error_summary: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IngestionRunResponse(BaseModel):
    run_id: str
    status: str
    inserted_count: int
    updated_count: int
    fetched_count: int
    duplicate_count: int
    queued_alerts: int
    connector_health: dict[str, Any]


class AuditLogRead(BaseModel):
    id: str
    client_id: str | None
    actor_user_id: str | None
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class OpsOverviewResponse(BaseModel):
    latest_run: IngestionRunRead | None
    source_health: list[SourceHealthRead]
    queued_alerts: int
    retrying_alerts: int
    failed_alerts: int
    active_users: int


class OpsMetricsResponse(BaseModel):
    run_count_24h: int
    success_rate_24h: float
    avg_run_duration_seconds_24h: float
    p95_run_duration_seconds_24h: float
    events_inserted_24h: int
    events_updated_24h: int
    queued_alerts_24h: int
    delivered_alerts_24h: int
    failed_alerts_24h: int
    retrying_alerts_current: int


class DashboardSummary(BaseModel):
    client_name: str
    open_events: int
    average_severity: float
    highest_risk_score: float
    latest_events: list[EventRead]


class ExplainabilityFactor(BaseModel):
    name: str
    value: float
    weight: float
    contribution: float


class ExplainabilityEstimate(BaseModel):
    risk_score: float
    lead_time_delta_days: float
    cost_delta_pct: float
    confidence: float
    revenue_risk_band: str


class ExplainabilityDelta(BaseModel):
    risk_score_delta: float
    lead_time_delta_days_delta: float
    cost_delta_pct_delta: float
    confidence_delta: float


class ExplainabilityRead(BaseModel):
    event_id: str
    client_id: str
    factors: list[ExplainabilityFactor]
    base_estimate: ExplainabilityEstimate
    override_estimate: ExplainabilityEstimate | None
    delta: ExplainabilityDelta | None
    top_rationale: list[str]
    assumptions: list[str]
    confidence_note: str


class DemoStatusRead(BaseModel):
    demo_mode: bool
    demo_scenario: Literal["tariff", "congestion", "all"]


class DemoStatusUpdate(BaseModel):
    demo_mode: bool
    demo_scenario: Literal["tariff", "congestion", "all"] = "all"

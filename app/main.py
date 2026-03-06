from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.config import get_cors_origins, settings
from app.constants import INDUSTRIES
from app.database import engine, get_session, init_db
from app.dependencies import Principal, get_current_principal, require_client_access, require_role
from app.logging_config import configure_logging
from app.models import (
    AlertDelivery,
    AlertSubscription,
    AuditLog,
    Client,
    Event,
    ImpactAssessment,
    IngestionRun,
    IncidentOutcome,
    Lane,
    Playbook,
    PlaybookApproval,
    PlaybookComment,
    RecommendationOverride,
    SkuGroup,
    SourceHealth,
    Supplier,
    User,
)
from app.schemas import (
    AlertDeliveryRead,
    AlertDispatchResponse,
    AlertSubscriptionCreate,
    AlertSubscriptionRead,
    AlertSubscriptionUpdate,
    AuditLogRead,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthResponse,
    ClientRead,
    DashboardSummary,
    DemoStatusRead,
    DemoStatusUpdate,
    ExplainabilityRead,
    EventRead,
    ExposureRead,
    IngestionRunRead,
    IngestionRunResponse,
    IncidentOutcomeRead,
    IncidentOutcomeUpsertRequest,
    OpsOverviewResponse,
    OpsMetricsResponse,
    PlaybookCommentCreate,
    PlaybookCommentRead,
    PlaybookApprovalRead,
    PlaybookApprovalUpdateRequest,
    PlaybookGenerateRequest,
    PlaybookRead,
    RiskScoreItem,
    RiskScoresResponse,
    RecommendationOverrideRead,
    RecommendationOverrideUpsertRequest,
    SessionRead,
    SourceHealthRead,
    SupplyMapRead,
    SupplyMapUpsertRequest,
    SupplyMapUpsertResponse,
    SupplyMapCsvImportRequest,
    SupplierRead,
    LaneRead,
    SkuGroupRead,
    UserCreateRequest,
    UserRead,
    UserUpdateRequest,
    WebhookTestRequest,
    WebhookTestResponse,
)
from app.security import create_access_token, hash_password, validate_callback_url, validate_password_strength, verify_password
from app.services.alerts import process_pending_alerts
from app.services.audit import log_audit_event
from app.services.ingestion import IngestionService
from app.services.playbooks import ensure_playbook_approvals, generate_playbook
from app.services.scoring import build_explainability, client_risk_snapshot, ensure_exposures, ensure_impact_assessment
from app.services.csv_import import build_supply_map_request_from_csv
from app.services.supply_map import upsert_supply_map
from app.utils import new_correlation_id, now_utc, set_correlation_id

static_dir = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="India-first supply chain disruption intelligence platform",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs and settings.app_env != "prod" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.enable_docs and settings.app_env != "prod" else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    incoming = request.headers.get("X-Correlation-Id", "").strip()
    correlation_id = incoming or new_correlation_id()
    set_correlation_id(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response


def _require_event(session: Session, event_id: str) -> Event:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
    return event


def _build_auth_response(user: User, client: Client, token: str) -> AuthResponse:
    return AuthResponse(
        access_token=token,
        token_type="bearer",
        client=ClientRead.model_validate(client),
        user=UserRead.model_validate(user),
    )


def _build_session_read(user: User, client: Client) -> SessionRead:
    return SessionRead(
        client=ClientRead.model_validate(client),
        user=UserRead.model_validate(user),
    )


def _workspace_users(session: Session, client_id: str) -> list[User]:
    return session.exec(select(User).where(User.client_id == client_id).order_by(User.created_at.asc())).all()


def _require_workspace_user(session: Session, principal: Principal, user_id: str) -> User:
    user = session.get(User, user_id)
    if not user or user.client_id != principal.client.id:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def _require_workspace_playbook(session: Session, principal: Principal, playbook_id: str) -> Playbook:
    playbook = session.get(Playbook, playbook_id)
    if not playbook or playbook.client_id != principal.client.id:
        raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")
    return playbook


def _require_workspace_subscription(session: Session, principal: Principal, subscription_id: str) -> AlertSubscription:
    subscription = session.get(AlertSubscription, subscription_id)
    if not subscription or subscription.client_id != principal.client.id:
        raise HTTPException(status_code=404, detail=f"Alert subscription {subscription_id} not found")
    return subscription


def _require_workspace_approval(
    session: Session,
    principal: Principal,
    playbook_id: str,
    approval_id: str,
) -> PlaybookApproval:
    approval = session.get(PlaybookApproval, approval_id)
    if not approval or approval.client_id != principal.client.id or approval.playbook_id != playbook_id:
        raise HTTPException(status_code=404, detail=f"Approval step {approval_id} not found")
    return approval


def _active_admin_count(session: Session, client_id: str) -> int:
    users = session.exec(
        select(User).where(User.client_id == client_id, User.role == "admin", User.is_active.is_(True))
    ).all()
    return len(users)


def _list_alert_deliveries(session: Session, client_id: str, status_filter: str | None = None, limit: int = 100) -> list[AlertDelivery]:
    deliveries = session.exec(
        select(AlertDelivery).where(AlertDelivery.client_id == client_id).order_by(AlertDelivery.created_at.desc())
    ).all()
    if status_filter:
        deliveries = [delivery for delivery in deliveries if delivery.status == status_filter]
    return deliveries[:limit]


def _is_recent(ts: datetime | None, minutes: int) -> bool:
    if not ts:
        return False
    reference = now_utc()
    if ts.tzinfo is None and reference.tzinfo is not None:
        return ts >= reference.replace(tzinfo=None) - timedelta(minutes=minutes)
    if ts.tzinfo is not None and reference.tzinfo is None:
        return ts.replace(tzinfo=None) >= reference - timedelta(minutes=minutes)
    return ts >= reference - timedelta(minutes=minutes)


@app.get("/")
def get_dashboard() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/ops")
def get_ops_page() -> FileResponse:
    return FileResponse(static_dir / "ops.html")


@app.get("/healthz")
def healthz(session: Session = Depends(get_session)) -> dict:
    db_status = "ok"
    try:
        session.exec(select(Client).limit(1)).all()
    except Exception:  # noqa: BLE001
        db_status = "error"

    latest_run = session.exec(select(IngestionRun).order_by(IngestionRun.started_at.desc())).first()
    if not latest_run:
        ingestion_status = "not_started"
    elif _is_recent(latest_run.finished_at, settings.health_ingestion_stale_minutes):
        ingestion_status = latest_run.status
    else:
        ingestion_status = "stale"

    overall = "ok" if db_status == "ok" and ingestion_status not in {"error", "failed"} else "degraded"
    return {
        "status": overall,
        "db_status": db_status,
        "ingestion_status": ingestion_status,
        "env": settings.app_env,
        "ts": now_utc().isoformat(),
    }


@app.get(f"{settings.api_prefix}/industries")
def list_industries() -> dict:
    return {"industries": INDUSTRIES}


@app.get(f"{settings.api_prefix}/demo/status", response_model=DemoStatusRead)
def get_demo_status(_: Principal = Depends(require_role("admin", "analyst"))) -> DemoStatusRead:
    return DemoStatusRead(demo_mode=settings.demo_mode, demo_scenario=settings.demo_scenario)


@app.post(f"{settings.api_prefix}/demo/status", response_model=DemoStatusRead)
def update_demo_status(
    payload: DemoStatusUpdate,
    _: Principal = Depends(require_role("admin")),
) -> DemoStatusRead:
    settings.demo_mode = payload.demo_mode
    settings.demo_scenario = payload.demo_scenario
    return DemoStatusRead(demo_mode=settings.demo_mode, demo_scenario=settings.demo_scenario)


@app.post(f"{settings.api_prefix}/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register_workspace(payload: AuthRegisterRequest, session: Session = Depends(get_session)) -> AuthResponse:
    existing = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    validate_password_strength(payload.password)
    current_time = now_utc()
    client = Client(
        name=payload.company_name,
        industry=payload.industry,
        country=payload.country,
        preferences=payload.preferences,
        updated_at=current_time,
    )
    session.add(client)
    session.commit()
    session.refresh(client)

    user = User(
        client_id=client.id,
        full_name=payload.full_name,
        email=payload.email.lower(),
        role="admin",
        password_hash=hash_password(payload.password),
        is_active=True,
        last_login_at=current_time,
        updated_at=current_time,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(user)
    log_audit_event(
        session,
        action="auth.register",
        entity_type="client",
        entity_id=client.id,
        actor=user,
        details={"industry": client.industry, "country": client.country},
    )
    return _build_auth_response(user, client, token)


@app.post(f"{settings.api_prefix}/auth/login", response_model=AuthResponse)
def login(payload: AuthLoginRequest, session: Session = Depends(get_session)) -> AuthResponse:
    user = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

    client = session.get(Client, user.client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Workspace is unavailable")

    user.last_login_at = now_utc()
    user.updated_at = now_utc()
    session.add(user)
    session.commit()
    session.refresh(user)

    token = create_access_token(user)
    log_audit_event(
        session,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        actor=user,
        details={"email": user.email},
    )
    return _build_auth_response(user, client, token)


@app.get(f"{settings.api_prefix}/auth/me", response_model=SessionRead)
def auth_me(principal: Principal = Depends(get_current_principal)) -> SessionRead:
    return _build_session_read(principal.user, principal.client)


@app.get(f"{settings.api_prefix}/users", response_model=list[UserRead])
def list_users(
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in _workspace_users(session, principal.client.id)]


@app.post(f"{settings.api_prefix}/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    principal: Principal = Depends(require_role("admin")),
    session: Session = Depends(get_session),
) -> UserRead:
    existing = session.exec(select(User).where(User.email == payload.email.lower())).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    validate_password_strength(payload.password)
    user = User(
        client_id=principal.client.id,
        full_name=payload.full_name,
        email=payload.email.lower(),
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=True,
        updated_at=now_utc(),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    log_audit_event(
        session,
        action="user.create",
        entity_type="user",
        entity_id=user.id,
        actor=principal.user,
        details={"role": user.role, "email": user.email},
    )
    return UserRead.model_validate(user)


@app.patch(f"{settings.api_prefix}/users/{{user_id}}", response_model=UserRead)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    principal: Principal = Depends(require_role("admin")),
    session: Session = Depends(get_session),
) -> UserRead:
    user = _require_workspace_user(session, principal, user_id)

    if payload.role and user.role == "admin" and payload.role != "admin" and _active_admin_count(session, principal.client.id) <= 1:
        raise HTTPException(status_code=422, detail="Workspace must retain at least one active admin")
    if payload.is_active is False and user.role == "admin" and _active_admin_count(session, principal.client.id) <= 1:
        raise HTTPException(status_code=422, detail="Workspace must retain at least one active admin")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password is not None:
        validate_password_strength(payload.password)
        user.password_hash = hash_password(payload.password)
    user.updated_at = now_utc()

    session.add(user)
    session.commit()
    session.refresh(user)
    log_audit_event(
        session,
        action="user.update",
        entity_type="user",
        entity_id=user.id,
        actor=principal.user,
        details=payload.model_dump(exclude_none=True, exclude={"password"}),
    )
    return UserRead.model_validate(user)


@app.get(f"{settings.api_prefix}/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> list[AuditLogRead]:
    logs = session.exec(
        select(AuditLog).where(AuditLog.client_id == principal.client.id).order_by(AuditLog.created_at.desc())
    ).all()
    return [AuditLogRead.model_validate(item) for item in logs[:limit]]


@app.post(
    f"{settings.api_prefix}/clients/{{client_id}}/supply-map",
    response_model=SupplyMapUpsertResponse,
    status_code=status.HTTP_201_CREATED,
)
def write_supply_map(
    client_id: str,
    payload: SupplyMapUpsertRequest,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> SupplyMapUpsertResponse:
    client = require_client_access(client_id, principal)
    result = upsert_supply_map(session, client_id, payload)
    client.updated_at = now_utc()
    session.add(client)
    session.commit()
    log_audit_event(
        session,
        action="supply_map.upsert",
        entity_type="client",
        entity_id=client_id,
        actor=principal.user,
        details={
            "suppliers_added": result.suppliers_added,
            "suppliers_updated": result.suppliers_updated,
            "lanes_added": result.lanes_added,
            "lanes_updated": result.lanes_updated,
            "sku_groups_added": result.sku_groups_added,
            "sku_groups_updated": result.sku_groups_updated,
        },
    )
    return result


@app.get(f"{settings.api_prefix}/clients/{{client_id}}/supply-map", response_model=SupplyMapRead)
def read_supply_map(
    client_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> SupplyMapRead:
    client = require_client_access(client_id, principal)
    suppliers = session.exec(select(Supplier).where(Supplier.client_id == client_id).order_by(Supplier.name.asc())).all()
    lanes = session.exec(select(Lane).where(Lane.client_id == client_id).order_by(Lane.origin.asc())).all()
    sku_groups = session.exec(select(SkuGroup).where(SkuGroup.client_id == client_id).order_by(SkuGroup.name.asc())).all()
    return SupplyMapRead(
        client_id=client_id,
        supply_map_version=client.supply_map_version,
        suppliers=[SupplierRead.model_validate(item) for item in suppliers],
        lanes=[LaneRead.model_validate(item) for item in lanes],
        sku_groups=[SkuGroupRead.model_validate(item) for item in sku_groups],
    )


@app.post(
    f"{settings.api_prefix}/clients/{{client_id}}/supply-map/import-csv",
    response_model=SupplyMapUpsertResponse,
    status_code=status.HTTP_201_CREATED,
)
def import_supply_map_csv(
    client_id: str,
    payload: SupplyMapCsvImportRequest,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> SupplyMapUpsertResponse:
    client = require_client_access(client_id, principal)
    upsert_payload = build_supply_map_request_from_csv(payload)
    result = upsert_supply_map(session, client_id, upsert_payload)
    client.updated_at = now_utc()
    session.add(client)
    session.commit()
    log_audit_event(
        session,
        action="supply_map.import_csv",
        entity_type="client",
        entity_id=client_id,
        actor=principal.user,
        details={
            "suppliers_added": result.suppliers_added,
            "suppliers_updated": result.suppliers_updated,
            "lanes_added": result.lanes_added,
            "lanes_updated": result.lanes_updated,
            "sku_groups_added": result.sku_groups_added,
            "sku_groups_updated": result.sku_groups_updated,
        },
    )
    return result


@app.get(f"{settings.api_prefix}/events", response_model=list[EventRead])
def list_events(
    since: datetime | None = Query(default=None),
    severity: float | None = Query(default=None, ge=0.0, le=1.0),
    region: str | None = None,
    industry: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
):
    events = session.exec(select(Event).order_by(Event.detected_at.desc())).all()

    def _match(event: Event) -> bool:
        if since and event.detected_at < since:
            return False
        if severity is not None and event.severity < severity:
            return False
        if region:
            blob = " ".join(event.geos + [event.title, event.description]).lower()
            if region.lower() not in blob:
                return False
        if industry and industry not in event.industry_tags:
            return False
        return True

    return [event for event in events if _match(event)][:limit]


@app.get(f"{settings.api_prefix}/clients/{{client_id}}/exposures", response_model=list[ExposureRead])
def get_exposures(
    client_id: str,
    event_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
):
    client = require_client_access(client_id, principal)
    event = _require_event(session, event_id)
    return ensure_exposures(session, client, event)


@app.get(f"{settings.api_prefix}/clients/{{client_id}}/risk-scores", response_model=RiskScoresResponse)
def get_risk_scores(
    client_id: str,
    window: int = Query(default=72, ge=1, le=720),
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
):
    client = require_client_access(client_id, principal)
    pairs = client_risk_snapshot(session, client.id, window_hours=window)

    if not pairs:
        cutoff = now_utc() - timedelta(hours=window)
        recent_events = session.exec(select(Event).where(Event.detected_at >= cutoff)).all()
        for event in recent_events:
            ensure_impact_assessment(session, client, event)
        pairs = client_risk_snapshot(session, client.id, window_hours=window)

    items = [
        RiskScoreItem(
            event_id=assessment.event_id,
            event_title=event.title,
            event_type=event.type,
            risk_score=assessment.risk_score,
            confidence=assessment.confidence,
            revenue_risk_band=assessment.revenue_risk_band,
            override_applied=assessment.override_applied,
            created_at=assessment.updated_at,
        )
        for assessment, event in pairs
    ]
    average = sum(item.risk_score for item in items) / len(items) if items else 0.0
    max_score = max((item.risk_score for item in items), default=0.0)
    return RiskScoresResponse(
        client_id=client_id,
        window_hours=window,
        average_risk_score=round(average, 4),
        max_risk_score=round(max_score, 4),
        items=items,
    )


@app.get(
    f"{settings.api_prefix}/clients/{{client_id}}/events/{{event_id}}/explainability",
    response_model=ExplainabilityRead,
)
def get_explainability(
    client_id: str,
    event_id: str,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> ExplainabilityRead:
    client = require_client_access(client_id, principal)
    event = _require_event(session, event_id)
    return build_explainability(session, client, event)


@app.post(f"{settings.api_prefix}/clients/{{client_id}}/playbooks/generate", response_model=PlaybookRead)
def create_playbook(
    client_id: str,
    payload: PlaybookGenerateRequest,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
):
    client = require_client_access(client_id, principal)
    event = _require_event(session, payload.event_id)
    playbook = generate_playbook(session, client, event)
    log_audit_event(
        session,
        action="playbook.generate",
        entity_type="playbook",
        entity_id=playbook.id,
        actor=principal.user,
        details={"event_id": event.id, "recommended_option": playbook.recommended_option},
    )
    return playbook


@app.get(f"{settings.api_prefix}/playbooks/{{playbook_id}}", response_model=PlaybookRead)
def get_playbook(
    playbook_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
):
    return _require_workspace_playbook(session, principal, playbook_id)


@app.get(f"{settings.api_prefix}/playbooks/{{playbook_id}}/comments", response_model=list[PlaybookCommentRead])
def list_playbook_comments(
    playbook_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> list[PlaybookCommentRead]:
    playbook = _require_workspace_playbook(session, principal, playbook_id)
    comments = session.exec(
        select(PlaybookComment)
        .where(PlaybookComment.client_id == principal.client.id, PlaybookComment.playbook_id == playbook.id)
        .order_by(PlaybookComment.created_at.asc())
    ).all()
    return [PlaybookCommentRead.model_validate(item) for item in comments]


@app.get(f"{settings.api_prefix}/playbooks/{{playbook_id}}/approvals", response_model=list[PlaybookApprovalRead])
def list_playbook_approvals(
    playbook_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> list[PlaybookApprovalRead]:
    playbook = _require_workspace_playbook(session, principal, playbook_id)
    approvals = session.exec(
        select(PlaybookApproval)
        .where(PlaybookApproval.client_id == principal.client.id, PlaybookApproval.playbook_id == playbook.id)
        .order_by(PlaybookApproval.step_order.asc())
    ).all()
    if not approvals:
        approvals = ensure_playbook_approvals(session, playbook)
    return [PlaybookApprovalRead.model_validate(item) for item in approvals]


@app.patch(f"{settings.api_prefix}/playbooks/{{playbook_id}}/approvals/{{approval_id}}", response_model=PlaybookApprovalRead)
def update_playbook_approval(
    playbook_id: str,
    approval_id: str,
    payload: PlaybookApprovalUpdateRequest,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> PlaybookApprovalRead:
    _require_workspace_playbook(session, principal, playbook_id)
    approval = _require_workspace_approval(session, principal, playbook_id, approval_id)
    if payload.owner_user_id:
        _require_workspace_user(session, principal, payload.owner_user_id)

    approval.status = payload.status
    approval.owner_user_id = payload.owner_user_id
    approval.decision_note = payload.decision_note
    if payload.status == "pending":
        approval.decided_at = None
        approval.decided_by_user_id = None
    else:
        approval.decided_at = now_utc()
        approval.decided_by_user_id = principal.user.id
    approval.updated_at = now_utc()
    session.add(approval)
    session.commit()
    session.refresh(approval)
    log_audit_event(
        session,
        action="playbook.approval.update",
        entity_type="playbook_approval",
        entity_id=approval.id,
        actor=principal.user,
        details={"playbook_id": playbook_id, "status": approval.status},
    )
    return PlaybookApprovalRead.model_validate(approval)


@app.post(
    f"{settings.api_prefix}/playbooks/{{playbook_id}}/comments",
    response_model=PlaybookCommentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_playbook_comment(
    playbook_id: str,
    payload: PlaybookCommentCreate,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> PlaybookCommentRead:
    playbook = _require_workspace_playbook(session, principal, playbook_id)
    comment = PlaybookComment(
        client_id=principal.client.id,
        playbook_id=playbook.id,
        event_id=playbook.event_id,
        author_user_id=principal.user.id,
        comment=payload.comment,
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    log_audit_event(
        session,
        action="playbook.comment.add",
        entity_type="playbook_comment",
        entity_id=comment.id,
        actor=principal.user,
        details={"playbook_id": playbook.id, "event_id": playbook.event_id},
    )
    return PlaybookCommentRead.model_validate(comment)


@app.get(f"{settings.api_prefix}/clients/{{client_id}}/events/{{event_id}}/outcome", response_model=IncidentOutcomeRead | None)
def get_incident_outcome(
    client_id: str,
    event_id: str,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> IncidentOutcomeRead | None:
    require_client_access(client_id, principal)
    outcome = session.exec(
        select(IncidentOutcome).where(IncidentOutcome.client_id == client_id, IncidentOutcome.event_id == event_id)
    ).first()
    if not outcome:
        return None
    return IncidentOutcomeRead.model_validate(outcome)


@app.post(
    f"{settings.api_prefix}/clients/{{client_id}}/events/{{event_id}}/outcome",
    response_model=IncidentOutcomeRead,
    status_code=status.HTTP_201_CREATED,
)
def upsert_incident_outcome(
    client_id: str,
    event_id: str,
    payload: IncidentOutcomeUpsertRequest,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> IncidentOutcomeRead:
    require_client_access(client_id, principal)
    _require_event(session, event_id)
    if payload.playbook_id:
        _require_workspace_playbook(session, principal, payload.playbook_id)
    if payload.owner_user_id:
        _require_workspace_user(session, principal, payload.owner_user_id)

    outcome = session.exec(
        select(IncidentOutcome).where(IncidentOutcome.client_id == client_id, IncidentOutcome.event_id == event_id)
    ).first()
    current_time = now_utc()
    if not outcome:
        outcome = IncidentOutcome(
            client_id=client_id,
            event_id=event_id,
            playbook_id=payload.playbook_id,
            owner_user_id=payload.owner_user_id,
            status=payload.status,
            summary=payload.summary,
            actions_taken=payload.actions_taken,
            eta_recovery_hours=payload.eta_recovery_hours,
            service_level_impact_pct=payload.service_level_impact_pct,
            margin_impact_pct=payload.margin_impact_pct,
            completed_at=payload.completed_at,
            updated_at=current_time,
        )
    else:
        outcome.playbook_id = payload.playbook_id
        outcome.owner_user_id = payload.owner_user_id
        outcome.status = payload.status
        outcome.summary = payload.summary
        outcome.actions_taken = payload.actions_taken
        outcome.eta_recovery_hours = payload.eta_recovery_hours
        outcome.service_level_impact_pct = payload.service_level_impact_pct
        outcome.margin_impact_pct = payload.margin_impact_pct
        outcome.completed_at = payload.completed_at
        outcome.updated_at = current_time

    session.add(outcome)
    session.commit()
    session.refresh(outcome)
    log_audit_event(
        session,
        action="incident.outcome.upsert",
        entity_type="incident_outcome",
        entity_id=outcome.id,
        actor=principal.user,
        details={"event_id": event_id, "status": outcome.status},
    )
    return IncidentOutcomeRead.model_validate(outcome)


@app.get(
    f"{settings.api_prefix}/clients/{{client_id}}/events/{{event_id}}/recommendation-override",
    response_model=RecommendationOverrideRead | None,
)
def get_recommendation_override(
    client_id: str,
    event_id: str,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> RecommendationOverrideRead | None:
    require_client_access(client_id, principal)
    override = session.exec(
        select(RecommendationOverride).where(
            RecommendationOverride.client_id == client_id,
            RecommendationOverride.event_id == event_id,
        )
    ).first()
    if not override:
        return None
    return RecommendationOverrideRead.model_validate(override)


@app.post(
    f"{settings.api_prefix}/clients/{{client_id}}/events/{{event_id}}/recommendation-override",
    response_model=RecommendationOverrideRead,
    status_code=status.HTTP_201_CREATED,
)
def upsert_recommendation_override(
    client_id: str,
    event_id: str,
    payload: RecommendationOverrideUpsertRequest,
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> RecommendationOverrideRead:
    client = require_client_access(client_id, principal)
    event = _require_event(session, event_id)

    override = session.exec(
        select(RecommendationOverride).where(
            RecommendationOverride.client_id == client_id,
            RecommendationOverride.event_id == event_id,
        )
    ).first()
    if not override:
        override = RecommendationOverride(
            client_id=client_id,
            event_id=event_id,
            analyst_user_id=principal.user.id,
        )
    override.analyst_user_id = principal.user.id
    override.is_active = payload.is_active
    override.risk_score = payload.risk_score
    override.lead_time_delta_days = payload.lead_time_delta_days
    override.cost_delta_pct = payload.cost_delta_pct
    override.revenue_risk_band = payload.revenue_risk_band
    override.recommended_option = payload.recommended_option
    override.confidence = payload.confidence
    override.analyst_note = payload.analyst_note
    override.updated_at = now_utc()

    session.add(override)
    session.commit()
    session.refresh(override)

    ensure_impact_assessment(session, client, event)
    generate_playbook(session, client, event)

    log_audit_event(
        session,
        action="recommendation_override.upsert",
        entity_type="recommendation_override",
        entity_id=override.id,
        actor=principal.user,
        details={
            "event_id": event_id,
            "is_active": override.is_active,
            "recommended_option": override.recommended_option,
        },
    )
    return RecommendationOverrideRead.model_validate(override)


@app.get(f"{settings.api_prefix}/playbooks/{{playbook_id}}/brief")
def get_playbook_brief(
    playbook_id: str,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    playbook = session.get(Playbook, playbook_id)
    if not playbook or playbook.client_id != principal.client.id:
        raise HTTPException(status_code=404, detail=f"Playbook {playbook_id} not found")

    event = session.get(Event, playbook.event_id)
    impact = session.exec(
        select(ImpactAssessment).where(
            ImpactAssessment.client_id == playbook.client_id,
            ImpactAssessment.event_id == playbook.event_id,
        )
    ).first()
    if not event or not impact:
        raise HTTPException(status_code=404, detail="Playbook dependencies missing")

    lines = [
        f"TradeShield Decision Brief | Playbook {playbook.id}",
        f"Workspace: {principal.client.name}",
        f"Event: {event.title}",
        f"Type: {event.type} | Severity: {event.severity:.2f} | Confidence: {event.confidence:.2f}",
        f"Estimated lead-time delta: {impact.lead_time_delta_days:.2f} days",
        f"Estimated cost delta: {impact.cost_delta_pct:.2f}%",
        f"Revenue risk band: {impact.revenue_risk_band}",
        "",
        f"Recommended scenario: {playbook.recommended_option}",
        "",
        "Scenario options:",
    ]
    for option in playbook.options:
        lines.extend(
            [
                f"- {option.get('name')}: {option.get('objective')}",
                f"  Outcome: {option.get('expected_outcome')}",
                f"  Tradeoff: {option.get('tradeoffs')}",
            ]
        )
    lines.extend(["", "Approval steps:"])
    lines.extend([f"- {step}" for step in playbook.approval_steps])
    return PlainTextResponse("\n".join(lines))


@app.post(
    f"{settings.api_prefix}/alerts/subscriptions",
    response_model=AlertSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_alert_subscription(
    payload: AlertSubscriptionCreate,
    principal: Principal = Depends(require_role("admin")),
    session: Session = Depends(get_session),
):
    if payload.channel == "webhook":
        validate_callback_url(payload.target)

    subscription = AlertSubscription(client_id=principal.client.id, **payload.model_dump(), updated_at=now_utc())
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    log_audit_event(
        session,
        action="alert_subscription.create",
        entity_type="alert_subscription",
        entity_id=subscription.id,
        actor=principal.user,
        details={"channel": subscription.channel, "target": subscription.target},
    )
    return subscription


@app.get(f"{settings.api_prefix}/alerts/subscriptions", response_model=list[AlertSubscriptionRead])
def list_alert_subscriptions(
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> list[AlertSubscriptionRead]:
    subscriptions = session.exec(
        select(AlertSubscription)
        .where(AlertSubscription.client_id == principal.client.id)
        .order_by(AlertSubscription.created_at.desc())
    ).all()
    return [AlertSubscriptionRead.model_validate(item) for item in subscriptions]


@app.patch(f"{settings.api_prefix}/alerts/subscriptions/{{subscription_id}}", response_model=AlertSubscriptionRead)
def update_alert_subscription(
    subscription_id: str,
    payload: AlertSubscriptionUpdate,
    principal: Principal = Depends(require_role("admin")),
    session: Session = Depends(get_session),
) -> AlertSubscriptionRead:
    subscription = _require_workspace_subscription(session, principal, subscription_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return AlertSubscriptionRead.model_validate(subscription)
    if "target" in data and subscription.channel == "webhook":
        validate_callback_url(data["target"])
    for key, value in data.items():
        setattr(subscription, key, value)
    subscription.updated_at = now_utc()
    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    log_audit_event(
        session,
        action="alert_subscription.update",
        entity_type="alert_subscription",
        entity_id=subscription.id,
        actor=principal.user,
        details=data,
    )
    return AlertSubscriptionRead.model_validate(subscription)


@app.delete(f"{settings.api_prefix}/alerts/subscriptions/{{subscription_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_subscription(
    subscription_id: str,
    principal: Principal = Depends(require_role("admin")),
    session: Session = Depends(get_session),
):
    subscription = _require_workspace_subscription(session, principal, subscription_id)
    session.delete(subscription)
    session.commit()
    log_audit_event(
        session,
        action="alert_subscription.delete",
        entity_type="alert_subscription",
        entity_id=subscription_id,
        actor=principal.user,
        details={},
    )
    return None


@app.get(f"{settings.api_prefix}/alerts/deliveries", response_model=list[AlertDeliveryRead])
def list_alert_deliveries(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> list[AlertDeliveryRead]:
    deliveries = _list_alert_deliveries(session, principal.client.id, status_filter=status_filter, limit=limit)
    return [AlertDeliveryRead.model_validate(delivery) for delivery in deliveries]


@app.post(f"{settings.api_prefix}/alerts/dispatch", response_model=AlertDispatchResponse)
def dispatch_alerts(
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> AlertDispatchResponse:
    result = process_pending_alerts(session)
    log_audit_event(
        session,
        action="alert.dispatch",
        entity_type="system",
        entity_id="alert-delivery",
        actor=principal.user,
        details={
            "processed_count": result.processed_count,
            "delivered_count": result.delivered_count,
            "retry_count": result.retry_count,
            "blocked_count": result.blocked_count,
            "failed_count": result.failed_count,
        },
    )
    return AlertDispatchResponse(
        processed_count=result.processed_count,
        delivered_count=result.delivered_count,
        retry_count=result.retry_count,
        blocked_count=result.blocked_count,
        failed_count=result.failed_count,
    )


@app.post(f"{settings.api_prefix}/webhooks/test", response_model=WebhookTestResponse)
def webhook_test(
    payload: WebhookTestRequest,
    _: Principal = Depends(require_role("admin")),
):
    validate_callback_url(payload.url)
    response = httpx.post(payload.url, json=payload.payload, timeout=settings.request_timeout_seconds)
    return WebhookTestResponse(
        status_code=response.status_code,
        delivered=response.status_code < 300,
        response_excerpt=response.text[:400],
    )


@app.post(f"{settings.api_prefix}/ingestion/run", response_model=IngestionRunResponse)
def run_ingestion(
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
):
    service = IngestionService()
    result = service.run_cycle(session, trigger="manual", queue_alerts=True)
    log_audit_event(
        session,
        action="ingestion.run",
        entity_type="system",
        entity_id=result.run.id,
        actor=principal.user,
        details={
            "inserted_count": result.inserted_count,
            "updated_count": result.updated_count,
            "fetched_count": result.fetched_count,
            "queued_alerts": result.queued_alerts,
        },
    )
    return IngestionRunResponse(
        run_id=result.run.id,
        status=result.run.status,
        inserted_count=result.inserted_count,
        updated_count=result.updated_count,
        fetched_count=result.fetched_count,
        duplicate_count=result.duplicate_count,
        queued_alerts=result.queued_alerts,
        connector_health=result.connector_health,
    )


@app.get(f"{settings.api_prefix}/ops/ingestion/runs", response_model=list[IngestionRunRead])
def list_ingestion_runs(
    limit: int = Query(default=20, ge=1, le=100),
    _: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> list[IngestionRunRead]:
    runs = session.exec(select(IngestionRun).order_by(IngestionRun.started_at.desc())).all()
    return [IngestionRunRead.model_validate(run) for run in runs[:limit]]


@app.get(f"{settings.api_prefix}/ops/source-health", response_model=list[SourceHealthRead])
def list_source_health(
    _: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> list[SourceHealthRead]:
    health = session.exec(select(SourceHealth).order_by(SourceHealth.source_name.asc())).all()
    return [SourceHealthRead.model_validate(item) for item in health]


@app.get(f"{settings.api_prefix}/ops/overview", response_model=OpsOverviewResponse)
def ops_overview(
    principal: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> OpsOverviewResponse:
    latest_run = session.exec(select(IngestionRun).order_by(IngestionRun.started_at.desc())).first()
    source_health = session.exec(select(SourceHealth).order_by(SourceHealth.source_name.asc())).all()
    deliveries = _list_alert_deliveries(session, principal.client.id, limit=500)
    active_users = len(
        session.exec(select(User).where(User.client_id == principal.client.id, User.is_active.is_(True))).all()
    )
    return OpsOverviewResponse(
        latest_run=IngestionRunRead.model_validate(latest_run) if latest_run else None,
        source_health=[SourceHealthRead.model_validate(item) for item in source_health],
        queued_alerts=sum(1 for item in deliveries if item.status == "queued"),
        retrying_alerts=sum(1 for item in deliveries if item.status == "retry_scheduled"),
        failed_alerts=sum(1 for item in deliveries if item.status in {"failed", "blocked"}),
        active_users=active_users,
    )


@app.get(f"{settings.api_prefix}/ops/metrics", response_model=OpsMetricsResponse)
def ops_metrics(
    _: Principal = Depends(require_role("admin", "analyst")),
    session: Session = Depends(get_session),
) -> OpsMetricsResponse:
    cutoff = now_utc() - timedelta(hours=24)
    runs = session.exec(select(IngestionRun).where(IngestionRun.started_at >= cutoff)).all()
    run_count = len(runs)

    successful_runs = [run for run in runs if run.status in {"completed", "partial_success"}]
    success_rate = (len(successful_runs) / run_count) if run_count else 0.0

    durations = [
        max((run.finished_at - run.started_at).total_seconds(), 0.0)
        for run in runs
        if run.finished_at is not None
    ]
    durations_sorted = sorted(durations)
    avg_duration = (sum(durations) / len(durations)) if durations else 0.0
    if durations_sorted:
        p95_index = min(len(durations_sorted) - 1, int(0.95 * (len(durations_sorted) - 1)))
        p95_duration = durations_sorted[p95_index]
    else:
        p95_duration = 0.0

    events_inserted = sum(run.inserted_count for run in runs)
    events_updated = sum(run.updated_count for run in runs)
    queued_alerts = sum(run.queued_alerts for run in runs)

    deliveries_24h = session.exec(select(AlertDelivery).where(AlertDelivery.created_at >= cutoff)).all()
    delivered_alerts = sum(1 for item in deliveries_24h if item.status == "delivered")
    failed_alerts = sum(1 for item in deliveries_24h if item.status in {"failed", "blocked"})
    retrying_alerts = sum(1 for item in deliveries_24h if item.status == "retry_scheduled")

    return OpsMetricsResponse(
        run_count_24h=run_count,
        success_rate_24h=round(success_rate, 4),
        avg_run_duration_seconds_24h=round(avg_duration, 2),
        p95_run_duration_seconds_24h=round(p95_duration, 2),
        events_inserted_24h=events_inserted,
        events_updated_24h=events_updated,
        queued_alerts_24h=queued_alerts,
        delivered_alerts_24h=delivered_alerts,
        failed_alerts_24h=failed_alerts,
        retrying_alerts_current=retrying_alerts,
    )


@app.get(f"{settings.api_prefix}/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_session),
):
    window = 168
    cutoff = now_utc() - timedelta(hours=window)
    recent_events = session.exec(select(Event).where(Event.detected_at >= cutoff).order_by(Event.detected_at.desc())).all()

    pairs = client_risk_snapshot(session, principal.client.id, window_hours=window)
    if not pairs:
        for event in recent_events:
            ensure_impact_assessment(session, principal.client, event)
        pairs = client_risk_snapshot(session, principal.client.id, window_hours=window)

    prioritized_events = [event for _, event in pairs[:8]] or recent_events[:8]
    open_events = len(prioritized_events)
    avg_severity = round(sum(e.severity for e in prioritized_events) / open_events, 4) if open_events else 0.0
    highest_risk = max((pair[0].risk_score for pair in pairs), default=0.0)

    return DashboardSummary(
        client_name=principal.client.name,
        open_events=open_events,
        average_severity=avg_severity,
        highest_risk_score=round(highest_risk, 4),
        latest_events=prioritized_events,
    )

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlmodel import Session, select

from app.config import get_enabled_connectors, settings
from app.connectors import GDELTConnector, NewsAPIConnector, OpenSkyConnector, SpireConnector, UKMTOConnector, USGSConnector
from app.connectors.base import BaseConnector, ConnectorEvent
from app.models import Event, IngestionRun, SourceHealth
from app.services.demo_replay import load_demo_events
from app.services.alerts import queue_alerts_for_event
from app.services.scoring import invalidate_event_artifacts
from app.utils import build_event_fingerprint, clamp, now_utc

logger = logging.getLogger(__name__)


def _is_backoff_active(backoff_until, current_time) -> bool:
    if not backoff_until:
        return False
    if backoff_until.tzinfo is None and current_time.tzinfo is not None:
        return backoff_until > current_time.replace(tzinfo=None)
    if backoff_until.tzinfo is not None and current_time.tzinfo is None:
        return backoff_until.replace(tzinfo=None) > current_time
    return backoff_until > current_time


def classify_event_type(text: str) -> str:
    blob = text.lower()
    if any(k in blob for k in ["tariff", "duty", "policy", "trade notice", "customs"]):
        return "tariff/policy"
    if any(k in blob for k in ["sanction", "embargo", "restricted", "compliance"]):
        return "sanctions/compliance"
    if any(k in blob for k in ["war", "piracy", "conflict", "attack", "missile"]):
        return "conflict/security"
    if any(k in blob for k in ["earthquake", "storm", "flood", "cyclone", "disaster"]):
        return "disaster/weather"
    if any(k in blob for k in ["congestion", "delay", "port", "vessel", "freight"]):
        return "logistics congestion"
    if any(k in blob for k in ["shutdown", "outage", "fire", "explosion", "incident"]):
        return "operational incidents"
    return "other"


def _normalize_token_list(items: list[str]) -> list[str]:
    unique = []
    seen: set[str] = set()
    for item in items:
        value = " ".join((item or "").split()).strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        unique.append(value[:120])
    return unique


def _normalize_event(event: ConnectorEvent) -> ConnectorEvent:
    text = f"{event.title} {event.description} {' '.join(event.entities)} {' '.join(event.geos)}"
    if not event.event_type or event.event_type == "other":
        event.event_type = classify_event_type(text)
    event.severity = clamp(event.severity, 0.0, 1.0)
    event.confidence = clamp(event.confidence, 0.0, 1.0)
    event.title = " ".join(event.title.split())[:250]
    event.description = " ".join(event.description.split())[:2000]
    event.geos = _normalize_token_list(event.geos)
    event.entities = _normalize_token_list(event.entities)
    event.industry_tags = _normalize_token_list(event.industry_tags)
    if not event.source_event_id:
        event.source_event_id = build_event_fingerprint(
            [
                event.source,
                event.title,
                event.description,
                "|".join(sorted(event.geos)),
                "|".join(sorted(event.entities)),
            ]
        )[:48]
    return event


def _build_fingerprint(event: ConnectorEvent) -> str:
    return build_event_fingerprint([event.source, event.source_event_id])


def _event_changed(model: Event, event: ConnectorEvent) -> bool:
    comparable_existing = (
        model.type,
        model.title,
        model.description,
        tuple(model.geos),
        tuple(model.entities),
        round(model.severity, 4),
        round(model.confidence, 4),
        tuple((item.get("title"), item.get("url"), item.get("source")) for item in model.evidence),
        tuple(model.industry_tags),
    )
    comparable_new = (
        event.event_type,
        event.title,
        event.description,
        tuple(event.geos),
        tuple(event.entities),
        round(event.severity, 4),
        round(event.confidence, 4),
        tuple((item.get("title"), item.get("url"), item.get("source")) for item in event.evidence),
        tuple(event.industry_tags),
    )
    return comparable_existing != comparable_new


@dataclass
class IngestionCycleResult:
    run: IngestionRun
    inserted_count: int
    updated_count: int
    fetched_count: int
    duplicate_count: int
    queued_alerts: int
    connector_health: dict[str, dict]
    inserted_events: list[Event]
    updated_events: list[Event]


class IngestionService:
    def __init__(self, connectors: list[BaseConnector] | None = None):
        available_connectors = connectors or [
            GDELTConnector(),
            USGSConnector(),
            UKMTOConnector(),
            OpenSkyConnector(),
            NewsAPIConnector(),
            SpireConnector(),
        ]
        enabled_connectors = get_enabled_connectors()
        if enabled_connectors is None:
            self.connectors = available_connectors
            return

        self.connectors = [connector for connector in available_connectors if connector.name.lower() in enabled_connectors]
        configured = sorted(enabled_connectors)
        available = sorted(connector.name.lower() for connector in available_connectors)
        logger.info(
            "Connector allowlist applied",
            extra={
                "enabled_connectors": configured,
                "active_connectors": [connector.name for connector in self.connectors],
                "available_connectors": available,
            },
        )

    def _fetch_demo_events(self) -> list[ConnectorEvent]:
        return load_demo_events(settings.demo_scenario)

    def _upsert_source_health(
        self,
        session: Session,
        *,
        source_name: str,
        status: str,
        fetched_count: int,
        inserted_count: int,
        updated_count: int,
        duplicate_count: int,
        consecutive_errors: int = 0,
        backoff_until=None,
        error: str | None = None,
    ) -> None:
        current_time = now_utc()
        health = session.exec(select(SourceHealth).where(SourceHealth.source_name == source_name)).first()
        if not health:
            health = SourceHealth(source_name=source_name)
            session.add(health)

        health.last_run_status = status
        health.last_run_at = current_time
        health.last_error = error
        health.fetched_count = fetched_count
        health.inserted_count = inserted_count
        health.updated_count = updated_count
        health.duplicate_count = duplicate_count
        health.consecutive_errors = consecutive_errors
        health.backoff_until = backoff_until
        health.updated_at = current_time
        if status == "ok":
            health.last_success_at = current_time

    def run_cycle(self, session: Session, *, trigger: str = "manual", queue_alerts: bool = True) -> IngestionCycleResult:
        run = IngestionRun(trigger=trigger, status="running", started_at=now_utc())
        session.add(run)
        session.commit()
        session.refresh(run)

        connector_health: dict[str, dict] = {}
        inserted_events: list[Event] = []
        updated_events: list[Event] = []
        fetched_count = 0
        duplicate_count = 0
        queued_alerts = 0
        had_error = False
        had_degraded = False

        if settings.demo_mode:
            connector_name = f"demo-replay:{settings.demo_scenario}"
            raw_events = self._fetch_demo_events()
            source_inserted = 0
            source_updated = 0
            source_duplicate = 0
            current_time = now_utc()
            fetched_count += len(raw_events)
            for connector_event in raw_events:
                event = _normalize_event(connector_event)
                fingerprint = _build_fingerprint(event)
                existing = session.exec(select(Event).where(Event.fingerprint == fingerprint)).first()
                if existing:
                    source_duplicate += 1
                    duplicate_count += 1
                    changed = _event_changed(existing, event)
                    existing.last_seen_at = current_time
                    existing.duplicate_count += 1
                    if changed:
                        existing.type = event.event_type
                        existing.title = event.title
                        existing.description = event.description
                        existing.occurred_at = event.occurred_at
                        existing.geos = event.geos
                        existing.entities = event.entities
                        existing.severity = event.severity
                        existing.confidence = event.confidence
                        existing.evidence = event.evidence
                        existing.industry_tags = event.industry_tags
                        existing.raw_payload = event.raw_payload
                        existing.updated_at = current_time
                        session.add(existing)
                        session.commit()
                        invalidate_event_artifacts(session, existing.id)
                        updated_events.append(existing)
                        source_updated += 1
                    else:
                        session.add(existing)
                        session.commit()
                    continue

                model = Event(
                    source=event.source,
                    source_event_id=event.source_event_id,
                    fingerprint=fingerprint,
                    type=event.event_type,
                    title=event.title,
                    description=event.description,
                    occurred_at=event.occurred_at,
                    detected_at=current_time,
                    last_seen_at=current_time,
                    geos=event.geos,
                    entities=event.entities,
                    severity=event.severity,
                    confidence=event.confidence,
                    evidence=event.evidence,
                    industry_tags=event.industry_tags,
                    raw_payload=event.raw_payload,
                    updated_at=current_time,
                )
                session.add(model)
                session.commit()
                session.refresh(model)
                inserted_events.append(model)
                source_inserted += 1

            connector_health[connector_name] = {
                "status": "ok",
                "fetched_count": len(raw_events),
                "inserted_count": source_inserted,
                "updated_count": source_updated,
                "duplicate_count": source_duplicate,
                "error": None,
            }
            self._upsert_source_health(
                session,
                source_name=connector_name,
                status="ok",
                fetched_count=len(raw_events),
                inserted_count=source_inserted,
                updated_count=source_updated,
                duplicate_count=source_duplicate,
                consecutive_errors=0,
                backoff_until=None,
                error=None,
            )
            session.commit()
        else:
            for connector in self.connectors:
                current_time = now_utc()
                source_inserted = 0
                source_updated = 0
                source_duplicate = 0
                connector_name = connector.name.lower()
                existing_health = session.exec(select(SourceHealth).where(SourceHealth.source_name == connector_name)).first()

                if existing_health and _is_backoff_active(existing_health.backoff_until, current_time):
                    had_degraded = True
                    connector_health[connector_name] = {
                        "status": "backoff",
                        "fetched_count": 0,
                        "inserted_count": 0,
                        "updated_count": 0,
                        "duplicate_count": 0,
                        "error": existing_health.last_error,
                        "backoff_until": existing_health.backoff_until.isoformat(),
                    }
                    self._upsert_source_health(
                        session,
                        source_name=connector_name,
                        status="backoff",
                        fetched_count=0,
                        inserted_count=0,
                        updated_count=0,
                        duplicate_count=0,
                        consecutive_errors=existing_health.consecutive_errors,
                        backoff_until=existing_health.backoff_until,
                        error=existing_health.last_error,
                    )
                    session.commit()
                    continue

                try:
                    raw_events = connector.fetch()
                    fetched_count += len(raw_events)
                    connector_status = "ok"
                    error_message = None
                    consecutive_errors = 0
                    backoff_until = None
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Connector fetch failed", extra={"connector": connector_name})
                    raw_events = []
                    next_error_count = (existing_health.consecutive_errors if existing_health else 0) + 1
                    connector_status = "error"
                    error_message = type(exc).__name__
                    consecutive_errors = next_error_count
                    backoff_until = None
                    if next_error_count >= settings.ingestion_backoff_error_threshold:
                        connector_status = "backoff"
                        backoff_until = current_time + timedelta(minutes=settings.ingestion_error_backoff_minutes)
                        had_degraded = True
                    had_error = True

                for connector_event in raw_events:
                    event = _normalize_event(connector_event)
                    fingerprint = _build_fingerprint(event)
                    existing = session.exec(select(Event).where(Event.fingerprint == fingerprint)).first()
                    if existing:
                        source_duplicate += 1
                        duplicate_count += 1
                        changed = _event_changed(existing, event)
                        existing.last_seen_at = current_time
                        existing.duplicate_count += 1
                        if changed:
                            existing.type = event.event_type
                            existing.title = event.title
                            existing.description = event.description
                            existing.occurred_at = event.occurred_at
                            existing.geos = event.geos
                            existing.entities = event.entities
                            existing.severity = event.severity
                            existing.confidence = event.confidence
                            existing.evidence = event.evidence
                            existing.industry_tags = event.industry_tags
                            existing.raw_payload = event.raw_payload
                            existing.updated_at = current_time
                            session.add(existing)
                            session.commit()
                            invalidate_event_artifacts(session, existing.id)
                            updated_events.append(existing)
                            source_updated += 1
                        else:
                            session.add(existing)
                            session.commit()
                        continue

                    model = Event(
                        source=event.source,
                        source_event_id=event.source_event_id,
                        fingerprint=fingerprint,
                        type=event.event_type,
                        title=event.title,
                        description=event.description,
                        occurred_at=event.occurred_at,
                        detected_at=current_time,
                        last_seen_at=current_time,
                        geos=event.geos,
                        entities=event.entities,
                        severity=event.severity,
                        confidence=event.confidence,
                        evidence=event.evidence,
                        industry_tags=event.industry_tags,
                        raw_payload=event.raw_payload,
                        updated_at=current_time,
                    )
                    session.add(model)
                    session.commit()
                    session.refresh(model)
                    inserted_events.append(model)
                    source_inserted += 1

                connector_health[connector_name] = {
                    "status": connector_status,
                    "fetched_count": len(raw_events),
                    "inserted_count": source_inserted,
                    "updated_count": source_updated,
                    "duplicate_count": source_duplicate,
                    "error": error_message,
                }
                if backoff_until:
                    connector_health[connector_name]["backoff_until"] = backoff_until.isoformat()
                self._upsert_source_health(
                    session,
                    source_name=connector_name,
                    status=connector_status,
                    fetched_count=len(raw_events),
                    inserted_count=source_inserted,
                    updated_count=source_updated,
                    duplicate_count=source_duplicate,
                    consecutive_errors=consecutive_errors,
                    backoff_until=backoff_until,
                    error=error_message,
                )
                session.commit()

        if queue_alerts:
            for event in inserted_events:
                queued_alerts += queue_alerts_for_event(session, event)

        if had_error and (inserted_events or updated_events):
            run.status = "partial_success"
        elif had_error:
            run.status = "failed"
        elif had_degraded:
            run.status = "partial_success"
        else:
            run.status = "completed"
        run.finished_at = now_utc()
        run.fetched_count = fetched_count
        run.inserted_count = len(inserted_events)
        run.updated_count = len(updated_events)
        run.duplicate_count = duplicate_count
        run.queued_alerts = queued_alerts
        run.connector_health = connector_health
        run.error_summary = {
            name: payload["error"]
            for name, payload in connector_health.items()
            if payload.get("error")
        }
        run.updated_at = now_utc()
        session.add(run)
        session.commit()
        session.refresh(run)

        return IngestionCycleResult(
            run=run,
            inserted_count=len(inserted_events),
            updated_count=len(updated_events),
            fetched_count=fetched_count,
            duplicate_count=duplicate_count,
            queued_alerts=queued_alerts,
            connector_health=connector_health,
            inserted_events=inserted_events,
            updated_events=updated_events,
        )

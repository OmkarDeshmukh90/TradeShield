from datetime import datetime, timezone

from sqlmodel import Session, select

from app.connectors.base import BaseConnector, ConnectorEvent
from app.config import settings
from app.database import engine, reset_db
from app.models import AlertDelivery, AlertSubscription, Client, Event, IngestionRun, RecommendationOverride, SourceHealth, User
from app.services.alerts import process_pending_alerts
from app.services.ingestion import IngestionService
from app.services.playbooks import generate_playbook
from app.services.scoring import ensure_exposures, ensure_impact_assessment
from app.services.supply_map import upsert_supply_map
from app.schemas import SupplyMapUpsertRequest
from app.utils import build_event_fingerprint


class StubConnector(BaseConnector):
    name = "stub"

    def __init__(self, batches: list[list[ConnectorEvent]]):
        self._batches = batches
        self._calls = 0

    def fetch(self) -> list[ConnectorEvent]:
        index = min(self._calls, len(self._batches) - 1)
        self._calls += 1
        return self._batches[index]


class FailingConnector(BaseConnector):
    name = "failing"

    def __init__(self):
        self.calls = 0

    def fetch(self) -> list[ConnectorEvent]:
        self.calls += 1
        raise RuntimeError("source unavailable")


class CountingConnector(BaseConnector):
    def __init__(self, name: str):
        self.name = name
        self.calls = 0

    def fetch(self) -> list[ConnectorEvent]:
        self.calls += 1
        return []


def _build_event(source_event_id: str, severity: float, description: str) -> ConnectorEvent:
    return ConnectorEvent(
        source="StubFeed",
        source_event_id=source_event_id,
        title="Port congestion rising near Strait of Malacca",
        description=description,
        occurred_at=datetime.now(timezone.utc),
        event_type="logistics congestion",
        geos=["Singapore", "Strait of Malacca"],
        entities=["shipping", "port congestion"],
        severity=severity,
        confidence=0.8,
        evidence=[{"title": "Stub", "url": "https://example.com", "source": "Stub"}],
    )


def test_ingestion_persists_run_source_health_and_queues_alerts():
    reset_db()
    connector = StubConnector(
        [
            [_build_event("evt-1", 0.7, "Queue times increased across the corridor.")],
            [_build_event("evt-1", 0.9, "Queue times increased and carriers started omitting calls.")],
        ]
    )

    with Session(engine) as session:
        client = Client(name="Service Test Client", industry="Pharmaceuticals and APIs", country="India")
        session.add(client)
        session.commit()
        session.refresh(client)

        session.add(
            AlertSubscription(
                client_id=client.id,
                channel="dashboard",
                target="control-tower",
                min_severity=0.5,
            )
        )
        session.commit()

        service = IngestionService(connectors=[connector])
        result_a = service.run_cycle(session, trigger="manual", queue_alerts=True)
        assert result_a.inserted_count == 1
        assert result_a.queued_alerts == 1

        runs = session.exec(select(IngestionRun).order_by(IngestionRun.created_at.asc())).all()
        assert len(runs) == 1
        assert runs[0].status == "completed"

        source_health = session.exec(select(SourceHealth).where(SourceHealth.source_name == "stub")).first()
        assert source_health is not None
        assert source_health.inserted_count == 1

        queued_delivery = session.exec(select(AlertDelivery)).first()
        assert queued_delivery is not None
        assert queued_delivery.status == "queued"

        result_b = service.run_cycle(session, trigger="manual", queue_alerts=True)
        assert result_b.inserted_count == 0
        assert result_b.updated_count == 1
        assert result_b.duplicate_count == 1

        event = session.exec(select(Event).where(Event.source_event_id == "evt-1")).first()
        assert event is not None
        assert event.severity == 0.9
        assert event.duplicate_count == 1


def test_process_pending_alerts_delivers_dashboard_messages():
    reset_db()

    with Session(engine) as session:
        client = Client(name="Alert Client", industry="Automotive and Auto Components", country="India")
        session.add(client)
        session.commit()
        session.refresh(client)

        subscription = AlertSubscription(
            client_id=client.id,
            channel="dashboard",
            target="control-tower",
            min_severity=0.4,
        )
        session.add(subscription)

        event = Event(
            source="test",
            source_event_id="evt-1",
            fingerprint=build_event_fingerprint(["test", "evt-1"]),
            type="conflict/security",
            title="Security incident near a major shipping lane",
            description="A vessel incident increased risk in the corridor.",
            occurred_at=datetime.now(timezone.utc),
            detected_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            geos=["Red Sea"],
            entities=["shipping"],
            severity=0.8,
            confidence=0.8,
        )
        session.add(event)
        session.commit()
        session.refresh(subscription)
        session.refresh(event)

        from app.services.alerts import queue_alerts_for_event

        queued = queue_alerts_for_event(session, event)
        assert queued == 1

        result = process_pending_alerts(session)
        assert result.delivered_count == 1
        assert result.failed_count == 0

        delivery = session.exec(select(AlertDelivery)).first()
        assert delivery is not None
        assert delivery.status == "delivered"
        assert delivery.delivered_at is not None


def test_supply_map_update_invalidates_and_recomputes_assessment_and_playbook():
    reset_db()

    with Session(engine) as session:
        client = Client(
            name="Service Test Client",
            industry="Pharmaceuticals and APIs",
            country="India",
            preferences={"objective": "margin-protect"},
        )
        session.add(client)
        session.commit()
        session.refresh(client)

        upsert_supply_map(
            session,
            client.id,
            SupplyMapUpsertRequest(
                suppliers=[
                    {
                        "name": "Supplier A",
                        "country": "China",
                        "region": "South China",
                        "commodity": "API",
                        "criticality": 0.4,
                        "substitution_score": 0.9,
                        "lead_time_sensitivity": 0.3,
                        "inventory_buffer_days": 35,
                    }
                ],
                lanes=[
                    {
                        "origin": "Shanghai",
                        "destination": "Nhava Sheva",
                        "mode": "sea",
                        "chokepoint": "Strait of Malacca",
                        "importance": 0.5,
                    }
                ],
                sku_groups=[{"name": "API Core", "category": "API", "monthly_volume": 5000, "margin_sensitivity": 0.4}],
            ),
        )

        event = Event(
            source="test",
            source_event_id="evt-1",
            fingerprint=build_event_fingerprint(["test", "evt-1"]),
            type="tariff/policy",
            title="Tariff raised on API ingredients",
            description="Duty increased overnight for selected pharma intermediates.",
            occurred_at=datetime.now(timezone.utc),
            detected_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            geos=["India", "China"],
            entities=["API", "tariff"],
            severity=0.8,
            confidence=0.9,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        exposures = ensure_exposures(session, client, event)
        assert len(exposures) >= 1

        impact_a = ensure_impact_assessment(session, client, event)
        playbook_a = generate_playbook(session, client, event)
        impact_a_id = impact_a.id
        impact_a_score = impact_a.risk_score
        playbook_a_id = playbook_a.id

        upsert_supply_map(
            session,
            client.id,
            SupplyMapUpsertRequest(
                suppliers=[
                    {
                        "name": "Supplier A",
                        "country": "China",
                        "region": "South China",
                        "commodity": "API",
                        "criticality": 0.95,
                        "substitution_score": 0.1,
                        "lead_time_sensitivity": 0.9,
                        "inventory_buffer_days": 5,
                    }
                ],
                lanes=[
                    {
                        "origin": "Shanghai",
                        "destination": "Nhava Sheva",
                        "mode": "sea",
                        "chokepoint": "Strait of Malacca",
                        "importance": 0.95,
                    }
                ],
                sku_groups=[{"name": "API Core", "category": "API", "monthly_volume": 25000, "margin_sensitivity": 0.9}],
            ),
        )

        impact_b = ensure_impact_assessment(session, client, event)
        playbook_b = generate_playbook(session, client, event)

        assert impact_b.id != impact_a_id
        assert impact_b.risk_score > impact_a_score
        assert playbook_b.id != playbook_a_id


def test_manual_override_applies_and_supply_map_version_increments():
    reset_db()

    with Session(engine) as session:
        client = Client(
            name="Override Client",
            industry="Electronics and Semiconductors",
            country="India",
            preferences={"objective": "cost-balanced"},
        )
        session.add(client)
        user = User(
            client_id=client.id,
            full_name="Analyst",
            email="analyst@example.com",
            role="analyst",
            password_hash="pbkdf2_sha256$390000$salt$hash",
        )
        session.add(user)
        session.commit()
        session.refresh(client)
        session.refresh(user)

        version_before = client.supply_map_version
        upsert_supply_map(
            session,
            client.id,
            SupplyMapUpsertRequest(
                suppliers=[
                    {
                        "name": "Supplier A",
                        "country": "China",
                        "region": "South China",
                        "commodity": "chipset",
                        "criticality": 0.8,
                        "substitution_score": 0.2,
                        "lead_time_sensitivity": 0.8,
                        "inventory_buffer_days": 6,
                    }
                ],
                lanes=[],
                sku_groups=[],
            ),
        )
        session.refresh(client)
        assert client.supply_map_version == version_before + 1

        event = Event(
            source="test",
            source_event_id="override-evt-1",
            fingerprint=build_event_fingerprint(["test", "override-evt-1"]),
            type="logistics congestion",
            title="Congestion has increased",
            description="Carrier delays are worsening in a major lane.",
            occurred_at=datetime.now(timezone.utc),
            detected_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            geos=["South China"],
            entities=["chipset", "shipping"],
            severity=0.8,
            confidence=0.9,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        impact_base = ensure_impact_assessment(session, client, event)
        assert impact_base.override_applied is False

        override = RecommendationOverride(
            client_id=client.id,
            event_id=event.id,
            analyst_user_id=user.id,
            is_active=True,
            risk_score=0.33,
            lead_time_delta_days=2.5,
            cost_delta_pct=4.2,
            revenue_risk_band="low",
            recommended_option="margin-protect",
            confidence=0.91,
            analyst_note="Manual market intelligence update from analyst desk.",
        )
        session.add(override)
        session.commit()

        impact_overridden = ensure_impact_assessment(session, client, event)
        assert impact_overridden.override_applied is True
        assert impact_overridden.risk_score == 0.33
        assert impact_overridden.lead_time_delta_days == 2.5
        assert impact_overridden.revenue_risk_band == "low"

        playbook = generate_playbook(session, client, event)
        assert playbook.override_applied is True
        assert playbook.recommended_option == "margin-protect"


def test_ingestion_backoff_after_consecutive_failures():
    reset_db()
    connector = FailingConnector()
    prev_threshold = settings.ingestion_backoff_error_threshold
    prev_minutes = settings.ingestion_error_backoff_minutes
    prev_enabled = settings.enabled_connectors
    settings.ingestion_backoff_error_threshold = 2
    settings.ingestion_error_backoff_minutes = 10
    settings.enabled_connectors = "all"

    try:
        with Session(engine) as session:
            service = IngestionService(connectors=[connector])
            first = service.run_cycle(session, trigger="manual", queue_alerts=False)
            assert first.run.status == "failed"
            health_first = session.exec(select(SourceHealth).where(SourceHealth.source_name == "failing")).first()
            assert health_first is not None
            assert health_first.consecutive_errors == 1
            assert health_first.backoff_until is None

            second = service.run_cycle(session, trigger="manual", queue_alerts=False)
            assert second.run.status == "failed"
            health_second = session.exec(select(SourceHealth).where(SourceHealth.source_name == "failing")).first()
            assert health_second is not None
            assert health_second.last_run_status == "backoff"
            assert health_second.consecutive_errors == 2
            assert health_second.backoff_until is not None

            _ = service.run_cycle(session, trigger="manual", queue_alerts=False)
            health_third = session.exec(select(SourceHealth).where(SourceHealth.source_name == "failing")).first()
            assert health_third is not None
            assert health_third.last_run_status == "backoff"
            assert connector.calls == 2
    finally:
        settings.ingestion_backoff_error_threshold = prev_threshold
        settings.ingestion_error_backoff_minutes = prev_minutes
        settings.enabled_connectors = prev_enabled


def test_ingestion_allowlist_filters_connectors():
    reset_db()
    connector_a = CountingConnector("alpha")
    connector_b = CountingConnector("beta")
    prev_enabled = settings.enabled_connectors
    settings.enabled_connectors = "beta"

    try:
        with Session(engine) as session:
            service = IngestionService(connectors=[connector_a, connector_b])
            service.run_cycle(session, trigger="manual", queue_alerts=False)
            assert connector_a.calls == 0
            assert connector_b.calls == 1

            alpha_health = session.exec(select(SourceHealth).where(SourceHealth.source_name == "alpha")).first()
            beta_health = session.exec(select(SourceHealth).where(SourceHealth.source_name == "beta")).first()
            assert alpha_health is None
            assert beta_health is not None
            assert beta_health.last_run_status == "ok"
    finally:
        settings.enabled_connectors = prev_enabled

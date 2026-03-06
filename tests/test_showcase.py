from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import settings
from app.database import engine, reset_db
from app.main import app
from app.models import AlertSubscription, Client, Event, RecommendationOverride, User
from app.services.demo_seed import seed_demo_workspace
from app.services.ingestion import IngestionService
from app.services.scoring import ensure_impact_assessment


def _register(client: TestClient, email: str):
    response = client.post(
        "/v1/auth/register",
        json={
            "company_name": "Showcase Co",
            "industry": "Electronics and Semiconductors",
            "country": "India",
            "preferences": {"objective": "cost-balanced"},
            "full_name": "Showcase Admin",
            "email": email,
            "password": "StrongPass123",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_demo_seed_lifecycle_creates_workspace_and_events():
    reset_db()
    with Session(engine) as session:
        payload = seed_demo_workspace(session, include_events=True)
        assert payload.get("client_id")
        client = session.exec(select(Client).where(Client.id == payload["client_id"])).first()
        assert client is not None
        events = session.exec(select(Event)).all()
        assert len(events) >= 2
        policies = session.exec(select(AlertSubscription).where(AlertSubscription.client_id == client.id)).all()
        assert len(policies) >= 2


def test_demo_mode_ingestion_is_deterministic():
    reset_db()
    prev_mode = settings.demo_mode
    prev_scenario = settings.demo_scenario
    settings.demo_mode = True
    settings.demo_scenario = "tariff"
    try:
        with Session(engine) as session:
            service = IngestionService()
            first = service.run_cycle(session, trigger="manual", queue_alerts=False)
            second = service.run_cycle(session, trigger="manual", queue_alerts=False)
            assert first.inserted_count >= 1
            assert second.inserted_count == 0
            assert second.duplicate_count == first.fetched_count
    finally:
        settings.demo_mode = prev_mode
        settings.demo_scenario = prev_scenario


def test_explainability_endpoint_returns_weighted_factors_and_override_delta():
    reset_db()
    with TestClient(app) as client:
        auth = _register(client, "showcase.explain@example.com")
        token = auth["access_token"]
        client_id = auth["client"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post(
            f"/v1/clients/{client_id}/supply-map",
            headers=headers,
            json={
                "suppliers": [
                    {
                        "name": "Supplier A",
                        "country": "China",
                        "region": "South China",
                        "commodity": "semiconductors",
                        "criticality": 0.9,
                        "substitution_score": 0.2,
                        "lead_time_sensitivity": 0.8,
                        "inventory_buffer_days": 6,
                    }
                ],
                "lanes": [{"origin": "Shanghai", "destination": "Nhava Sheva", "mode": "sea", "importance": 0.8}],
                "sku_groups": [{"name": "Power IC", "category": "semiconductor", "margin_sensitivity": 0.8}],
            },
        )

        prev_mode = settings.demo_mode
        prev_scenario = settings.demo_scenario
        settings.demo_mode = True
        settings.demo_scenario = "tariff"
        try:
            with Session(engine) as session:
                IngestionService().run_cycle(session, trigger="manual", queue_alerts=False)
                event = session.exec(select(Event).order_by(Event.created_at.desc())).first()
                assert event is not None
                event_id = event.id

                app_user = session.exec(select(User).where(User.client_id == client_id).order_by(User.created_at.asc())).first()
                assert app_user is not None

                override = RecommendationOverride(
                    client_id=client_id,
                    event_id=event_id,
                    analyst_user_id=app_user.id,
                    is_active=True,
                    risk_score=0.31,
                    lead_time_delta_days=2.2,
                    cost_delta_pct=3.6,
                    confidence=0.92,
                    analyst_note="Showcase override for delta view",
                )
                session.add(override)
                session.commit()
                ensure_impact_assessment(session, session.get(Client, client_id), event)
        finally:
            settings.demo_mode = prev_mode
            settings.demo_scenario = prev_scenario

        response = client.get(f"/v1/clients/{client_id}/events/{event_id}/explainability", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["factors"]) == 4
        assert payload["base_estimate"]["risk_score"] >= 0
        assert payload["override_estimate"] is not None
        assert payload["delta"] is not None


def test_end_to_end_showcase_narrative_flow():
    reset_db()
    with TestClient(app) as client:
        auth = _register(client, "showcase.flow@example.com")
        token = auth["access_token"]
        client_id = auth["client"]["id"]
        headers = {"Authorization": f"Bearer {token}"}

        client.post(
            f"/v1/clients/{client_id}/supply-map",
            headers=headers,
            json={
                "suppliers": [
                    {
                        "name": "Supplier A",
                        "country": "China",
                        "region": "South China",
                        "commodity": "semiconductors",
                        "criticality": 0.9,
                        "substitution_score": 0.25,
                        "lead_time_sensitivity": 0.8,
                        "inventory_buffer_days": 7,
                    }
                ],
                "lanes": [{"origin": "Shanghai", "destination": "Nhava Sheva", "mode": "sea", "importance": 0.8}],
                "sku_groups": [{"name": "Power IC", "category": "semiconductor", "margin_sensitivity": 0.8}],
            },
        )

        prev_mode = settings.demo_mode
        prev_scenario = settings.demo_scenario
        settings.demo_mode = True
        settings.demo_scenario = "congestion"
        try:
            with Session(engine) as session:
                IngestionService().run_cycle(session, trigger="manual", queue_alerts=False)
        finally:
            settings.demo_mode = prev_mode
            settings.demo_scenario = prev_scenario

        events = client.get("/v1/events", headers=headers).json()
        assert events
        event_id = events[0]["id"]

        playbook = client.post(
            f"/v1/clients/{client_id}/playbooks/generate",
            headers=headers,
            json={"event_id": event_id},
        )
        assert playbook.status_code == 200
        playbook_id = playbook.json()["id"]

        approvals = client.get(f"/v1/playbooks/{playbook_id}/approvals", headers=headers)
        assert approvals.status_code == 200
        approval_id = approvals.json()[0]["id"]

        approval_update = client.patch(
            f"/v1/playbooks/{playbook_id}/approvals/{approval_id}",
            headers=headers,
            json={"status": "approved", "decision_note": "Showcase approval"},
        )
        assert approval_update.status_code == 200

        comment = client.post(
            f"/v1/playbooks/{playbook_id}/comments",
            headers=headers,
            json={"comment": "Action owners aligned and in progress."},
        )
        assert comment.status_code == 201

        outcome = client.post(
            f"/v1/clients/{client_id}/events/{event_id}/outcome",
            headers=headers,
            json={
                "playbook_id": playbook_id,
                "status": "monitoring",
                "summary": "Reroute initiated for high-priority orders.",
                "actions_taken": ["Approved reroute", "Updated ETA board"],
                "eta_recovery_hours": 36,
            },
        )
        assert outcome.status_code == 201

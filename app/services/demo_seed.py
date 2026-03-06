from sqlmodel import Session, select

from app.config import settings
from app.models import AlertSubscription, Client, User
from app.security import hash_password
from app.services.ingestion import IngestionService
from app.services.supply_map import upsert_supply_map
from app.schemas import SupplyMapUpsertRequest
from app.utils import now_utc


def seed_demo_workspace(session: Session, *, include_events: bool = True) -> dict[str, str]:
    existing = session.exec(select(Client).where(Client.name == "TradeShield Demo Workspace")).first()
    if existing:
        return {"client_id": existing.id}

    client = Client(
        name="TradeShield Demo Workspace",
        industry="Electronics and Semiconductors",
        country="India",
        preferences={"objective": "cost-balanced", "demo_mode": True},
        updated_at=now_utc(),
    )
    session.add(client)
    session.commit()
    session.refresh(client)

    admin = User(
        client_id=client.id,
        full_name="Demo Admin",
        email="demo.admin@tradeshield.local",
        role="admin",
        password_hash=hash_password("StrongPass123"),
        is_active=True,
        updated_at=now_utc(),
    )
    analyst = User(
        client_id=client.id,
        full_name="Demo Analyst",
        email="demo.analyst@tradeshield.local",
        role="analyst",
        password_hash=hash_password("StrongPass123"),
        is_active=True,
        updated_at=now_utc(),
    )
    session.add(admin)
    session.add(analyst)
    session.commit()

    upsert_supply_map(
        session,
        client.id,
        SupplyMapUpsertRequest(
            suppliers=[
                {
                    "name": "Supplier A",
                    "country": "China",
                    "region": "South China",
                    "commodity": "semiconductors",
                    "criticality": 0.9,
                    "substitution_score": 0.3,
                    "lead_time_sensitivity": 0.8,
                    "inventory_buffer_days": 8,
                }
            ],
            lanes=[
                {
                    "origin": "Shanghai",
                    "destination": "Nhava Sheva",
                    "mode": "sea",
                    "chokepoint": "Strait of Malacca",
                    "importance": 0.9,
                }
            ],
            sku_groups=[
                {
                    "name": "Power IC",
                    "category": "semiconductor",
                    "monthly_volume": 12000,
                    "margin_sensitivity": 0.85,
                }
            ],
        ),
    )

    policies = [
        AlertSubscription(
            client_id=client.id,
            channel="dashboard",
            target="control-tower",
            min_severity=0.55,
            industries=[client.industry],
            active=True,
            updated_at=now_utc(),
        ),
        AlertSubscription(
            client_id=client.id,
            channel="email",
            target="demo.alerts@tradeshield.local",
            min_severity=0.7,
            industries=[client.industry],
            active=True,
            updated_at=now_utc(),
        ),
    ]
    for policy in policies:
        session.add(policy)
    session.commit()

    if include_events:
        previous_demo_mode = settings.demo_mode
        previous_demo_scenario = settings.demo_scenario
        settings.demo_mode = True
        settings.demo_scenario = "all"
        try:
            IngestionService().run_cycle(session, trigger="demo_seed", queue_alerts=True)
        finally:
            settings.demo_mode = previous_demo_mode
            settings.demo_scenario = previous_demo_scenario

    return {"client_id": client.id, "admin_email": admin.email, "admin_password": "StrongPass123"}

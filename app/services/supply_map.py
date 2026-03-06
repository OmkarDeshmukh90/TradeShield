from sqlmodel import Session, select

from app.models import Client, Lane, SkuGroup, Supplier
from app.schemas import SupplyMapUpsertRequest, SupplyMapUpsertResponse
from app.services.scoring import invalidate_client_artifacts
from app.utils import now_utc


def upsert_supply_map(session: Session, client_id: str, payload: SupplyMapUpsertRequest) -> SupplyMapUpsertResponse:
    supplier_added = supplier_updated = 0
    lane_added = lane_updated = 0
    sku_added = sku_updated = 0
    touched = False

    for supplier in payload.suppliers:
        existing = session.exec(
            select(Supplier).where(
                Supplier.client_id == client_id,
                Supplier.name == supplier.name,
                Supplier.country == supplier.country,
                Supplier.commodity == supplier.commodity,
            )
        ).first()
        if existing:
            data = supplier.model_dump()
            for key, value in data.items():
                setattr(existing, key, value)
            existing.updated_at = now_utc()
            supplier_updated += 1
        else:
            session.add(Supplier(client_id=client_id, **supplier.model_dump()))
            supplier_added += 1
        touched = True

    for lane in payload.lanes:
        existing = session.exec(
            select(Lane).where(
                Lane.client_id == client_id,
                Lane.origin == lane.origin,
                Lane.destination == lane.destination,
                Lane.mode == lane.mode,
                Lane.chokepoint == lane.chokepoint,
            )
        ).first()
        if existing:
            data = lane.model_dump()
            for key, value in data.items():
                setattr(existing, key, value)
            existing.updated_at = now_utc()
            lane_updated += 1
        else:
            session.add(Lane(client_id=client_id, **lane.model_dump()))
            lane_added += 1
        touched = True

    for sku in payload.sku_groups:
        existing = session.exec(
            select(SkuGroup).where(
                SkuGroup.client_id == client_id,
                SkuGroup.name == sku.name,
                SkuGroup.category == sku.category,
            )
        ).first()
        if existing:
            data = sku.model_dump()
            for key, value in data.items():
                setattr(existing, key, value)
            existing.updated_at = now_utc()
            sku_updated += 1
        else:
            session.add(SkuGroup(client_id=client_id, **sku.model_dump()))
            sku_added += 1
        touched = True

    session.commit()
    if touched:
        client = session.get(Client, client_id)
        if client:
            client.supply_map_version += 1
            client.updated_at = now_utc()
            session.add(client)
            session.commit()
        invalidate_client_artifacts(session, client_id)

    return SupplyMapUpsertResponse(
        client_id=client_id,
        suppliers_added=supplier_added,
        suppliers_updated=supplier_updated,
        lanes_added=lane_added,
        lanes_updated=lane_updated,
        sku_groups_added=sku_added,
        sku_groups_updated=sku_updated,
    )

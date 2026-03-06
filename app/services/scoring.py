from datetime import timedelta

from sqlmodel import Session, delete, select

from app.constants import EVENT_TYPE_WEIGHTS
from app.models import Client, Event, Exposure, ImpactAssessment, Lane, Playbook, RecommendationOverride, SkuGroup, Supplier
from app.schemas import ExplainabilityDelta, ExplainabilityEstimate, ExplainabilityFactor, ExplainabilityRead
from app.utils import clamp, now_utc


def _text_blob(event: Event) -> str:
    parts = [event.title, event.description] + event.entities + event.geos
    return " ".join(part for part in parts if part).lower()


def _region_match(region: str, event_blob: str) -> float:
    if not region:
        return 0.2
    return 1.0 if region.lower() in event_blob else 0.2


def _entity_match(entity: str, event_blob: str) -> float:
    if not entity:
        return 0.25
    return 1.0 if entity.lower() in event_blob else 0.25


def _existing_exposures(session: Session, client_id: str, event_id: str) -> list[Exposure]:
    return list(
        session.exec(
            select(Exposure).where(Exposure.client_id == client_id, Exposure.event_id == event_id)
        ).all()
    )


def invalidate_client_artifacts(session: Session, client_id: str) -> None:
    session.exec(delete(Playbook).where(Playbook.client_id == client_id))
    session.exec(delete(ImpactAssessment).where(ImpactAssessment.client_id == client_id))
    session.exec(delete(Exposure).where(Exposure.client_id == client_id))
    session.commit()


def invalidate_event_artifacts(session: Session, event_id: str) -> None:
    session.exec(delete(Playbook).where(Playbook.event_id == event_id))
    session.exec(delete(ImpactAssessment).where(ImpactAssessment.event_id == event_id))
    session.exec(delete(Exposure).where(Exposure.event_id == event_id))
    session.commit()


def ensure_exposures(session: Session, client: Client, event: Event) -> list[Exposure]:
    existing = _existing_exposures(session, client.id, event.id)
    if existing:
        return existing

    event_blob = _text_blob(event)
    created: list[Exposure] = []

    suppliers = session.exec(select(Supplier).where(Supplier.client_id == client.id)).all()
    lanes = session.exec(select(Lane).where(Lane.client_id == client.id)).all()
    skus = session.exec(select(SkuGroup).where(SkuGroup.client_id == client.id)).all()

    for supplier in suppliers:
        region_component = _region_match(supplier.region, event_blob)
        commodity_component = _entity_match(supplier.commodity, event_blob)
        substitution_risk = 1.0 - supplier.substitution_score
        buffer_penalty = clamp(1.0 - (supplier.inventory_buffer_days / 45.0), 0.1, 1.0)
        sensitivity = supplier.lead_time_sensitivity

        relevance = clamp(
            0.24 * region_component
            + 0.18 * commodity_component
            + 0.2 * supplier.criticality
            + 0.18 * substitution_risk
            + 0.12 * sensitivity
            + 0.08 * buffer_penalty
        )
        exposure_score = clamp(relevance * event.severity * (0.75 + substitution_risk * 0.25))
        if exposure_score < 0.22:
            continue

        created.append(
            Exposure(
                client_id=client.id,
                event_id=event.id,
                supplier_id=supplier.id,
                exposure_score=round(exposure_score, 4),
                relevance_score=round(relevance, 4),
                notes=(
                    f"Supplier {supplier.name} exposed via {supplier.region}; "
                    f"substitution risk={substitution_risk:.2f}, buffer={supplier.inventory_buffer_days:.0f} days"
                ),
            )
        )

    for lane in lanes:
        route_terms = [lane.origin, lane.destination, lane.chokepoint or "", lane.mode]
        route_matches = sum(1 for piece in route_terms if piece and piece.lower() in event_blob)
        chokepoint_match = 1.0 if lane.chokepoint and lane.chokepoint.lower() in event_blob else 0.25
        match = clamp(0.2 + route_matches * 0.2, 0.2, 1.0)
        relevance = clamp(0.45 * match + 0.3 * lane.importance + 0.25 * chokepoint_match)
        exposure_score = clamp(relevance * event.severity)
        if exposure_score < 0.22:
            continue

        created.append(
            Exposure(
                client_id=client.id,
                event_id=event.id,
                lane_id=lane.id,
                exposure_score=round(exposure_score, 4),
                relevance_score=round(relevance, 4),
                notes=f"Lane {lane.origin}->{lane.destination} ({lane.mode}) exposed; chokepoint={lane.chokepoint or 'none'}",
            )
        )

    for sku in skus:
        category_match = _entity_match(sku.category, event_blob)
        volume_factor = clamp(sku.monthly_volume / 50000.0, 0.1, 1.0)
        relevance = clamp(0.42 * category_match + 0.38 * sku.margin_sensitivity + 0.2 * volume_factor)
        exposure_score = clamp(relevance * event.severity)
        if exposure_score < 0.28:
            continue

        created.append(
            Exposure(
                client_id=client.id,
                event_id=event.id,
                sku_group_id=sku.id,
                exposure_score=round(exposure_score, 4),
                relevance_score=round(relevance, 4),
                notes=f"SKU group {sku.name} may see margin and service-level impact",
            )
        )

    if not created:
        created.append(
            Exposure(
                client_id=client.id,
                event_id=event.id,
                exposure_score=round(clamp(event.severity * 0.25), 4),
                relevance_score=0.25,
                notes="Generic exposure generated because structural overlap is currently low.",
            )
        )

    for row in created:
        session.add(row)
    session.commit()
    for row in created:
        session.refresh(row)
    return created


def _risk_band(score: float) -> str:
    if score >= 0.8:
        return "critical"
    if score >= 0.65:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _estimate_from_inputs(
    *,
    objective: str,
    event_type: str,
    event_confidence: float,
    avg_exposure: float,
    exposure_density: float,
    substitution_gap: float,
    lead_sensitivity: float,
    inventory_buffer_days: float,
    chokepoint_density: float,
) -> dict[str, float | str]:
    type_weight = EVENT_TYPE_WEIGHTS.get(event_type, EVENT_TYPE_WEIGHTS["other"])
    objective_bias = {
        "continuity-first": 1.08,
        "cost-balanced": 1.0,
        "margin-protect": 0.95,
    }.get(objective, 1.0)
    buffer_score = clamp(1.0 - inventory_buffer_days / 45.0, 0.05, 1.0)
    risk_score = clamp(
        avg_exposure
        * type_weight
        * objective_bias
        * (0.76 + exposure_density * 0.1 + substitution_gap * 0.08 + lead_sensitivity * 0.06)
    )
    lead_time_delta_days = round(
        clamp(
            risk_score * 11.0
            + lead_sensitivity * 7.0
            + chokepoint_density * 3.0
            + buffer_score * 4.0
            - min(inventory_buffer_days / 10.0, 3.0),
            0.5,
            45.0,
        ),
        2,
    )
    cost_delta_pct = round(
        clamp(
            risk_score * 14.0
            + substitution_gap * 8.0
            + chokepoint_density * 4.0
            + (0.8 if objective == "continuity-first" else 0.0),
            0.5,
            40.0,
        ),
        2,
    )
    confidence = round(clamp(event_confidence * 0.65 + min(exposure_density * 8, 6) * 0.05 + (1.0 - buffer_score) * 0.05), 2)
    return {
        "risk_score": round(risk_score, 4),
        "lead_time_delta_days": lead_time_delta_days,
        "cost_delta_pct": cost_delta_pct,
        "confidence": confidence,
        "revenue_risk_band": _risk_band(risk_score),
    }


def _client_supply_metrics(session: Session, client_id: str) -> dict[str, float]:
    suppliers = session.exec(select(Supplier).where(Supplier.client_id == client_id)).all()
    lanes = session.exec(select(Lane).where(Lane.client_id == client_id)).all()

    if suppliers:
        avg_substitution_gap = sum(1 - supplier.substitution_score for supplier in suppliers) / len(suppliers)
        avg_lead_sensitivity = sum(supplier.lead_time_sensitivity for supplier in suppliers) / len(suppliers)
        avg_inventory_buffer = sum(supplier.inventory_buffer_days for supplier in suppliers) / len(suppliers)
        avg_criticality = sum(supplier.criticality for supplier in suppliers) / len(suppliers)
    else:
        avg_substitution_gap = 0.45
        avg_lead_sensitivity = 0.5
        avg_inventory_buffer = 14.0
        avg_criticality = 0.5

    if lanes:
        lane_importance = sum(lane.importance for lane in lanes) / len(lanes)
        chokepoint_density = sum(1 for lane in lanes if lane.chokepoint) / len(lanes)
    else:
        lane_importance = 0.5
        chokepoint_density = 0.2

    return {
        "substitution_gap": round(avg_substitution_gap, 4),
        "lead_sensitivity": round(avg_lead_sensitivity, 4),
        "inventory_buffer": round(avg_inventory_buffer, 2),
        "criticality": round(avg_criticality, 4),
        "lane_importance": round(lane_importance, 4),
        "chokepoint_density": round(chokepoint_density, 4),
    }


def ensure_impact_assessment(session: Session, client: Client, event: Event) -> ImpactAssessment:
    override = session.exec(
        select(RecommendationOverride).where(
            RecommendationOverride.client_id == client.id,
            RecommendationOverride.event_id == event.id,
            RecommendationOverride.is_active.is_(True),
        )
    ).first()
    existing = session.exec(
        select(ImpactAssessment).where(
            ImpactAssessment.client_id == client.id,
            ImpactAssessment.event_id == event.id,
        )
    ).first()
    if existing and (
        existing.supply_map_version == client.supply_map_version
        and existing.event_updated_at == event.updated_at
        and bool(existing.override_applied) == bool(override)
        and (not override or existing.updated_at >= override.updated_at)
    ):
        return existing
    if existing:
        session.delete(existing)
        session.commit()

    exposures = ensure_exposures(session, client, event)
    avg_exposure = sum(item.exposure_score for item in exposures) / len(exposures)
    top_exposure = max((item.exposure_score for item in exposures), default=0.0)
    exposure_density = clamp(len(exposures) / 8.0, 0.15, 1.0)

    supply_metrics = _client_supply_metrics(session, client.id)
    type_weight = EVENT_TYPE_WEIGHTS.get(event.type, EVENT_TYPE_WEIGHTS["other"])
    objective = (client.preferences or {}).get("objective", "cost-balanced")
    objective_bias = {
        "continuity-first": 1.08,
        "cost-balanced": 1.0,
        "margin-protect": 0.95,
    }.get(objective, 1.0)

    substitution_gap = supply_metrics["substitution_gap"]
    lead_sensitivity = supply_metrics["lead_sensitivity"]
    buffer_score = clamp(1.0 - supply_metrics["inventory_buffer"] / 45.0, 0.05, 1.0)
    chokepoint_density = supply_metrics["chokepoint_density"]
    base_estimate = _estimate_from_inputs(
        objective=objective,
        event_type=event.type,
        event_confidence=event.confidence,
        avg_exposure=avg_exposure,
        exposure_density=exposure_density,
        substitution_gap=substitution_gap,
        lead_sensitivity=lead_sensitivity,
        inventory_buffer_days=supply_metrics["inventory_buffer"],
        chokepoint_density=chokepoint_density,
    )
    risk_score = float(base_estimate["risk_score"])
    lead_time_delta_days = float(base_estimate["lead_time_delta_days"])
    cost_delta_pct = float(base_estimate["cost_delta_pct"])
    confidence = float(base_estimate["confidence"])

    rationale = [
        f"Average exposure score: {avg_exposure:.2f}; top exposure: {top_exposure:.2f}",
        f"Client substitution gap: {substitution_gap:.2f}; lead-time sensitivity: {lead_sensitivity:.2f}",
        f"Average inventory buffer: {supply_metrics['inventory_buffer']:.1f} days; chokepoint density: {chokepoint_density:.2f}",
        f"Event type weight {type_weight:.2f} applied for {event.type}",
        f"Decision objective bias applied for {objective}",
    ]
    assumptions = [
        "Supplier criticality, substitution, and buffer values are client-maintained inputs.",
        "Lead-time and cost deltas are heuristic estimates calibrated for near-term operational decisions.",
        "Assessments are recomputed when the supply map or event facts change.",
    ]
    override_applied = False
    override_notes = ""
    if override:
        if override.risk_score is not None:
            risk_score = round(clamp(override.risk_score), 4)
        if override.lead_time_delta_days is not None:
            lead_time_delta_days = round(max(0.0, override.lead_time_delta_days), 2)
        if override.cost_delta_pct is not None:
            cost_delta_pct = round(max(0.0, override.cost_delta_pct), 2)
        if override.revenue_risk_band is not None:
            revenue_risk_band = override.revenue_risk_band
        else:
            revenue_risk_band = _risk_band(risk_score)
        if override.confidence is not None:
            confidence = round(clamp(override.confidence), 2)
        override_applied = True
        override_notes = override.analyst_note or "Manual analyst override applied."
        rationale.append("Manual analyst override applied to one or more impact fields.")
        assumptions.append("Override values supersede model estimates for this event/workspace.")
    else:
        revenue_risk_band = _risk_band(risk_score)

    assessment = ImpactAssessment(
        client_id=client.id,
        event_id=event.id,
        risk_score=round(risk_score, 4),
        lead_time_delta_days=lead_time_delta_days,
        cost_delta_pct=cost_delta_pct,
        revenue_risk_band=revenue_risk_band,
        confidence=confidence,
        supply_map_version=client.supply_map_version,
        event_updated_at=event.updated_at,
        override_applied=override_applied,
        override_notes=override_notes,
        rationale=rationale,
        assumptions=assumptions,
        updated_at=now_utc(),
    )
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def build_explainability(session: Session, client: Client, event: Event) -> ExplainabilityRead:
    assessment = ensure_impact_assessment(session, client, event)
    exposures = ensure_exposures(session, client, event)
    supply_metrics = _client_supply_metrics(session, client.id)
    objective = (client.preferences or {}).get("objective", "cost-balanced")

    avg_exposure = sum(item.exposure_score for item in exposures) / len(exposures)
    exposure_density = clamp(len(exposures) / 8.0, 0.15, 1.0)
    substitution_gap = supply_metrics["substitution_gap"]
    lead_sensitivity = supply_metrics["lead_sensitivity"]
    inventory_buffer_days = supply_metrics["inventory_buffer"]
    inventory_buffer_factor = clamp(1.0 - inventory_buffer_days / 45.0, 0.05, 1.0)
    chokepoint_density = supply_metrics["chokepoint_density"]

    base = _estimate_from_inputs(
        objective=objective,
        event_type=event.type,
        event_confidence=event.confidence,
        avg_exposure=avg_exposure,
        exposure_density=exposure_density,
        substitution_gap=substitution_gap,
        lead_sensitivity=lead_sensitivity,
        inventory_buffer_days=inventory_buffer_days,
        chokepoint_density=chokepoint_density,
    )
    base_estimate = ExplainabilityEstimate(
        risk_score=float(base["risk_score"]),
        lead_time_delta_days=float(base["lead_time_delta_days"]),
        cost_delta_pct=float(base["cost_delta_pct"]),
        confidence=float(base["confidence"]),
        revenue_risk_band=str(base["revenue_risk_band"]),
    )

    raw = [
        ("Exposure overlap", avg_exposure, 0.5),
        ("Inventory buffer risk", inventory_buffer_factor, 0.15),
        ("Substitution gap", substitution_gap, 0.2),
        ("Lead-time sensitivity", lead_sensitivity, 0.15),
    ]
    total = sum(value * weight for _, value, weight in raw) or 1.0
    factors = [
        ExplainabilityFactor(
            name=name,
            value=round(value, 4),
            weight=round(weight, 4),
            contribution=round((value * weight) / total, 4),
        )
        for name, value, weight in raw
    ]

    override_estimate = None
    delta = None
    if assessment.override_applied:
        override_estimate = ExplainabilityEstimate(
            risk_score=assessment.risk_score,
            lead_time_delta_days=assessment.lead_time_delta_days,
            cost_delta_pct=assessment.cost_delta_pct,
            confidence=assessment.confidence,
            revenue_risk_band=assessment.revenue_risk_band,
        )
        delta = ExplainabilityDelta(
            risk_score_delta=round(override_estimate.risk_score - base_estimate.risk_score, 4),
            lead_time_delta_days_delta=round(override_estimate.lead_time_delta_days - base_estimate.lead_time_delta_days, 4),
            cost_delta_pct_delta=round(override_estimate.cost_delta_pct - base_estimate.cost_delta_pct, 4),
            confidence_delta=round(override_estimate.confidence - base_estimate.confidence, 4),
        )

    confidence_note = (
        "Confidence incorporates source confidence, exposure coverage, and inventory-buffer resilience."
    )

    return ExplainabilityRead(
        event_id=event.id,
        client_id=client.id,
        factors=factors,
        base_estimate=base_estimate,
        override_estimate=override_estimate,
        delta=delta,
        top_rationale=assessment.rationale[:5],
        assumptions=assessment.assumptions,
        confidence_note=confidence_note,
    )


def client_risk_snapshot(session: Session, client_id: str, window_hours: int = 72) -> list[tuple[ImpactAssessment, Event]]:
    cutoff = now_utc() - timedelta(hours=window_hours)
    assessments = session.exec(
        select(ImpactAssessment).where(
            ImpactAssessment.client_id == client_id,
            ImpactAssessment.updated_at >= cutoff,
        )
    ).all()

    pairs: list[tuple[ImpactAssessment, Event]] = []
    for assessment in assessments:
        event = session.get(Event, assessment.event_id)
        if not event:
            continue
        pairs.append((assessment, event))
    pairs.sort(key=lambda pair: pair[0].risk_score, reverse=True)
    return pairs

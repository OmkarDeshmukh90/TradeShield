from sqlmodel import Session, select

from app.config import settings
from app.constants import DEFAULT_APPROVAL_STEPS, DEFAULT_OWNER_ASSIGNMENTS
from app.models import Client, Event, Playbook, PlaybookApproval, RecommendationOverride
from app.services.scoring import ensure_impact_assessment
from app.utils import clamp, now_utc


def _scenario_templates(event_type: str) -> dict[str, list[str]]:
    catalog = {
        "tariff/policy": [
            "Shift volume to prequalified lower-duty origins for the affected commodity",
            "Update landed-cost assumptions and reprice open procurement decisions",
            "Engage customs broker and legal team on temporary classification or notice changes",
        ],
        "conflict/security": [
            "Reserve alternate lanes outside the affected risk zone",
            "Escalate supplier security status and verify shipment insurance coverage",
            "Prioritize critical orders for controlled expedite capacity",
        ],
        "disaster/weather": [
            "Confirm supplier recovery timeline and plant operating status",
            "Use inventory buffers for critical SKUs while re-sequencing production",
            "Move inbound flow to the next-best operational port or airport",
        ],
        "logistics congestion": [
            "Split shipments by customer priority and due date risk",
            "Book blended sea-air or alternate port routings for time-sensitive orders",
            "Delay low-priority replenishment to protect premium capacity for critical SKUs",
        ],
        "sanctions/compliance": [
            "Run supplier, vessel, and counterparty screening before release",
            "Block risky purchase orders until legal review is complete",
            "Activate backup approved suppliers in compliant jurisdictions",
        ],
        "operational incidents": [
            "Confirm the facility outage duration and recovery milestones",
            "Reallocate production across alternate approved suppliers",
            "Protect the highest-margin or most contractual orders first",
        ],
    }
    return {
        "continuity-first": catalog.get(event_type, catalog["logistics congestion"]),
        "cost-balanced": catalog.get(event_type, catalog["logistics congestion"]),
        "margin-protect": catalog.get(event_type, catalog["operational incidents"]),
    }


def _scenario_options(
    client: Client,
    event: Event,
    risk_score: float,
    lead_delta: float,
    cost_delta: float,
    risk_band: str,
) -> list[dict]:
    objective = (client.preferences or {}).get("objective", "cost-balanced")
    templates = _scenario_templates(event.type)

    continuity_conf = clamp(0.72 + risk_score * 0.2 + (0.05 if objective == "continuity-first" else 0.0))
    balanced_conf = clamp(0.68 + risk_score * 0.14 + (0.04 if objective == "cost-balanced" else 0.0))
    margin_conf = clamp(0.66 + (1 - risk_score) * 0.18 + (0.05 if objective == "margin-protect" else 0.0))

    return [
        {
            "name": "continuity-first",
            "objective": "Protect service levels and prevent line stoppage",
            "actions": templates["continuity-first"],
            "expected_outcome": f"Lead-time impact pulled toward ~{max(1.0, lead_delta * 0.55):.1f} days with higher expedite spend.",
            "tradeoffs": "Higher freight and working-capital cost in exchange for continuity.",
            "assumptions": [
                "Secondary suppliers or alternate lanes can be activated within 48 hours.",
                "Critical SKUs are clearly prioritized in the client's planning process.",
            ],
            "confidence": round(continuity_conf, 2),
        },
        {
            "name": "cost-balanced",
            "objective": "Balance continuity, service, and landed-cost discipline",
            "actions": [
                templates["cost-balanced"][0],
                "Re-sequence dispatches using customer priority tiers and stock cover",
                "Share disruption assumptions across procurement, logistics, and finance in one control-tower review",
            ],
            "expected_outcome": f"Cost impact held near ~{max(0.5, cost_delta * 0.72):.1f}% with moderate service slippage.",
            "tradeoffs": "Accepts controlled delay on lower-priority orders to limit premium logistics cost.",
            "assumptions": [
                "Demand can be prioritized by service criticality.",
                "The business can tolerate moderate ETA movement on non-critical lanes.",
            ],
            "confidence": round(balanced_conf, 2),
        },
        {
            "name": "margin-protect",
            "objective": "Protect contribution margin during a prolonged disruption",
            "actions": [
                templates["margin-protect"][0],
                "Limit replenishment for low-margin or low-priority product groups",
                "Apply temporary commercial guardrails to absorb disruption cost selectively",
            ],
            "expected_outcome": f"Cost impact held near ~{max(0.3, cost_delta * 0.48):.1f}% with a longer recovery window.",
            "tradeoffs": "Higher delay tolerance and selective service degradation while preserving margin.",
            "assumptions": [
                "Commercial teams can align customers to revised order terms.",
                "The business can defer lower-priority demand without major revenue loss.",
            ],
            "confidence": round(margin_conf, 2),
        },
    ]


def _recommended_option(client: Client, risk_band: str, lead_delta: float, cost_delta_pct: float) -> str:
    objective = (client.preferences or {}).get("objective", "cost-balanced")
    if risk_band in {"critical", "high"} and lead_delta >= 6:
        return "continuity-first"
    if objective == "margin-protect" or cost_delta_pct >= 10:
        return "margin-protect"
    if objective == "continuity-first":
        return "continuity-first"
    return "cost-balanced"


def ensure_playbook_approvals(session: Session, playbook: Playbook) -> list[PlaybookApproval]:
    approvals = session.exec(
        select(PlaybookApproval)
        .where(PlaybookApproval.playbook_id == playbook.id)
        .order_by(PlaybookApproval.step_order.asc())
    ).all()
    if approvals:
        return approvals

    created: list[PlaybookApproval] = []
    for index, step_name in enumerate(playbook.approval_steps, start=1):
        approval = PlaybookApproval(
            client_id=playbook.client_id,
            playbook_id=playbook.id,
            step_order=index,
            step_name=step_name,
            status="pending",
            updated_at=now_utc(),
        )
        session.add(approval)
        created.append(approval)
    session.commit()
    return session.exec(
        select(PlaybookApproval)
        .where(PlaybookApproval.playbook_id == playbook.id)
        .order_by(PlaybookApproval.step_order.asc())
    ).all()


def generate_playbook(session: Session, client: Client, event: Event) -> Playbook:
    override = session.exec(
        select(RecommendationOverride).where(
            RecommendationOverride.client_id == client.id,
            RecommendationOverride.event_id == event.id,
            RecommendationOverride.is_active.is_(True),
        )
    ).first()
    existing = session.exec(
        select(Playbook).where(Playbook.client_id == client.id, Playbook.event_id == event.id)
    ).first()
    if existing and (
        existing.supply_map_version == client.supply_map_version
        and existing.event_updated_at == event.updated_at
        and bool(existing.override_applied) == bool(override)
        and (not override or existing.updated_at >= override.updated_at)
    ):
        ensure_playbook_approvals(session, existing)
        return existing
    if existing:
        approvals = session.exec(select(PlaybookApproval).where(PlaybookApproval.playbook_id == existing.id)).all()
        for approval in approvals:
            session.delete(approval)
        session.commit()
        session.delete(existing)
        session.commit()

    impact = ensure_impact_assessment(session, client, event)
    options = _scenario_options(
        client=client,
        event=event,
        risk_score=impact.risk_score,
        lead_delta=impact.lead_time_delta_days,
        cost_delta=impact.cost_delta_pct,
        risk_band=impact.revenue_risk_band,
    )
    recommended = _recommended_option(client, impact.revenue_risk_band, impact.lead_time_delta_days, impact.cost_delta_pct)
    override_applied = False
    override_notes = ""
    if override and override.recommended_option:
        recommended = override.recommended_option
        override_applied = True
        override_notes = override.analyst_note or "Manual analyst override applied."
    elif impact.override_applied:
        override_applied = True
        override_notes = impact.override_notes

    playbook = Playbook(
        client_id=client.id,
        event_id=event.id,
        options=options,
        recommended_option=recommended,
        supply_map_version=client.supply_map_version,
        event_updated_at=event.updated_at,
        override_applied=override_applied,
        override_notes=override_notes,
        approval_steps=DEFAULT_APPROVAL_STEPS,
        owner_assignments=DEFAULT_OWNER_ASSIGNMENTS,
        model_version=settings.model_version,
        updated_at=now_utc(),
    )
    session.add(playbook)
    session.commit()
    session.refresh(playbook)
    ensure_playbook_approvals(session, playbook)
    return playbook

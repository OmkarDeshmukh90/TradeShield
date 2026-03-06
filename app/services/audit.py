from typing import Any

from sqlmodel import Session

from app.models import AuditLog, User


def log_audit_event(
    session: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor: User | None = None,
    client_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    record = AuditLog(
        client_id=client_id or (actor.client_id if actor else None),
        actor_user_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record

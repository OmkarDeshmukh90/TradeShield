import httpx

from app.config import settings
from app.connectors.base import BaseConnector, ConnectorEvent
from app.utils import build_event_fingerprint, clamp, now_utc, parse_datetime


class SpireConnector(BaseConnector):
    """Optional premium feed connector for maritime congestion/routing signals."""

    name = "spire"
    endpoint = "https://api.spire.com/v2/port-events"

    def fetch(self) -> list[ConnectorEvent]:
        if not settings.spire_api_key:
            return []

        response = httpx.get(
            self.endpoint,
            headers={"Authorization": f"Bearer {settings.spire_api_key}"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        records = payload.get("data") or payload.get("events") or []

        events: list[ConnectorEvent] = []
        for record in records[:30]:
            title = record.get("title") or record.get("event_type") or "Spire maritime signal"
            severity = clamp(float(record.get("severity", 0.65)), 0.3, 1.0)
            confidence = clamp(float(record.get("confidence", 0.8)), 0.5, 1.0)
            when = record.get("occurred_at") or record.get("timestamp")
            occurred_at = parse_datetime(when) if isinstance(when, str) else now_utc()

            events.append(
                ConnectorEvent(
                    source="Spire",
                    source_event_id=str(
                        record.get("id")
                        or build_event_fingerprint([title, str(when or ""), record.get("port_name", ""), record.get("region", "")])[:48]
                    ),
                    title=title[:220],
                    description=record.get("description") or "Premium maritime event signal",
                    occurred_at=occurred_at,
                    event_type="logistics congestion",
                    geos=[record.get("port_name", ""), record.get("region", "")],
                    entities=["maritime", "port", "vessel routing"],
                    severity=severity,
                    confidence=confidence,
                    evidence=[{"title": "Spire Maritime Feed", "url": self.endpoint, "source": "Spire"}],
                    raw_payload=record,
                )
            )
        return events

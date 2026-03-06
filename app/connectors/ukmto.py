import re

import httpx

from app.connectors.base import BaseConnector, ConnectorEvent
from app.utils import build_event_fingerprint, now_utc


class UKMTOConnector(BaseConnector):
    name = "ukmto"
    endpoint = "https://www.ukmto.org/ukmto-products/advisories"

    def fetch(self) -> list[ConnectorEvent]:
        response = httpx.get(self.endpoint, timeout=20.0)
        response.raise_for_status()
        text = response.text

        matches = re.findall(r"(?i)(advisory[^<]{0,180})", text)
        events: list[ConnectorEvent] = []
        for match in matches[:10]:
            cleaned = re.sub(r"\s+", " ", match).strip()
            events.append(
                ConnectorEvent(
                    source="UKMTO",
                    source_event_id=build_event_fingerprint(["ukmto", cleaned])[:32],
                    title=cleaned[:220],
                    description="Maritime security advisory issued by UKMTO.",
                    occurred_at=now_utc(),
                    event_type="conflict/security",
                    geos=["Red Sea", "Gulf of Aden", "Arabian Sea"],
                    entities=["maritime", "shipping", "security advisory"],
                    severity=0.72,
                    confidence=0.74,
                    evidence=[{"title": "UKMTO Advisory", "url": self.endpoint, "source": "UKMTO"}],
                    raw_payload={"snippet": cleaned},
                )
            )
        return events
